import asyncio
import json
import logging
import time
from typing import List, Optional

import httpx

from app.models.abs import Book

from .base import CHAPTERS_RESPONSE_FORMAT, AIService, IncrementalJSONParser, ModelInfo, ProviderInfo, coerce_bool

logger = logging.getLogger(__name__)

# How long to wait for the first streamed token before telling the user the
# endpoint may still be loading the model. There is no standard "loading"
# signal in the OpenAI API surface, so first-token latency is the best proxy.
FIRST_TOKEN_WATCHDOG_SECONDS = 5.0


class OpenAICompatibleService(AIService):
    """Generic provider for any OpenAI-compatible endpoint (e.g. LiteLLM, vLLM).

    Talks the standard OpenAI REST surface: ``GET {base_url}/models`` for
    discovery and ``POST {base_url}/chat/completions`` for generation. The base
    URL and (optional) API key are supplied by the user via the frontend.
    """

    # Self-hosted: the user controls the model list, so always fetch it fresh.
    CACHE_MODELS = False

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

    def _get_skip_ssl_verify(self, config=None) -> bool:
        """Get whether TLS certificate verification should be skipped."""
        if config and "skip_ssl_verify" in config:
            return coerce_bool(config["skip_ssl_verify"])

        from ...core.config import get_app_config

        app_config = get_app_config()
        return app_config.llm.openai_compatible.skip_ssl_verify

    def _create_headers(self, api_key: str = "") -> dict:
        """Build request headers, including auth only when a key is set."""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _start_first_token_watchdog(self) -> asyncio.Task:
        """Update the status if the endpoint is slow to produce its first token."""

        async def watchdog():
            await asyncio.sleep(FIRST_TOKEN_WATCHDOG_SECONDS)
            self._notify_progress(0, "Waiting for a response - the endpoint may be loading the model…")

        return asyncio.create_task(watchdog())

    async def load_saved_config(self) -> dict:
        """Load saved configuration for the OpenAI-compatible provider."""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "base_url": config.llm.openai_compatible.base_url,
            "api_key": config.llm.openai_compatible.api_key,
            "skip_ssl_verify": config.llm.openai_compatible.skip_ssl_verify,
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

            # The frontend omits the api_key field when it is unchanged (it only
            # ever sees a masked value), so fall back to the saved key rather
            # than wiping it. An explicit empty string still clears it.
            api_key = config["api_key"] if "api_key" in config else self._get_api_key()

            provider_config = LLMProviderConfig(
                base_url=base_url,
                api_key=api_key,
                skip_ssl_verify=self._get_skip_ssl_verify(config),
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
                saved = asyncio.run(self.load_saved_config())
                self._saved_config = saved
            except Exception:
                return True

        new_base_url = self._get_base_url(new_config) or ""
        saved_base_url = (self._saved_config.get("base_url") or "").rstrip("/")

        return (
            new_base_url != saved_base_url
            or new_config.get("api_key", "") != self._saved_config.get("api_key", "")
            or self._get_skip_ssl_verify(new_config) != coerce_bool(self._saved_config.get("skip_ssl_verify", False))
        )

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
            description="Connect to any OpenAI-compatible endpoint such as LiteLLM, vLLM, or another gateway.",
            instructions="The Base URL is the API root serving <b>/models</b> and <b>/chat/completions</b>, "
            "usually ending in <b>/v1</b>.",
            setup_fields=[
                {
                    "name": "base_url",
                    "type": "text",
                    "label": "Base URL",
                    "placeholder": "Base URL (e.g. http://litellm.local:4000/v1)",
                    "required": True,
                },
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "placeholder": "API Key (leave blank if not required)",
                    "required": False,
                },
                {
                    "name": "skip_ssl_verify",
                    "type": "checkbox",
                    "label": "Skip SSL certificate verification",
                    "help_text": "Allows HTTPS servers with self-signed certificates. Only enable this for servers you trust.",
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
            verify = not self._get_skip_ssl_verify(config)
            async with httpx.AsyncClient(timeout=10.0, verify=verify) as client:
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

            async with httpx.AsyncClient(timeout=30.0, verify=not self._get_skip_ssl_verify()) as client:
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
                    {"role": "user", "content": self._build_chapter_input(titles)},
                ],
                "stream": True,
            }

            # Try progressively less constrained output modes. The strict schema
            # can express the array shape the prompt asks for; json_object alone
            # cannot, so it is only a fallback for gateways that reject schemas.
            # A generic OpenAI-compatible gateway fronts many backends, and any
            # mode may be rejected outright (HTTP 400) or accepted but mangled
            # (e.g. Ollama's json_object grammar ends generation after a single
            # object), so both outcomes advance to the next attempt.
            attempts = [
                {**base_payload, "response_format": CHAPTERS_RESPONSE_FORMAT},
                {**base_payload, "response_format": {"type": "json_object"}},
                base_payload,
            ]

            content_received = ""
            processed_chapters = []

            async with httpx.AsyncClient(timeout=120.0, verify=not self._get_skip_ssl_verify()) as client:
                for attempt_index, payload in enumerate(attempts):
                    is_last_attempt = attempt_index == len(attempts) - 1
                    parser = IncrementalJSONParser()
                    content_received = ""
                    last_thinking_update = 0

                    watchdog = self._start_first_token_watchdog()
                    try:
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
                                # Retry with a less constrained mode if the format was rejected.
                                format_rejected = response.status_code == 400 and any(
                                    term in error_text for term in ("response_format", "json_schema", "json_object")
                                )
                                if not is_last_attempt and format_rejected:
                                    logger.warning("Endpoint rejected the response format; retrying with a simpler one")
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

                                watchdog.cancel()

                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    delta = chunk["choices"][0].get("delta", {})

                                    # Reasoning models stream thinking separately:
                                    # reasoning_content (DeepSeek/vLLM/LiteLLM/LM Studio)
                                    # or reasoning (OpenRouter).
                                    if delta.get("reasoning_content") or delta.get("reasoning"):
                                        current_time = time.time()
                                        if current_time - last_thinking_update >= 1.0:  # Limit to once per second
                                            self._notify_progress(0, "Thinking…")
                                            last_thinking_update = current_time
                                        continue

                                    content = delta.get("content")
                                    if content:
                                        content_received += content

                                        result = parser.feed(content)
                                        if result["new_chapters"]:
                                            progress_percent = result["total_parsed"] / total_chapters * 100
                                            self._notify_progress(
                                                progress_percent,
                                                f"Processed {result['total_parsed']}/{total_chapters} chapters",
                                            )
                    finally:
                        watchdog.cancel()

                    self._notify_progress(100, "Processing AI response…")

                    try:
                        processed_chapters = self._extract_chapter_array(content_received)
                    except (json.JSONDecodeError, ValueError) as e:
                        # A backend can accept a response_format yet still produce
                        # the wrong shape (e.g. Ollama's json_object mode returns a
                        # single object). Fall back to the next attempt.
                        if not is_last_attempt:
                            logger.warning(f"Could not parse response ({e}); retrying with a simpler response format")
                            continue
                        logger.error(f"Failed to parse OpenAI-compatible response: {e}")
                        logger.error(f"Raw response: {content_received}")
                        raise

                    # Stream parsed successfully; no need to try further variants.
                    break

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
