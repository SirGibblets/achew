import json
import logging
from typing import List, Optional

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError, APIError


from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser, ChapterList

logger = logging.getLogger(__name__)


class GeminiService(AIService):
    """Google Gemini implementation of AIService"""

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

    def _get_api_key(self, config=None):
        """Get the current API key from config or saved configuration"""
        # First try from passed config
        if config and config.get("api_key"):
            return config["api_key"]
        else:
            # Load from saved configuration
            from ...core.config import get_app_config

            app_config = get_app_config()
            return app_config.llm.gemini.api_key

    def _create_client(self, api_key=None, stable=False):
        """Create a Gemini client with the given or current API key"""
        if not api_key:
            api_key = self._get_api_key()

        if not api_key:
            raise ValueError("Gemini API key configuration is required")

        if stable:
            # Use stable version if requested
            return genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1"),  # Stable version
            )
        else:
            return genai.Client(api_key=api_key)

    async def load_saved_config(self) -> dict:
        """Load saved configuration for Gemini provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "api_key": config.llm.gemini.api_key or "",
            "enabled": config.llm.gemini.enabled,
            "validated": config.llm.gemini.validated,
            "validation_status": config.llm.gemini.validation_status,
            "validation_message": config.llm.gemini.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from ...core.config import save_llm_provider_config, LLMProviderConfig
        from datetime import datetime, timezone

        try:
            # Get and validate API key
            api_key = self._get_api_key(config)
            if not api_key:
                return False, "Gemini API key configuration is required"

            # Validate first
            valid, message = await self.validate_config(**config)

            # Save configuration
            provider_config = LLMProviderConfig(
                api_key=api_key,
                enabled=config.get("enabled", True),
                validated=valid,
                last_validated=datetime.now(timezone.utc) if valid else None,
                validation_status="configured" if valid else "error",
                validation_message=message,
                config_changed=False,
            )

            success = save_llm_provider_config("gemini", provider_config)
            if success:
                self._saved_config = config.copy()
                return True, "Configuration saved successfully"
            else:
                return False, "Failed to save configuration"

        except Exception as e:
            return False, f"Error saving configuration: {str(e)}"

    def is_enabled(self) -> bool:
        """Check if this provider is enabled"""
        from ...core.config import get_app_config

        config = get_app_config()
        return config.llm.gemini.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.gemini.enabled = enabled
            if not enabled:
                config.llm.gemini.validation_status = "disabled"
            else:
                # When enabling, set status based on whether we have a valid config
                if config.llm.gemini.validated and config.llm.gemini.api_key:
                    config.llm.gemini.validation_status = "configured"
                else:
                    config.llm.gemini.validation_status = "not_validated"
            return save_llm_provider_config("gemini", config.llm.gemini)
        except Exception:
            return False

    def has_config_changed(self, **new_config) -> bool:
        """Check if configuration has changed from saved state"""
        if not self._saved_config:
            # Load saved config if not cached
            try:
                import asyncio

                saved = asyncio.run(self.load_saved_config())
                self._saved_config = saved
            except Exception:
                return True  # Assume changed if we can't load saved config

        # Compare relevant fields
        return new_config.get("api_key", "") != self._saved_config.get("api_key", "")

    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status"""
        from ...core.config import get_app_config

        config = get_app_config()

        provider_info = self.get_provider_info()
        provider_info.is_available = True
        provider_info.is_enabled = config.llm.gemini.enabled
        provider_info.is_configured = config.llm.gemini.validated

        # Fix status logic - if enabled but no explicit status, check if validated
        if config.llm.gemini.enabled:
            if config.llm.gemini.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.gemini.validation_status or "not_validated"
                provider_info.validation_message = config.llm.gemini.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.gemini.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the Gemini provider"""
        return ProviderInfo(
            id="gemini",
            name="Gemini",
            description="Requires a Google AI API key (free or paid tier).",
            setup_fields=[
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "placeholder": "Gemini API Key",
                    "required": True,
                    "help_url": "https://aistudio.google.com/apikey",
                }
            ],
            is_available=True,
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the Gemini configuration by trying to list models"""
        # Get API key using helper method
        api_key = self._get_api_key(config)

        # API key is required
        if not api_key:
            return False, "Gemini API key configuration is required"

        try:
            # Create client using helper method
            client = self._create_client(api_key)

            # Test the API key with a simple request
            client.models.list()
            return True, "Connected successfully"

        except Exception as e:
            logger.error(f"Gemini Validation exception: {type(e).__name__}: {e}", exc_info=True)
            if "API_KEY_INVALID" in str(e) or "invalid" in str(e).lower():
                return False, "Invalid API key"
            elif "quota" in str(e).lower() or "billing" in str(e).lower():
                return False, "API quota exceeded or billing issue"
            return False, f"Connection failed: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available Gemini models"""
        try:
            # Get API key and create client
            api_key = self._get_api_key()
            if not api_key:
                logger.warning("Gemini No API key configured, returning empty model list")
                return []

            client = self._create_client(api_key, stable=True)
            models_response = client.models.list()

            models = []

            for model in models_response:
                logger.debug(f"Gemini Processing model: {model.name}")

                if (
                    "gemini" in model.name
                    and "generateContent" in getattr(model, "supported_actions", [])
                    and model.name.endswith(("pro", "flash", "lite"))
                ):
                    display_name = model.display_name or model.name.replace("models/", "").replace("-", " ").title()
                    model_info = ModelInfo(
                        id=model.name,
                        name=display_name,
                        description=model.description,
                        supports_streaming=True,
                    )
                    models.append(model_info)
                    logger.debug(f"Gemini Added model: {model_info.name} (id: {model_info.id})")

            # Sort by preference (gemini-2.5 first, then others)
            def sort_key(model):
                if "gemini-2.5" in model.id:
                    return 0
                elif "gemini-2.0" in model.id:
                    return 1
                elif "gemini-1.5" in model.id:
                    return 2
                else:
                    return 3

            models.sort(key=sort_key)

            return models

        except Exception as e:
            logger.error(f"Failed to get Gemini models: {e}", exc_info=True)
            return []

    async def process_chapter_titles(
        self,
        transcriptions: List[str],
        model_id: str,
        additional_instructions: List[str] = None,
        deselect_non_chapters: bool = True,
        infer_opening_credits: bool = True,
        infer_end_credits: bool = True,
        preferred_titles: List[str] = None,
    ) -> List[Optional[str]]:
        """Process transcriptions into chapter titles using Gemini"""

        if not transcriptions:
            logger.warning("Gemini No transcriptions provided, returning empty list")
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Sending request to Gemini...")

        # Build system prompt dynamically based on options
        system_prompt = self._build_system_prompt(
            deselect_non_chapters=deselect_non_chapters,
            infer_opening_credits=infer_opening_credits,
            infer_end_credits=infer_end_credits,
            preferred_titles=preferred_titles,
            additional_instructions=additional_instructions,
        )

        # Create JSON input for all chapters
        chapter_data = [{"id": idx, "title": text} for idx, text in enumerate(transcriptions)]
        user_message = f"Input data:\n{json.dumps(chapter_data)}"

        try:
            # Get API key and create client
            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("Gemini API key configuration is required")

            processing_client = self._create_client(api_key)

            # Initialize incremental parser for progress tracking
            parser = IncrementalJSONParser()
            total_chapters = len(transcriptions)

            # Combine system prompt and user message
            combined_prompt = f"{system_prompt}\n\n{user_message}"

            # Use structured output with ChapterList model
            stream_count = 0
            content_received = ""

            # Enable thinking only for gemini-2.5 models
            thinking_budget = 0
            if "gemini-2.5" in model_id:
                thinking_budget = 1024

            # Stream the response for progress updates
            async for chunk in await processing_client.aio.models.generate_content_stream(
                model=model_id,
                contents=combined_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ChapterList,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=thinking_budget,
                        include_thoughts=True,
                    ),
                ),
            ):
                stream_count += 1
                logger.debug(f"Gemini Received chunk {stream_count}: {chunk}")

                for part in chunk.candidates[0].content.parts:
                    if not part.text:
                        continue

                    if part.thought:
                        self._notify_progress(0, "Thinking...")
                    else:
                        content = part.text
                        content_received += content
                        logger.debug(f"Gemini Content chunk: '{content}'")

                        result = parser.feed(content)
                        if result["new_chapters"]:
                            progress_percent = result["total_parsed"] / total_chapters * 100
                            self._notify_progress(
                                progress_percent,
                                f"Processed {result['total_parsed']}/{total_chapters} chapters",
                            )

            if not content_received:
                logger.error("Gemini No content received from streaming!")

            self._notify_progress(100, "Processing AI response...")

            # Parse the response
            try:
                response_data = json.loads(content_received)
                processed_chapters = response_data.get("chapters", [])

            except json.JSONDecodeError as e:
                logger.error(f"Gemini Failed to parse Gemini response as JSON: {e}")
                logger.error(f"Gemini Raw response: {content_received}")
                raise

            # Convert to title list
            chapters = [
                None if chapter.get("title") == "null" or chapter.get("title") is None else chapter.get("title")
                for chapter in processed_chapters
            ]

            valid_chapters = len([t for t in chapters if t])

            self._notify_progress(100, f"Generated {valid_chapters} chapter titles")

            return chapters

        except ClientError as e:
            error_msg = f"Gemini Client error: {str(e)}"
            logger.error(f"Gemini Client error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except ServerError as e:
            error_msg = f"Gemini server error - please wait and try again: {str(e)}"
            logger.error(f"Gemini server error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except APIError as e:
            error_msg = f"Google Gemini API error: {str(e)}"
            logger.error(f"Gemini API error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse Gemini response - invalid JSON format: {str(e)}"
            logger.error(f"Gemini JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during Gemini processing (model: {model_id}): {str(e)}"
            logger.error(f"Gemini unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
