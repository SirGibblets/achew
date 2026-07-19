import json
import logging
import time
from typing import List, Optional

import httpx

from app.models.abs import Book

from .base import CHAPTERS_RESPONSE_FORMAT, AIService, IncrementalJSONParser, ModelInfo, ProviderInfo, coerce_bool

logger = logging.getLogger(__name__)

# Model loading can take a while on first use, so allow generous read timeouts.
REQUEST_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


class LMStudioService(AIService):
    """LM Studio implementation of AIService for local models.

    Talks to LM Studio's REST API over HTTP(S): ``GET {host}/api/v0/models``
    for model discovery (with a fallback to the OpenAI-compatible
    ``/v1/models``) and ``POST {host}/v1/chat/completions`` for generation.
    Using the REST API instead of the websocket SDK allows optional API token
    authentication and HTTPS hosts (including self-signed certificates).
    """

    # Self-hosted: the user controls the model list, so always fetch it fresh.
    CACHE_MODELS = False

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

    def _get_host(self, config=None) -> Optional[str]:
        """Get the current host from config or saved configuration"""
        # First try from passed config
        if config and config.get("host"):
            host = config["host"]
        else:
            # Load from saved configuration
            from ...core.config import get_app_config

            app_config = get_app_config()
            host = app_config.llm.lm_studio.host

        if not host:
            return None

        # Ensure host has proper format (default port for LM Studio is 1234)
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"

        return host.rstrip("/")

    def _get_api_key(self, config=None) -> str:
        """Get the current API token. Optional unless authentication is enabled in LM Studio."""
        if config and config.get("api_key"):
            return config["api_key"]

        from ...core.config import get_app_config

        app_config = get_app_config()
        return app_config.llm.lm_studio.api_key

    def _get_skip_ssl_verify(self, config=None) -> bool:
        """Get whether TLS certificate verification should be skipped."""
        if config and "skip_ssl_verify" in config:
            return coerce_bool(config["skip_ssl_verify"])

        from ...core.config import get_app_config

        app_config = get_app_config()
        return app_config.llm.lm_studio.skip_ssl_verify

    def _create_headers(self, api_key: str = "") -> dict:
        """Build request headers, including auth only when a token is set."""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _extract_error_message(error_text: str) -> str:
        """Pull the human-readable message out of an OpenAI-style JSON error body.

        Falls back to the raw (truncated) body when it isn't JSON; returns an
        empty string when there is no useful detail.
        """
        try:
            error = json.loads(error_text).get("error", "")
            if isinstance(error, dict):
                error = error.get("message", "")
            if isinstance(error, str):
                return error.strip()[:300]
        except (json.JSONDecodeError, AttributeError):
            pass
        return error_text.strip()[:300]

    async def _model_not_loaded(self, client: httpx.AsyncClient, host: str, headers: dict, model_id: str) -> bool:
        """Check whether a chat failure is explained by an unloaded model.

        LM Studio only loads models on demand when JIT model loading is enabled
        in its server settings; with it disabled, requests against an unloaded
        model fail. Best-effort: any error here means "don't know", not "yes".
        """
        try:
            response = await client.get(f"{host}/api/v0/models", headers=headers, timeout=10.0)
            if response.status_code != 200:
                return False
            for model in response.json().get("data", []):
                if model.get("id") == model_id:
                    return model.get("state") == "not-loaded"
        except Exception as e:
            logger.debug(f"LM Studio model state check failed: {e}")
        return False

    async def load_saved_config(self) -> dict:
        """Load saved configuration for LM Studio provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "host": config.llm.lm_studio.host or "",
            "api_key": config.llm.lm_studio.api_key,
            "skip_ssl_verify": config.llm.lm_studio.skip_ssl_verify,
            "enabled": config.llm.lm_studio.enabled,
            "validated": config.llm.lm_studio.validated,
            "validation_status": config.llm.lm_studio.validation_status,
            "validation_message": config.llm.lm_studio.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from datetime import datetime, timezone

        from ...core.config import LLMProviderConfig, save_llm_provider_config

        try:
            # Get and validate host
            host = self._get_host(config)
            if not host:
                return False, "LM Studio server URL is required"

            # Validate first
            valid, message = await self.validate_config(**config)

            # The frontend omits the api_key field when it is unchanged (it only
            # ever sees a masked value), so fall back to the saved token rather
            # than wiping it. An explicit empty string still clears it.
            api_key = config["api_key"] if "api_key" in config else self._get_api_key()

            # Save configuration
            provider_config = LLMProviderConfig(
                host=host,
                api_key=api_key,
                skip_ssl_verify=self._get_skip_ssl_verify(config),
                enabled=config.get("enabled", True),
                validated=valid,
                last_validated=datetime.now(timezone.utc) if valid else None,
                validation_status="configured" if valid else "error",
                validation_message=message,
                config_changed=False,
            )

            success = save_llm_provider_config("lm_studio", provider_config)
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
        return config.llm.lm_studio.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.lm_studio.enabled = enabled
            if not enabled:
                config.llm.lm_studio.validation_status = "disabled"
            else:
                # When enabling, set status based on whether we have a valid config
                if config.llm.lm_studio.validated:
                    config.llm.lm_studio.validation_status = "configured"
                else:
                    config.llm.lm_studio.validation_status = "not_validated"
            return save_llm_provider_config("lm_studio", config.llm.lm_studio)
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

        # Compare relevant fields using helper method
        new_host = self._get_host(new_config) or ""
        saved_host = self._saved_config.get("host", "")

        return (
            new_host != saved_host
            or new_config.get("api_key", "") != self._saved_config.get("api_key", "")
            or self._get_skip_ssl_verify(new_config) != coerce_bool(self._saved_config.get("skip_ssl_verify", False))
        )

    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status"""
        from ...core.config import get_app_config

        config = get_app_config()

        provider_info = self.get_provider_info()
        provider_info.is_available = True
        provider_info.is_enabled = config.llm.lm_studio.enabled
        provider_info.is_configured = config.llm.lm_studio.validated

        # Fix status logic - if enabled but no explicit status, check if validated
        if config.llm.lm_studio.enabled:
            if config.llm.lm_studio.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.lm_studio.validation_status or "not_validated"
                provider_info.validation_message = config.llm.lm_studio.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.lm_studio.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the LM Studio provider"""
        return ProviderInfo(
            id="lm_studio",
            name="LM Studio",
            description="Free and private access to local LLMs when you self-host LM Studio. Be aware that small models may not produce usable results.",
            setup_fields=[
                {
                    "name": "host",
                    "type": "text",
                    "label": "Server URL",
                    "placeholder": "Server URL (e.g. http://localhost:1234)",
                    "required": True,
                    "help_url": "https://lmstudio.ai/docs/app/api",
                },
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Token",
                    "placeholder": "API Token (leave blank if authentication is disabled)",
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
            is_available=True,
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the LM Studio configuration by trying to list models"""
        # Get host using helper method
        host = self._get_host(config)

        # Host is required
        if not host:
            return False, "LM Studio server URL is required"

        try:
            headers = self._create_headers(self._get_api_key(config))
            verify = not self._get_skip_ssl_verify(config)
            async with httpx.AsyncClient(timeout=10.0, verify=verify) as client:
                response = await client.get(f"{host}/v1/models", headers=headers)

                if response.status_code == 200:
                    return True, "Connected successfully"
                elif response.status_code in (401, 403):
                    return False, "Authentication failed - check your API token"
                elif response.status_code == 404:
                    return False, "LM Studio API not found - ensure the server is running"
                else:
                    detail = self._extract_error_message(response.text)
                    return False, f"LM Studio error: HTTP {response.status_code}" + (f" - {detail}" if detail else "")

        except httpx.TimeoutException:
            logger.error("LM Studio Connection timeout")
            return False, "Connection timeout - check URL and network"
        except Exception as e:
            logger.error(f"LM Studio Validation exception: {type(e).__name__}: {e}", exc_info=True)
            return False, f"Connection failed: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available LM Studio models"""
        host = self._get_host()
        if not host:
            logger.warning("LM Studio No host configured, returning empty model list")
            return []

        try:
            headers = self._create_headers(self._get_api_key())
            verify = not self._get_skip_ssl_verify()

            async with httpx.AsyncClient(timeout=30.0, verify=verify) as client:
                # Prefer the native REST API, which includes model metadata such
                # as architecture and context length.
                response = await client.get(f"{host}/api/v0/models", headers=headers)
                if response.status_code != 200:
                    logger.info(f"LM Studio /api/v0/models returned HTTP {response.status_code}, trying /v1/models")
                    response = await client.get(f"{host}/v1/models", headers=headers)

                if response.status_code != 200:
                    logger.error(f"Failed to get LM Studio models: HTTP {response.status_code}")
                    return []

                models = []
                for model in response.json().get("data", []):
                    model_id = model.get("id", "")
                    if not model_id:
                        continue

                    # Skip non-LLM entries (e.g. embedding models) when the
                    # native API reports a type.
                    model_type = model.get("type")
                    if model_type and model_type not in ("llm", "vlm"):
                        continue

                    description = f"Local model: {model_id}"
                    if model.get("arch"):
                        description += f" ({model['arch']})"

                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=model_id,
                            description=description,
                            context_length=model.get("max_context_length"),
                            supports_streaming=True,
                        )
                    )

                # Sort by name for better UX
                models.sort(key=lambda m: m.name.lower())

                return models

        except Exception as e:
            logger.error(f"Failed to get LM Studio models: {e}", exc_info=True)
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
        """Refine chapter titles using LM Studio"""

        if not titles:
            logger.warning("LM Studio No titles provided, returning empty list")
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Loading LM Studio model ({model_id}), please wait…")

        # Build system prompt dynamically based on options
        system_prompt = self._build_system_prompt(
            deselect_non_chapters=deselect_non_chapters,
            infer_opening_credits=infer_opening_credits,
            infer_end_credits=infer_end_credits,
            preferred_titles=preferred_titles,
            additional_instructions=additional_instructions,
            book=book,
        )

        try:
            host = self._get_host()
            if not host:
                raise ValueError("LM Studio server URL is required")

            headers = self._create_headers(self._get_api_key())
            verify = not self._get_skip_ssl_verify()

            total_chapters = len(titles)

            base_payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Input data:\n{self._build_chapter_input(titles)}"},
                ],
                "stream": True,
            }

            structured_payload = {
                **base_payload,
                "response_format": CHAPTERS_RESPONSE_FORMAT,
            }

            # Response from gpt-oss models is currently broken when using
            # structured outputs. Seems to work well enough without it.
            if "gpt-oss" in model_id.lower():
                attempts = [base_payload]
            else:
                # Request structured output, but fall back to a plain request if
                # the model rejects response_format.
                attempts = [structured_payload, base_payload]

            content_received = ""

            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=verify) as client:
                for attempt_index, payload in enumerate(attempts):
                    is_last_attempt = attempt_index == len(attempts) - 1
                    parser = IncrementalJSONParser()
                    content_received = ""
                    last_thinking_update = 0

                    async with client.stream(
                        "POST",
                        f"{host}/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            await response.aread()
                            error_text = response.text
                            # Retry without response_format if that is what was rejected.
                            if not is_last_attempt and response.status_code == 400:
                                logger.warning(
                                    f"LM Studio rejected structured output; retrying without it: {error_text}"
                                )
                                continue
                            logger.error(f"LM Studio API error: {response.status_code} - {error_text}")

                            if response.status_code in (400, 404) and await self._model_not_loaded(
                                client, host, headers, model_id
                            ):
                                raise Exception(
                                    f'Model "{model_id}" is not loaded and JIT model loading appears to be '
                                    "disabled in LM Studio - load the model in LM Studio (or enable JIT "
                                    "model loading in its server settings) and try again"
                                )

                            detail = self._extract_error_message(error_text)
                            raise Exception(
                                f"LM Studio API error: {response.status_code}" + (f" - {detail}" if detail else "")
                            )

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
                                delta = chunk["choices"][0].get("delta", {})

                                # Handle thinking mode for models that support it
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

                    # Stream completed successfully; no need to try further variants.
                    break

            if not content_received:
                logger.error("LM Studio No content received from streaming!")

            self._notify_progress(100, "Processing AI response…")

            # Parse the response
            try:
                processed_chapters = self._extract_chapter_array(content_received)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"LM Studio Failed to parse response as JSON: {e}")
                logger.error(f"LM Studio Raw response: {content_received}")
                raise

            # Convert to title list
            chapters = [
                None if chapter.get("title") == "null" or chapter.get("title") is None else chapter.get("title")
                for chapter in processed_chapters
            ]

            valid_chapters = len([t for t in chapters if t])

            self._notify_progress(100, f"Generated {valid_chapters} chapter titles")

            return chapters

        except httpx.TimeoutException as e:
            error_msg = f"LM Studio request timed out - server may be overloaded: {str(e)}"
            logger.error(f"LM Studio timeout error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except httpx.RequestError as e:
            error_msg = f"Failed to connect to LM Studio - please ensure LM Studio is running and accessible: {str(e)}"
            logger.error(f"LM Studio connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse LM Studio response - invalid JSON format: {str(e)}"
            logger.error(f"LM Studio JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during LM Studio processing (model: {model_id}): {str(e)}"
            logger.error(f"LM Studio unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
