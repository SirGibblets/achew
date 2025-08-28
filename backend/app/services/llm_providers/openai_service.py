import json
import logging
from typing import List, Optional

import openai
from openai.types.responses import ParsedResponse, EasyInputMessageParam

from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser, ChapterList

logger = logging.getLogger(__name__)


class OpenAIService(AIService):
    """OpenAI implementation of AIService"""

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

        # Do not create client here - defer until needed like other services
        # This allows safe instantiation for config/state purposes

    def _get_api_key(self, config=None):
        """Get the current API key from config or saved configuration"""
        # First try from passed config
        if config and config.get("api_key"):
            return config["api_key"]
        else:
            # Load from saved configuration
            from ...core.config import get_app_config

            app_config = get_app_config()
            return app_config.llm.openai.api_key

    def _create_client(self, api_key=None):
        """Create an OpenAI client with the given or current API key"""
        if not api_key:
            api_key = self._get_api_key()

        if not api_key:
            raise ValueError("OpenAI API key configuration is required")

        return openai.AsyncOpenAI(api_key=api_key)

    async def load_saved_config(self) -> dict:
        """Load saved configuration for OpenAI provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "api_key": config.llm.openai.api_key,
            "enabled": config.llm.openai.enabled,
            "validated": config.llm.openai.validated,
            "validation_status": config.llm.openai.validation_status,
            "validation_message": config.llm.openai.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from ...core.config import save_llm_provider_config, LLMProviderConfig
        from datetime import datetime, timezone

        try:
            # Validate first
            valid, message = await self.validate_config(**config)

            # Save configuration
            provider_config = LLMProviderConfig(
                api_key=config.get("api_key", ""),
                enabled=config.get("enabled", True),
                validated=valid,
                last_validated=datetime.now(timezone.utc) if valid else None,
                validation_status="configured" if valid else "error",
                validation_message=message,
                config_changed=False,
            )

            success = save_llm_provider_config("openai", provider_config)
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
        return config.llm.openai.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.openai.enabled = enabled
            if not enabled:
                config.llm.openai.validation_status = "disabled"
            else:
                # When enabling, set status based on whether we have a valid config
                if config.llm.openai.validated and config.llm.openai.api_key:
                    config.llm.openai.validation_status = "configured"
                else:
                    config.llm.openai.validation_status = "not_validated"
            return save_llm_provider_config("openai", config.llm.openai)
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
        provider_info.is_available = bool(config.llm.openai.api_key)
        provider_info.is_enabled = config.llm.openai.enabled
        provider_info.is_configured = config.llm.openai.validated

        # Fix status logic - if enabled but no explicit status, check if validated
        if config.llm.openai.enabled:
            if config.llm.openai.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.openai.validation_status or "not_validated"
                provider_info.validation_message = config.llm.openai.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.openai.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the OpenAI provider"""
        return ProviderInfo(
            id="openai",
            name="OpenAI",
            description="Requires an OpenAI account with prepaid API credits.",
            setup_fields=[
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "placeholder": "OpenAI API Key",
                    "required": True,
                    "help_url": "https://platform.openai.com/api-keys",
                }
            ],
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the OpenAI configuration"""
        api_key = config.get("api_key")
        if not api_key:
            return False, "API key is required"

        try:
            # Test the API key with a simple request
            client = openai.AsyncOpenAI(api_key=api_key)
            await client.models.list()
            return True, "Valid"
        except openai.AuthenticationError:
            return False, "Invalid API key"
        except openai.APIError as e:
            return False, f"API error: {str(e)}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available OpenAI models"""
        try:
            client = self._create_client()
        except ValueError:
            return []

        try:
            models_response = await client.models.list()
            gpt_models = []

            # Filter for GPT models that support chat completions
            for model in models_response.data:
                if "gpt" in model.id.lower() and not model.id.startswith("gpt-3.5-turbo-instruct"):
                    # Map common models to user-friendly info
                    if model.id == "gpt-4o":
                        gpt_models.append(
                            ModelInfo(
                                id=model.id,
                                name="GPT-4o",
                                description="Most capable model, best for complex reasoning",
                                context_length=128000,
                                supports_streaming=True,
                            )
                        )
                    elif model.id == "gpt-4o-mini":
                        gpt_models.append(
                            ModelInfo(
                                id=model.id,
                                name="GPT-4o Mini",
                                description="Fast and efficient, good for most tasks",
                                context_length=128000,
                                supports_streaming=True,
                            )
                        )
                    elif model.id.startswith("gpt-4"):
                        gpt_models.append(
                            ModelInfo(
                                id=model.id,
                                name=model.id.upper(),
                                description="Advanced reasoning capabilities",
                                context_length=8192 if "32k" not in model.id else 32768,
                                supports_streaming=True,
                            )
                        )
                    elif model.id.startswith("gpt-3.5"):
                        gpt_models.append(
                            ModelInfo(
                                id=model.id,
                                name=model.id.upper(),
                                description="Fast and cost-effective",
                                context_length=4096 if "16k" not in model.id else 16384,
                                supports_streaming=True,
                            )
                        )

            # Sort by preference (gpt-4o first, then others)
            def sort_key(model):
                if model.id == "gpt-4o":
                    return 0
                elif model.id == "gpt-4o-mini":
                    return 1
                elif model.id.startswith("gpt-4"):
                    return 2
                else:
                    return 3

            gpt_models.sort(key=sort_key)
            return gpt_models

        except Exception as e:
            logger.error(f"Failed to get OpenAI models: {e}")
            # Return default models as fallback
            return [
                ModelInfo(
                    id="gpt-4o",
                    name="GPT-4o",
                    description="Most capable model (fallback)",
                    context_length=128000,
                    supports_streaming=True,
                ),
                ModelInfo(
                    id="gpt-4o-mini",
                    name="GPT-4o Mini",
                    description="Fast and efficient (fallback)",
                    context_length=128000,
                    supports_streaming=True,
                ),
            ]

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
        """Process transcriptions into chapter titles using OpenAI"""

        if not transcriptions:
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Sending request to OpenAI...")

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

        try:
            client = self._create_client()
        except ValueError as e:
            logger.error(f"OpenAI client not configured: {e}")
            self._notify_progress(0, "OpenAI not configured")
            raise

        try:
            # Use structured output parsing
            system_message = EasyInputMessageParam(role="system", content=system_prompt)
            user_message = EasyInputMessageParam(role="user", content=json.dumps(chapter_data))

            # Initialize incremental parser for progress tracking
            parser = IncrementalJSONParser()
            total_chapters = len(transcriptions)

            async with client.responses.stream(
                model=model_id,
                input=[system_message, user_message],
                text_format=ChapterList,
            ) as stream:
                async for event in stream:
                    if event.type == "response.created":
                        self._notify_progress(0, "Awaiting response...")
                    elif event.type == "response.output_text.delta":
                        result = parser.feed(event.delta)
                        if result["new_chapters"]:
                            progress_percent = result["total_parsed"] / total_chapters * 100
                            self._notify_progress(
                                progress_percent,
                                f"Processed {result['total_parsed']}/{total_chapters} chapters",
                            )

                final_response: ParsedResponse[ChapterList] = await stream.get_final_response()
                processed_chapters = final_response.output_parsed.chapters

            self._notify_progress(100, "Processing AI response...")

            # Parse the response
            chapters = [None if chapter.title == "null" else chapter.title for chapter in processed_chapters]

            self._notify_progress(100, f"Generated {len([t for t in chapters if t])} chapter titles")

            return chapters

        except openai.AuthenticationError as e:
            error_msg = f"OpenAI authentication failed - please check your API key: {str(e)}"
            logger.error(f"OpenAI authentication error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except openai.RateLimitError as e:
            error_msg = f"OpenAI rate limit exceeded - please wait and try again: {str(e)}"
            logger.error(f"OpenAI rate limit error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except openai.APIConnectionError as e:
            error_msg = f"Failed to connect to OpenAI - please check your internet connection: {str(e)}"
            logger.error(f"OpenAI connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except openai.APIError as e:
            error_msg = f"OpenAI API error ({e.status_code if hasattr(e, 'status_code') else 'unknown'}): {str(e)}"
            logger.error(f"OpenAI API error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse OpenAI response - invalid JSON format: {str(e)}"
            logger.error(f"OpenAI JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during OpenAI processing (model: {model_id}): {str(e)}"
            logger.error(f"OpenAI unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
