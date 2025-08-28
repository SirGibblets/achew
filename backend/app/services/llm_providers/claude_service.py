import anthropic
import json
import logging
from typing import List, Optional

from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser

logger = logging.getLogger(__name__)


class ClaudeService(AIService):
    """Anthropic Claude implementation of AIService"""

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
            return app_config.llm.claude.api_key

    def _create_client(self, api_key=None):
        """Create a Claude client with the given or current API key"""
        if not api_key:
            api_key = self._get_api_key()

        if not api_key:
            raise ValueError("Claude API key configuration is required")

        return anthropic.AsyncAnthropic(api_key=api_key)

    async def load_saved_config(self) -> dict:
        """Load saved configuration for Claude provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "api_key": config.llm.claude.api_key or "",
            "enabled": config.llm.claude.enabled,
            "validated": config.llm.claude.validated,
            "validation_status": config.llm.claude.validation_status,
            "validation_message": config.llm.claude.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from ...core.config import save_llm_provider_config, LLMProviderConfig
        from datetime import datetime, timezone

        try:
            # Get and validate API key
            api_key = self._get_api_key(config)
            if not api_key:
                return False, "Claude API key configuration is required"

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

            success = save_llm_provider_config("claude", provider_config)
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
        return config.llm.claude.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.claude.enabled = enabled
            if not enabled:
                config.llm.claude.validation_status = "disabled"
            else:
                # When enabling, set status based on whether we have a valid config
                if config.llm.claude.validated and config.llm.claude.api_key:
                    config.llm.claude.validation_status = "configured"
                else:
                    config.llm.claude.validation_status = "not_validated"
            return save_llm_provider_config("claude", config.llm.claude)
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
        provider_info.is_enabled = config.llm.claude.enabled
        provider_info.is_configured = config.llm.claude.validated

        # Fix status logic - if enabled but no explicit status, check if validated
        if config.llm.claude.enabled:
            if config.llm.claude.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.claude.validation_status or "not_validated"
                provider_info.validation_message = config.llm.claude.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.claude.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the Claude provider"""
        return ProviderInfo(
            id="claude",
            name="Claude",
            description="Requires an Anthropic account with prepaid credits.",
            setup_fields=[
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "placeholder": "Claude API Key",
                    "required": True,
                    "help_url": "https://console.anthropic.com/settings/keys",
                }
            ],
            is_available=True,
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the Claude configuration by trying to list models"""
        # Get API key using helper method
        api_key = self._get_api_key(config)

        # API key is required
        if not api_key:
            return False, "Claude API key configuration is required"

        try:
            # Create client using helper method
            client = self._create_client(api_key)

            # Test the API key with a simple request
            await client.models.list(limit=1)
            return True, "Connected successfully"

        except Exception as e:
            logger.error(f"Claude Validation exception: {type(e).__name__}: {e}", exc_info=True)
            if "authentication" in str(e).lower() or "invalid" in str(e).lower():
                return False, "Invalid API key"
            elif "quota" in str(e).lower() or "billing" in str(e).lower():
                return False, "API quota exceeded or billing issue"
            return False, f"Connection failed: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available Claude models"""
        try:
            # Get API key and create client
            api_key = self._get_api_key()
            if not api_key:
                logger.warning("Claude No API key configured, returning empty model list")
                return []

            client = self._create_client(api_key)
            models_response = await client.models.list(limit=100)

            models = []

            for model in models_response.data:
                logger.debug(f"Claude Processing model: {model.id}")

                if "claude" in model.id:
                    display_name = model.display_name or model.id.replace("-", " ").title()
                    model_info = ModelInfo(
                        id=model.id,
                        name=display_name,
                        description=f"Claude model: {model.id}",
                        supports_streaming=True,
                    )
                    models.append(model_info)
                    logger.debug(f"Claude Added model: {model_info.name} (id: {model_info.id})")

            # Sort by preference (claude-3-5-sonnet first, then others)
            def sort_key(model):
                if "claude-3-5-sonnet" in model.id:
                    return 0
                else:
                    return 1

            models.sort(key=sort_key)

            return models

        except Exception as e:
            logger.error(f"Failed to get Claude models: {e}", exc_info=True)
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
        """Process transcriptions into chapter titles using Claude"""

        if not transcriptions:
            logger.warning("Claude No transcriptions provided, returning empty list")
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Sending request to Claude...")

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
                raise ValueError("Claude API key configuration is required")

            processing_client = self._create_client(api_key)

            # Initialize incremental parser for progress tracking
            parser = IncrementalJSONParser()
            total_chapters = len(transcriptions)

            # Stream the response for progress updates
            content_received = ""

            async with processing_client.messages.stream(
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
                model=model_id,
                max_tokens=4096,
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        content_received += text
                        logger.debug(f"Claude Content chunk: '{text}'")

                        result = parser.feed(text)
                        if result["new_chapters"]:
                            progress_percent = result["total_parsed"] / total_chapters * 100
                            self._notify_progress(
                                progress_percent,
                                f"Processed {result['total_parsed']}/{total_chapters} chapters",
                            )

            if not content_received:
                logger.error("Claude No content received from streaming!")

            self._notify_progress(100, "Processing AI response...")

            # Parse the response
            try:
                processed_chapters = json.loads(content_received)

            except json.JSONDecodeError as e:
                logger.error(f"Claude Failed to parse Claude response as JSON: {e}")
                logger.error(f"Claude Raw response: {content_received}")
                raise

            # Convert to title list
            chapters = [
                None if chapter.get("title") == "null" or chapter.get("title") is None else chapter.get("title")
                for chapter in processed_chapters
            ]

            valid_chapters = len([t for t in chapters if t])

            self._notify_progress(100, f"Generated {valid_chapters} chapter titles")

            return chapters

        except anthropic.AuthenticationError as e:
            error_msg = f"Claude authentication failed - please check your API key: {str(e)}"
            logger.error(f"Claude authentication error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except anthropic.RateLimitError as e:
            error_msg = f"Claude rate limit exceeded - please wait and try again: {str(e)}"
            logger.error(f"Claude rate limit error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except anthropic.APIConnectionError as e:
            error_msg = f"Failed to connect to Claude - please check your internet connection: {str(e)}"
            logger.error(f"Claude connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except anthropic.APIError as e:
            error_msg = f"Claude API error ({e.status_code if hasattr(e, 'status_code') else 'unknown'}): {str(e)}"
            logger.error(f"Claude API error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse Claude response - invalid JSON format: {str(e)}"
            logger.error(f"Claude JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during Claude processing (model: {model_id}): {str(e)}"
            logger.error(f"Claude unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
