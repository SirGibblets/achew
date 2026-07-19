import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.models.abs import Book
from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


def coerce_bool(value: Any) -> bool:
    """Coerce a config value to bool, treating the strings "false"/"0"/"" as False."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


class Chapter(BaseModel):
    id: float
    title: Optional[str]


class ChapterList(BaseModel):
    chapters: list[Chapter]


# JSON schema for the chapter list every provider requests and parses. The
# array is wrapped in an object because OpenAI-style structured outputs forbid
# root arrays; the shared prompt and input data use the same wrapper, so the
# machine constraint and the prompt agree. Backends that ignore the schema
# still work: _extract_chapter_array accepts a bare array too.
CHAPTERS_SCHEMA = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title": {"type": ["string", "null"]},
                },
                "required": ["id", "title"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["chapters"],
    "additionalProperties": False,
}

# The same schema in OpenAI-style chat-completions response_format clothing.
CHAPTERS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "chapters",
        "strict": True,
        "schema": CHAPTERS_SCHEMA,
    },
}


class IncrementalJSONParser:
    """Helper class for parsing incomplete JSON streams"""

    def __init__(self):
        self.buffer = ""
        self.parsed_chapters = []

    def feed(self, chunk: str) -> dict:
        """Feed a chunk of JSON and return parsing status"""
        self.buffer += chunk

        # Try to extract complete chapter objects from the buffer
        # Look for the structured format: {"id": 0, "title": "Chapter 1"} or {"id": 0, "title": null}
        chapter_pattern = r'\{\s*"id":\s*(\d+(?:\.\d+)?)\s*,\s*"title":\s*(".*?"|null)\s*\}'

        new_chapters = []
        for match in re.finditer(chapter_pattern, self.buffer):
            try:
                chapter_id = float(match.group(1))
                title_str = match.group(2)

                # Parse the title
                if title_str == "null":
                    title = "null"
                else:
                    title = json.loads(title_str)  # Properly decode JSON string

                chapter = {"id": chapter_id, "title": title}

                # Only add if we haven't seen this chapter ID yet
                if not any(c["id"] == chapter_id for c in self.parsed_chapters):
                    new_chapters.append(chapter)
                    self.parsed_chapters.append(chapter)

            except (ValueError, json.JSONDecodeError) as e:
                logger.debug(f"Failed to parse chapter from match: {match.group(0)}: {e}")
                continue

        return {
            "new_chapters": new_chapters,
            "total_parsed": len(self.parsed_chapters),
            "buffer_size": len(self.buffer),
        }


class ModelInfo(BaseModel):
    """Information about an available model"""

    id: str
    name: str
    description: Optional[str] = None
    context_length: Optional[int] = None
    supports_streaming: bool = True


class ProviderInfo(BaseModel):
    """Information about an LLM provider"""

    id: str
    name: str
    description: str
    instructions: Optional[str] = None
    setup_fields: List[Dict[str, Any]]  # Fields needed for setup (e.g., api_key, base_url)
    is_available: bool = False
    is_enabled: bool = False
    is_configured: bool = False
    is_recommended: bool = False
    validation_status: str = "not_validated"  # disabled, not_validated, validating, configured, error
    validation_message: Optional[str] = None
    config_changed: bool = False


class AIService(ABC):
    """Abstract base class for LLM providers"""

    # Whether model lists may be cached (see registry). Self-hosted providers
    # disable this so newly added/removed models show up immediately.
    CACHE_MODELS: bool = True

    def __init__(self, progress_callback: ProgressCallback, **config):
        self.progress_callback = progress_callback
        self.config = config
        self._saved_config = {}
        self._enabled = False  # Default to disabled

    def _notify_progress(self, percent: float, message: str = ""):
        """Notify progress via callback"""
        self.progress_callback(Step.AI_CLEANUP, percent, message, {})

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip Markdown code fences some models wrap JSON in despite instructions.

        Handles blocks like ``` ```json ... ``` ``` by dropping the opening fence
        line (with any language hint) and the closing fence. Returns the input
        unchanged when no leading fence is present.
        """
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped

        lines = stripped.splitlines()
        lines = lines[1:]  # Drop the opening fence (e.g. ``` or ```json).
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # Drop the closing fence.
        return "\n".join(lines).strip()

    @staticmethod
    def _build_chapter_input(titles: List[str]) -> str:
        """Serialize the input titles as the {"chapters": [...]} JSON the prompt describes."""
        return json.dumps({"chapters": [{"id": idx, "title": text} for idx, text in enumerate(titles)]})

    @staticmethod
    def _extract_chapter_array(content: str) -> list:
        """Pull the chapter array out of a raw model response.

        Strips Markdown code fences, then accepts a bare array, a
        ``{"chapters": [...]}`` wrapper, or any object containing a list value.
        Raises ``json.JSONDecodeError`` or ``ValueError`` when no chapter array
        can be found.
        """
        response_data = json.loads(AIService._strip_code_fences(content))

        if isinstance(response_data, list):
            processed_chapters = response_data
        elif isinstance(response_data, dict) and isinstance(response_data.get("chapters"), list):
            processed_chapters = response_data["chapters"]
        else:
            processed_chapters = []
            for value in response_data.values() if isinstance(response_data, dict) else []:
                if isinstance(value, list):
                    processed_chapters = value
                    break

        if not processed_chapters:
            raise ValueError("No chapter array found in response")

        return processed_chapters

    @classmethod
    @abstractmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about this provider"""
        pass

    @abstractmethod
    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the configuration for this provider"""
        pass

    @abstractmethod
    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models for this provider"""
        pass

    @abstractmethod
    async def load_saved_config(self) -> Dict[str, Any]:
        """Load saved configuration for this provider"""
        pass

    @abstractmethod
    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if this provider is enabled"""
        pass

    @abstractmethod
    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        pass

    @abstractmethod
    def has_config_changed(self, **new_config) -> bool:
        """Check if configuration has changed from saved state"""
        pass

    @abstractmethod
    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status"""
        pass

    @staticmethod
    def _build_system_prompt(
        deselect_non_chapters: bool = True,
        infer_opening_credits: bool = True,
        infer_end_credits: bool = True,
        preferred_titles: Optional[List[str]] = None,
        additional_instructions: Optional[List[str]] = None,
        book: Optional[Book] = None,
    ) -> str:
        """Build the system prompt dynamically based on options"""
        book_title = book.media.metadata.title if book and book.media else None
        book_author = book.media.metadata.authorName if book and book.media else None

        # Base prompt
        base_prompt = """You are a helpful assistant that validates and cleans up audiobook chapter titles.
