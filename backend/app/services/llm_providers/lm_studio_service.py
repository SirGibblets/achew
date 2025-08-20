import json
import logging
import time
import asyncio
from typing import List, Optional
from lmstudio import AsyncClient

from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser

logger = logging.getLogger(__name__)


class LMStudioService(AIService):
    """LM Studio implementation of AIService for local models"""

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
            host = app_config.llm.lm_studio.host

        if not host:
            return None

        # Ensure host has proper format (default port for LM Studio is 1234)
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"

        return host

    def _create_client(self, host=None):
        """Create an LM Studio client with the given or current host"""
        if not host:
            host = self._get_host()

        if not host:
            raise ValueError("LM Studio host configuration is required")

        # Remove http:// or https:// prefix for LM Studio client
        if host.startswith("http://"):
            host = host[7:]
        elif host.startswith("https://"):
            host = host[8:]

        return AsyncClient(host)

    async def load_saved_config(self) -> dict:
        """Load saved configuration for LM Studio provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "host": config.llm.lm_studio.host or "",
            "enabled": config.llm.lm_studio.enabled,
            "validated": config.llm.lm_studio.validated,
            "validation_status": config.llm.lm_studio.validation_status,
            "validation_message": config.llm.lm_studio.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from ...core.config import save_llm_provider_config, LLMProviderConfig
        from datetime import datetime, timezone

        try:
            # Get and validate host
            host = self._get_host(config)
            if not host:
                return False, "LM Studio host configuration is required"

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

    @classmethod
    async def set_enabled_static(cls, enabled: bool) -> bool:
        """Enable or disable this provider (class method that doesn't require instance)"""
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

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider (instance method for compatibility)"""
        return await self.set_enabled_static(enabled)

    def has_config_changed(self, **new_config) -> bool:
        """Check if configuration has changed from saved state"""
        if not self._saved_config:
            # Load saved config if not cached
            try:
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
                    "label": "LM Studio Host URL",
                    "placeholder": "localhost:1234",
                    "required": False,
                    "help_url": "https://lmstudio.ai/docs/app/api",
                }
            ],
            is_available=True,
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the LM Studio configuration by trying to list models"""
        # Get host using helper method
        host = self._get_host(config)

        # Host is required
        if not host:
            return False, "LM Studio host configuration is required"

        try:
            # Create client using helper method
            async with self._create_client(host) as client:
                # Add 5-second timeout to the validation
                try:
                    await asyncio.wait_for(client.llm.list_downloaded(), timeout=5.0)
                    return True, "Connected successfully"
                except asyncio.TimeoutError:
                    logger.error("LM Studio Connection timeout after 5 seconds")
                    return False, "Connection timeout (5s) - check URL and network"

        except Exception as e:
            logger.error(f"LM Studio Validation exception: {type(e).__name__}: {e}", exc_info=True)
            return False, f"Connection failed: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available LM Studio models"""
        try:
            # Get host and create client
            host = self._get_host()
            if not host:
                logger.warning("LM Studio No host configured, returning empty model list")
                return []

            async with self._create_client(host) as client:
                models = await client.llm.list_downloaded()

                model_list = []

                for model in models:
                    logger.debug(f"LM Studio Processing model: {model}")

                    try:
                        model_info = model.info
                        model_key = model_info.model_key
                        display_name = model_info.display_name

                        if model_key and display_name:
                            # Get model size info if available
                            size_info = ""
                            if model_info.size_bytes:
                                size_gb = model_info.size_bytes / (1024**3)
                                size_info = f" ({size_gb:.1f}GB)"

                            description = f"Local model: {model_key}"
                            if model_info.architecture:
                                description += f" ({model_info.architecture})"

                            model_info_obj = ModelInfo(
                                id=model_key,
                                name=f"{display_name}{size_info}",
                                description=description,
                                supports_streaming=True,
                            )
                            model_list.append(model_info_obj)
                            logger.debug(f"LM Studio Added model: {model_info_obj.name} (id: {model_info_obj.id})")
                        else:
                            logger.warning(
                                f"LM Studio model missing required attributes: model_key={model_key}, display_name={display_name}"
                            )
                    except Exception as e:
                        logger.error(f"Error processing LM Studio model {model}: {e}")
                        continue

                # Sort by name for better UX
                model_list.sort(key=lambda m: m.name.lower())

                return model_list

        except Exception as e:
            logger.error(f"Failed to get LM Studio models: {e}", exc_info=True)
            return []

    async def process_chapter_titles(
        self,
        transcriptions: List[str],
        model_id: str,
        additional_instructions: List[str] = None,
        keep_all_chapters: bool = False,
        infer_opening_credits: bool = True,
        infer_end_credits: bool = True,
        preferred_titles: List[str] = None,
    ) -> List[Optional[str]]:
        """Process transcriptions into chapter titles using LM Studio"""

        if not transcriptions:
            logger.warning("LM Studio No transcriptions provided, returning empty list")
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Loading LM Studio model ({model_id}), please wait...")

        # Build system prompt dynamically based on options
        system_prompt = self._build_system_prompt(
            keep_all_chapters=keep_all_chapters,
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
                raise ValueError("LM Studio host configuration is required")

            async with self._create_client(host) as client:
                # Load the model
                model = await client.llm.model(model_id)
                model_info = await model.get_info()

                is_gpt_oss = model_info.architecture == "gpt-oss"

                # Initialize incremental parser for progress tracking
                parser = IncrementalJSONParser()
                total_chapters = len(transcriptions)

                # Stream the response for progress updates
                stream_count = 0
                content_received = ""
                last_thinking_update = 0

                # Combine system prompt and user message
                combined_prompt = f"{system_prompt}\n\n{user_message}"

                logger.info(f"LM Studio Combined prompt:\n{combined_prompt}")

                if is_gpt_oss:
                    # Response from gpt-oss models is currently broken when using structured outputs. Seems to work well enough without it.
                    response_format = None
                else:
                    response_format = {
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

                async for chunk in await model.respond_stream(combined_prompt, response_format=response_format):
                    stream_count += 1
                    logger.debug(f"LM Studio Received chunk {stream_count}: {chunk}")

                    # Handle thinking mode for models that support it
                    if hasattr(chunk, "reasoning_type") and chunk.reasoning_type != "none":
                        current_time = time.time()
                        if current_time - last_thinking_update >= 1.0:  # Limit to once per second
                            self._notify_progress(0, "Thinking...")
                            last_thinking_update = current_time
                        continue

                    if hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        content_received += content
                        logger.debug(f"LM Studio Content chunk: '{content}'")

                        result = parser.feed(content)
                        if result["new_chapters"]:
                            progress_percent = result["total_parsed"] / total_chapters * 100
                            self._notify_progress(
                                progress_percent,
                                f"Processed {result['total_parsed']}/{total_chapters} chapters",
                            )

                if not content_received:
                    logger.error("LM Studio No content received from streaming!")

                self._notify_progress(100, "Processing AI response...")

                # Parse the response
                try:
                    try:
                        if is_gpt_oss:
                            # For gpt-oss, take only content after "<|message|>"
                            # Ideally this would be handled by LM Studio or with openai-harmony
                            if "<|message|>" in content_received:
                                content_received = content_received.split("<|message|>")[-1]
                    except Exception as e:
                        logger.debug(f"Could not get model info for architecture check: {e}")

                    processed_chapters = json.loads(content_received)

                except json.JSONDecodeError as e:
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

        except asyncio.TimeoutError as e:
            error_msg = f"LM Studio request timed out - server may be overloaded: {str(e)}"
            logger.error(f"LM Studio timeout error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except ConnectionError as e:
            error_msg = f"Failed to connect to LM Studio - please ensure LM Studio is running and accessible: {str(e)}"
            logger.error(f"LM Studio connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except OSError as e:
            error_msg = f"Network error connecting to LM Studio - check host and port: {str(e)}"
            logger.error(f"LM Studio network error: {e}")
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
