import json
import logging
from typing import List, Optional

import httpx

from app.models.abs import Book

from .base import AIService, IncrementalJSONParser, ModelInfo, ProviderInfo

logger = logging.getLogger(__name__)


class OpenAICompatibleService(AIService):
    """Generic provider for any OpenAI-compatible endpoint (e.g. LiteLLM, vLLM).

    Talks the standard OpenAI REST surface: ``GET {base_url}/models`` for
    discovery and ``POST {base_url}/chat/completions`` for generation. The base
    URL and (optional) API key are supplied by the user via the frontend.
    """

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

    def _get_base_url(self, config=None) -> Optional[str]:
        """Get the current base URL from config or saved configuration."""
        if config and config.get("base_url"):
            base_url = config["base_url"]
        else:
            from ...core.config import get_app_config

            app_config = get_app_config()
            base_url = app_config.llm.openai_compatible.base_url

        if not base_url:
            return None

        # Ensure a scheme is present and drop any trailing slash so we can
        # safely append paths like "/models".
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"

        return base_url.rstrip("/")

    def _get_api_key(self, config=None) -> str:
        """Get the current API key. Optional for local/keyless gateways."""
        if config and config.get("api_key"):
            return config["api_key"]

        from ...core.config import get_app_config

        app_config = get_app_config()
        return app_config.llm.openai_compatible.api_key

    def _create_headers(self, api_key: str = "") -> dict:
        """Build request headers, including auth only when a key is set."""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

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

    async def load_saved_config(self) -> dict:
        """Load saved configuration for the OpenAI-compatible provider."""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "base_url": config.llm.openai_compatible.base_url,
            "api_key": config.llm.openai_compatible.api_key,
            "enabled": config.llm.openai_compatible.enabled,
            "validated": config.llm.openai_compatible.validated,
            "validation_status": config.llm.openai_compatible.validation_status,
            "validation_message": config.llm.openai_compatible.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation."""
        from datetime import datetime, timezone

        from ...core.config import LLMProviderConfig, save_llm_provider_config

        try:
            base_url = self._get_base_url(config)
            if not base_url:
                return False, "Base URL is required"

            valid, message = await self.validate_config(**config)

            provider_config = LLMProviderConfig(
                base_url=base_url,
                api_key=config.get("api_key", ""),
                enabled=config.get("enabled", True),
                validated=valid,
                last_validated=datetime.now(timezone.utc) if valid else None,
                validation_status="configured" if valid else "error",
                validation_message=message,
                config_changed=False,
            )

            success = save_llm_provider_config("openai_compatible", provider_config)
            if success:
                self._saved_config = config.copy()
                return True, "Configuration saved successfully"
            else:
                return False, "Failed to save configuration"

        except Exception as e:
            return False, f"Error saving configuration: {str(e)}"

    def is_enabled(self) -> bool:
        """Check if this provider is enabled."""
        from ...core.config import get_app_config

        config = get_app_config()
        return config.llm.openai_compatible.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider."""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.openai_compatible.enabled = enabled
            if not enabled:
                config.llm.openai_compatible.validation_status = "disabled"
            else:
                if config.llm.openai_compatible.validated and config.llm.openai_compatible.base_url:
                    config.llm.openai_compatible.validation_status = "configured"
                else:
                    config.llm.openai_compatible.validation_status = "not_validated"
            return save_llm_provider_config("openai_compatible", config.llm.openai_compatible)
        except Exception:
            return False

    def has_config_changed(self, **new_config) -> bool:
        """Check if configuration has changed from saved state."""
        if not self._saved_config:
            try:
                import asyncio

                saved = asyncio.run(self.load_saved_config())
                self._saved_config = saved
            except Exception:
                return True

        new_base_url = self._get_base_url(new_config) or ""
        saved_base_url = (self._saved_config.get("base_url") or "").rstrip("/")

        return new_base_url != saved_base_url or new_config.get("api_key", "") != self._saved_config.get("api_key", "")

    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status."""
        from ...core.config import get_app_config

        config = get_app_config()

        provider_info = self.get_provider_info()
        provider_info.is_available = bool(config.llm.openai_compatible.base_url)
        provider_info.is_enabled = config.llm.openai_compatible.enabled
        provider_info.is_configured = config.llm.openai_compatible.validated

        if config.llm.openai_compatible.enabled:
            if config.llm.openai_compatible.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.openai_compatible.validation_status or "not_validated"
                provider_info.validation_message = config.llm.openai_compatible.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.openai_compatible.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the OpenAI-compatible provider."""
        return ProviderInfo(
            id="openai_compatible",
            name="OpenAI-Compatible",
            description="Connect to any OpenAI-compatible endpoint such as LiteLLM, vLLM, or another gateway. "
            "The Base URL should point at the API root that serves /models and /chat/completions "
            "(commonly ending in /v1).",
            setup_fields=[
                {
                    "name": "base_url",
                    "type": "text",
                    "label": "Base URL",
                    "placeholder": "http://litellm.local:4000/v1",
                    "required": True,
                },
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "placeholder": "Optional (leave blank if not required)",
                    "required": False,
                },
            ],
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the configuration by listing models."""
        base_url = self._get_base_url(config)
        if not base_url:
            return False, "Base URL is required"

        api_key = self._get_api_key(config)

        try:
            headers = self._create_headers(api_key)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/models", headers=headers)

                if response.status_code == 200:
                    return True, "Connected successfully"
                elif response.status_code in (401, 403):
                    return False, "Authentication failed - check your API key"
                elif response.status_code == 404:
                    return False, "No /models endpoint found - check the Base URL (it often ends in /v1)"
                else:
                    return False, f"API error: HTTP {response.status_code}"

        except httpx.TimeoutException:
            return False, "Connection timeout - check the URL and network"
        except httpx.ConnectError:
            return False, "Connection failed - check the URL and network"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of models advertised by the endpoint."""
        base_url = self._get_base_url()
        if not base_url:
            return []

        try:
            api_key = self._get_api_key()
            headers = self._create_headers(api_key)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{base_url}/models", headers=headers)

                if response.status_code != 200:
                    logger.error(f"Failed to get models from {base_url}: HTTP {response.status_code}")
                    return []

                models_data = response.json()
                models = []

                for model in models_data.get("data", []):
                    model_id = model.get("id", "")
                    if not model_id:
                        continue

                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=model_id,
                            supports_streaming=True,
                        )
                    )

                models.sort(key=lambda model: model.name.lower())
                return models

        except Exception as e:
            logger.error(f"Failed to get models from OpenAI-compatible endpoint: {e}")
            return []

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
        """Refine chapter titles using an OpenAI-compatible endpoint."""

        if not titles:
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, "Sending request…")

        system_prompt = self._build_system_prompt(
            deselect_non_chapters=deselect_non_chapters,
            infer_opening_credits=infer_opening_credits,
            infer_end_credits=infer_end_credits,
            preferred_titles=preferred_titles,
            additional_instructions=additional_instructions,
            book=book,
        )

        chapter_data = [{"id": idx, "title": text} for idx, text in enumerate(titles)]

        try:
            base_url = self._get_base_url()
            if not base_url:
                logger.error("OpenAI-compatible base URL not configured")
                self._notify_progress(0, "Provider not configured")
                raise ValueError("OpenAI-compatible base URL not configured")

            headers = self._create_headers(self._get_api_key())

            total_chapters = len(titles)

            base_payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(chapter_data)},
                ],
                "stream": True,
            }

            # Request JSON output, but fall back to a plain request if the
            # endpoint/model rejects response_format. A generic OpenAI-compatible
            # gateway fronts many backends, not all of which support it.
            attempts = [
                {**base_payload, "response_format": {"type": "json_object"}},
                base_payload,
            ]

            content_received = ""

            async with httpx.AsyncClient(timeout=120.0) as client:
                for attempt_index, payload in enumerate(attempts):
                    is_last_attempt = attempt_index == len(attempts) - 1
                    parser = IncrementalJSONParser()
                    content_received = ""

                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60.0,
                    ) as response:
                        if response.status_code != 200:
                            await response.aread()
                            error_text = response.text
                            # Retry without response_format if that is what was rejected.
                            if not is_last_attempt and response.status_code == 400 and "response_format" in error_text:
                                logger.warning("Endpoint rejected response_format; retrying without it")
                                continue
                            logger.error(f"OpenAI-compatible API error: {response.status_code} - {error_text}")
                            raise Exception(f"OpenAI-compatible API error: {response.status_code}")

                        async for line in response.aiter_lines():
                            if not line or not line.strip():
                                continue

                            line = line.strip()
                            if not line.startswith("data: "):
                                continue

                            data_str = line[6:]  # Remove "data: " prefix
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                choice = chunk["choices"][0]

                                if "delta" in choice and "content" in choice["delta"]:
                                    content = choice["delta"]["content"]
                                    if content:
                                        content_received += content

                                        result = parser.feed(content)
                                        if result["new_chapters"]:
                                            progress_percent = result["total_parsed"] / total_chapters * 100
                                            self._notify_progress(
                                                progress_percent,
                                                f"Processed {result['total_parsed']}/{total_chapters} chapters",
                                            )

                    # Stream completed successfully; no need to try further variants.
                    break

            self._notify_progress(100, "Processing AI response…")

            try:
                response_data = json.loads(self._strip_code_fences(content_received))

                if isinstance(response_data, list):
                    processed_chapters = response_data
                elif isinstance(response_data, dict) and "chapters" in response_data:
                    processed_chapters = response_data["chapters"]
                else:
                    processed_chapters = []
                    for value in response_data.values() if isinstance(response_data, dict) else []:
                        if isinstance(value, list):
                            processed_chapters = value
                            break

                if not processed_chapters:
                    raise ValueError("No chapter array found in response")

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse OpenAI-compatible response: {e}")
                logger.error(f"Raw response: {content_received}")
                raise

            chapters = []
            for chapter in processed_chapters:
                if isinstance(chapter, dict):
                    title = chapter.get("title")
                    if title == "null" or title is None:
                        chapters.append(None)
                    else:
                        chapters.append(title)
                else:
                    chapters.append(str(chapter) if chapter != "null" else None)

            valid_chapters = len([t for t in chapters if t])
            self._notify_progress(100, f"Generated {valid_chapters} chapter titles")

            return chapters

        except httpx.TimeoutException:
            error_msg = "Request timeout - the model may be taking longer than expected"
            logger.error("OpenAI-compatible timeout error")
            self._notify_progress(0, error_msg)
            raise
        except httpx.HTTPStatusError as e:
            error_msg = f"API error ({e.response.status_code}): {str(e)}"
            logger.error(f"OpenAI-compatible HTTP error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except httpx.RequestError as e:
            error_msg = f"Failed to connect to the endpoint - check the Base URL and network: {str(e)}"
            logger.error(f"OpenAI-compatible connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse response - invalid JSON format: {str(e)}"
            logger.error(f"OpenAI-compatible JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during processing (model: {model_id}): {str(e)}"
            logger.error(f"OpenAI-compatible unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
