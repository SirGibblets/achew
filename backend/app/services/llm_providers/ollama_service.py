import json
import logging
import time
from typing import List, Optional
from urllib.parse import urlparse
import ollama

from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser

logger = logging.getLogger(__name__)


class OllamaService(AIService):
    """Ollama implementation of AIService for local models"""

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

        # Do not create client or validate host here - defer until needed
        # This allows safe instantiation for config/state purposes

    def _get_host(self, config=None):
        """Get the current host from config or saved configuration"""
        # First try from passed config
        if config and config.get("host"):
            host = config["host"]
        else:
            # Load from saved configuration
            from ...core.config import get_app_config

            app_config = get_app_config()
            host = app_config.llm.ollama.host

        if not host:
            return None

        # Ensure host has proper format
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"

        return host

    def _create_client(self, host=None):
        """Create an Ollama client with the given or current host"""
        if not host:
            host = self._get_host()

        if not host:
            raise ValueError("Ollama host configuration is required")

        # Parse and validate URL
        parsed = urlparse(host)
        if not parsed.netloc:
            raise ValueError(f"Invalid host URL: {host}")

        return ollama.AsyncClient(host=host)

    async def load_saved_config(self) -> dict:
        """Load saved configuration for Ollama provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "host": config.llm.ollama.host or "",
            "enabled": config.llm.ollama.enabled,
            "validated": config.llm.ollama.validated,
            "validation_status": config.llm.ollama.validation_status,
            "validation_message": config.llm.ollama.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from ...core.config import save_llm_provider_config, LLMProviderConfig
        from datetime import datetime, timezone

        try:
            # Get and validate host
            host = self._get_host(config)
            if not host:
                return False, "Ollama host configuration is required"

            # Validate first
            valid, message = await self.validate_config(**config)

            # Save configuration
            provider_config = LLMProviderConfig(
                host=host,
                enabled=config.get("enabled", True),
                validated=valid,
                last_validated=datetime.now(timezone.utc) if valid else None,
                validation_status="configured" if valid else "error",
                validation_message=message,
                config_changed=False,
            )

            success = save_llm_provider_config("ollama", provider_config)
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
        return config.llm.ollama.enabled

    @classmethod
    async def set_enabled_static(cls, enabled: bool) -> bool:
        """Enable or disable this provider (class method that doesn't require instance)"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.ollama.enabled = enabled
            if not enabled:
                config.llm.ollama.validation_status = "disabled"
            else:
                # When enabling, set status based on whether we have a valid config
                if config.llm.ollama.validated:
                    config.llm.ollama.validation_status = "configured"
                else:
                    config.llm.ollama.validation_status = "not_validated"
            return save_llm_provider_config("ollama", config.llm.ollama)
        except Exception:
            return False

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider (instance method for compatibility)"""
        return await self.set_enabled_static(enabled)

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

        return new_host != saved_host

    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status"""
        from ...core.config import get_app_config

        config = get_app_config()

        provider_info = self.get_provider_info()
        provider_info.is_available = True
        provider_info.is_enabled = config.llm.ollama.enabled
        provider_info.is_configured = config.llm.ollama.validated

        # Fix status logic - if enabled but no explicit status, check if validated
        if config.llm.ollama.enabled:
            if config.llm.ollama.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.ollama.validation_status or "not_validated"
                provider_info.validation_message = config.llm.ollama.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.ollama.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the Ollama provider"""
        return ProviderInfo(
            id="ollama",
            name="Ollama",
            description="Free and private access to local LLMs when you self-host Ollama. Be aware that small models may not produce usable results.",
            setup_fields=[
                {
                    "name": "host",
                    "type": "text",
                    "label": "Ollama Host URL",
                    "placeholder": "http://localhost:11434",
                    "required": False,
                    "help_url": "https://github.com/ollama/ollama/blob/66fb8575ced090a969c9529c88ee57a8df1259c2/docs/faq.md#how-can-i-expose-ollama-on-my-network",
                }
            ],
            is_available=True,
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the Ollama configuration by trying to list models"""
        # Get host using helper method
        host = self._get_host(config)

        # Host is required
        if not host:
            return False, "Ollama host configuration is required"

        try:
            # Create client using helper method
            client = self._create_client(host)

            # Add 5-second timeout to the validation
            import asyncio

            try:
                await asyncio.wait_for(client.list(), timeout=5.0)
                return True, "Connected successfully"
            except asyncio.TimeoutError:
                logger.error("Ollama Connection timeout after 5 seconds")
                return False, "Connection timeout (5s) - check URL and network"

        except ollama.ResponseError as e:
            logger.error(f"Ollama ResponseError: status={e.status_code}, error={e.error}")
            if e.status_code == 404:
                return False, "Ollama server not found - ensure Ollama is running"
            return False, f"Ollama error: {e.error}"
        except Exception as e:
            logger.error(f"Ollama Validation exception: {type(e).__name__}: {e}", exc_info=True)
            return False, f"Connection failed: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available Ollama models"""
        try:
            # Get host and create client
            host = self._get_host()
            if not host:
                logger.warning("Ollama No host configured, returning empty model list")
                return []

            client = self._create_client(host)
            response = await client.list()

            models = []

            for model in response.get("models", []):
                model_name = model.get("name", model.get("model", ""))
                logger.debug(f"Ollama Processing model: {model}")

                if model_name:
                    # Extract base model name (remove tag if present)
                    display_name = model_name.split(":")[0]

                    # Get model size info if available
                    size_info = ""
                    if "size" in model:
                        size_gb = model["size"] / (1024**3)
                        size_info = f" ({size_gb:.1f}GB)"

                    model_info = ModelInfo(
                        id=model_name,
                        name=f"{display_name.title()}{size_info}",
                        description=f"Local model: {model_name}",
                        supports_streaming=True,
                    )
                    models.append(model_info)
                    logger.debug(f"Ollama Added model: {model_info.name} (id: {model_info.id})")

            # Sort by name for better UX
            models.sort(key=lambda m: m.name.lower())

            return models

        except Exception as e:
            logger.error(f"Failed to get Ollama models: {e}", exc_info=True)
            raise

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
        """Process transcriptions into chapter titles using Ollama"""

        if not transcriptions:
            logger.warning("Ollama No transcriptions provided, returning empty list")
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Loading Ollama model ({model_id}), please wait...")

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
            # Get host and create client
            host = self._get_host()
            if not host:
                raise ValueError("Ollama host configuration is required")

            processing_client = self._create_client(host)

            # Initialize incremental parser for progress tracking
            parser = IncrementalJSONParser()
            total_chapters = len(transcriptions)

            # Stream the response for progress updates
            is_oss_gpt: bool = False
            last_thinking_update = 0
            stream_count = 0
            content_received = ""

            try:
                # Check if model is gpt-oss
                show_response = await processing_client.show(model=model_id)
                is_oss_gpt = show_response.details.family == "gptoss"
            except Exception:
                pass

            # Combine system prompt and user message into single prompt for generate API
            combined_prompt = f"{system_prompt}\n\n{user_message}"

            if is_oss_gpt:
                # Response from gpt-oss models is currently broken when using structured outputs. Seems to work well enough without it.
                format = None
            else:
                format = {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "number"},
                            "title": {"type": ["string", "null"]},
                        },
                        "required": ["id", "title"],
                    },
                }

            async for chunk in await processing_client.generate(
                model=model_id,
                prompt=combined_prompt,
                stream=True,
                format=format,
            ):
                stream_count += 1
                logger.debug(f"Ollama Received chunk {stream_count}: {chunk}")

                if chunk.get("response"):
                    content = chunk["response"]
                    content_received += content
                    logger.debug(f"Ollama Content chunk: '{content}'")

                    result = parser.feed(content)
                    if result["new_chapters"]:
                        progress_percent = result["total_parsed"] / total_chapters * 100
                        self._notify_progress(
                            progress_percent,
                            f"Processed {result['total_parsed']}/{total_chapters} chapters",
                        )
                elif chunk.get("thinking"):
                    current_time = time.time()
                    if current_time - last_thinking_update >= 1.0:  # Limit to once per second
                        self._notify_progress(0, "Thinking...")
                        last_thinking_update = current_time
                    continue

            if not content_received:
                logger.error("Ollama No content received from streaming!")

            self._notify_progress(100, "Processing AI response...")

            # Parse the response
            try:
                processed_chapters = json.loads(content_received)

            except json.JSONDecodeError as e:
                logger.error(f"Ollama Failed to parse Ollama response as JSON: {e}")
                logger.error(f"Ollama Raw response: {content_received}")
                raise

            # Convert to title list
            chapters = [
                None if chapter.get("title") == "null" or chapter.get("title") is None else chapter.get("title")
                for chapter in processed_chapters
            ]

            valid_chapters = len([t for t in chapters if t])

            self._notify_progress(100, f"Generated {valid_chapters} chapter titles")

            return chapters

        except ollama.RequestError as e:
            error_msg = f"Failed to connect to Ollama server - please ensure Ollama is running: {str(e)}"
            logger.error(f"Ollama connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except ollama.ResponseError as e:
            error_msg = f"Ollama server error - check server status: {str(e)}"
            logger.error(f"Ollama response error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse Ollama response - invalid JSON format: {str(e)}"
            logger.error(f"Ollama JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during Ollama processing (model: {model_id}): {str(e)}"
            logger.error(f"Ollama unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