You will receive a JSON object with a "chapters" array, each item containing a chapter index (int) and a raw text transcript of the title. Note that there may be inaccuracies in the transcripts.
You will output the same structure, but with processed titles. You must respond with ONLY the raw JSON data - no additional text, comments, or markdown."""

        if book_title and book_author:
            base_prompt += f'\n\nThe book is titled "{book_title}" by {book_author}.'
        elif book_title:
            base_prompt += f'\n\nThe book is titled "{book_title}".'
        elif book_author:
            base_prompt += f"\n\nThe book is by {book_author}."

        base_prompt += """

Rules for processing chapter titles:
- For transcripts that clearly denote a numbered chapter/section (e.g., "Chapter 1", "Part 5", "One", "Section IX"):
    - Keep the terminology (e.g. "Chapter", "Part", "Section")
    - Always use digits for numbers
    - Place a colon (:) after the chapter number, but only if there is relevant title text following it
    - Do not include a colon if you do not also include text after it
- Remove any partial sentences or unrelated words at the end of the text
- Remove periods at the end of the text
- For transcripts that do not appear to denote numbered chapters/sections/etc:
    - If it appears near the start of the list:
        - It could be opening credits, a prologue, a foreword, etc. Consider labelling it accordingly."""

        # Add opening credits logic if enabled
        if infer_opening_credits:
            base_prompt += """
        - The very first item will often be named "Opening Credits\" unless it appears to be a chapter or other special section."""

        base_prompt += """
    - If it appears near the end of the list:
        - It could be closing credits, an epilogue, an afterword, etc. Consider labelling it accordingly.
        - Occasionally some books will have a chapter for bloopers, so keep an eye out for nonsensical content."""

        # Add end credits logic if enabled
        if infer_end_credits:
            base_prompt += """
        - The very last item will often be named "End Credits" unless it appears to be a chapter or other special section."""

        # Add chapter removal logic based on deselect_non_chapters setting
        if not deselect_non_chapters:
            base_prompt += "\n- Assume all items are valid chapters."
        else:
            base_prompt += """
    - If it appears in the middle of the list and doesn't seem to be a chapter/section/etc or other book division point (i.e. it appears to be narrative content), consider removing it entirely.
    - When removing a chapter, simply set the title to null instead of a string. Keep the index and do not remove the object from the list."""

        if preferred_titles:
            base_prompt += "\n\nThe following is a list of known correct chapter titles for this book. Please attempt to use these where possible. Note that the list may be incomplete:\n"
            base_prompt += "\n".join(preferred_titles)

        # Add additional instructions if provided
        if additional_instructions:
            base_prompt += "\n\nThe following are additional instructions specific to the current book, and supersede any previous instructions:\n"
            base_prompt += "\n - ".join(additional_instructions)

        return base_prompt

    @abstractmethod
    async def process_chapter_titles(
        self,
        titles: List[str],
        model_id: str,
        additional_instructions: Optional[List[str]] = None,
        deselect_non_chapters: bool = True,
        infer_opening_credits: bool = True,
        infer_end_credits: bool = True,
        preferred_titles: Optional[List[str]] = None,
        book: Optional[Book] = None,
    ) -> List[Optional[str]]:
        """Refine chapter titles using the LLM"""
        pass
