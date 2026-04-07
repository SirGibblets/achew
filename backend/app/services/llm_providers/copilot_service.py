import asyncio
import json
import logging
import re
from typing import List, Optional

from copilot import CopilotClient, SubprocessConfig
from copilot.session import PermissionHandler

from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser

logger = logging.getLogger(__name__)


class CopilotService(AIService):
    """GitHub Copilot implementation of AIService"""

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

    def _get_github_token(self, config=None):
        """Get the current GitHub token from config or saved configuration"""
        if config and config.get("api_key"):
            return config["api_key"]
        else:
            from ...core.config import get_app_config

            app_config = get_app_config()
            return app_config.llm.copilot.api_key

    def _create_client(self, github_token=None):
        """Create a CopilotClient with the given or saved GitHub token"""
        if not github_token:
            github_token = self._get_github_token()

        if not github_token:
            raise ValueError("GitHub token is required")

        return CopilotClient(SubprocessConfig(github_token=github_token))

    async def load_saved_config(self) -> dict:
        """Load saved configuration for Copilot provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "api_key": config.llm.copilot.api_key,
            "enabled": config.llm.copilot.enabled,
            "validated": config.llm.copilot.validated,
            "validation_status": config.llm.copilot.validation_status,
            "validation_message": config.llm.copilot.validation_message,
        }

    async def save_config(self, **config) -> tuple[bool, str]:
        """Save configuration after successful validation"""
        from ...core.config import save_llm_provider_config, LLMProviderConfig
        from datetime import datetime, timezone

        try:
            valid, message = await self.validate_config(**config)

            provider_config = LLMProviderConfig(
                api_key=config.get("api_key", ""),
                enabled=config.get("enabled", True),
                validated=valid,
                last_validated=datetime.now(timezone.utc) if valid else None,
                validation_status="configured" if valid else "error",
                validation_message=message,
                config_changed=False,
            )

            success = save_llm_provider_config("copilot", provider_config)
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
        return config.llm.copilot.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.copilot.enabled = enabled
            if not enabled:
                config.llm.copilot.validation_status = "disabled"
            else:
                if config.llm.copilot.validated and config.llm.copilot.api_key:
                    config.llm.copilot.validation_status = "configured"
                else:
                    config.llm.copilot.validation_status = "not_validated"
            return save_llm_provider_config("copilot", config.llm.copilot)
        except Exception:
            return False

    def has_config_changed(self, **new_config) -> bool:
        """Check if configuration has changed from saved state"""
        if not self._saved_config:
            try:
                import asyncio

                saved = asyncio.run(self.load_saved_config())
                self._saved_config = saved
            except Exception:
                return True

        return new_config.get("api_key", "") != self._saved_config.get("api_key", "")

    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status"""
        from ...core.config import get_app_config

        config = get_app_config()

        provider_info = self.get_provider_info()
        provider_info.is_available = bool(config.llm.copilot.api_key)
        provider_info.is_enabled = config.llm.copilot.enabled
        provider_info.is_configured = config.llm.copilot.validated

        if config.llm.copilot.enabled:
            if config.llm.copilot.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.copilot.validation_status or "not_validated"
                provider_info.validation_message = config.llm.copilot.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.copilot.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the GitHub Copilot provider"""
        return ProviderInfo(
            id="copilot",
            name="GitHub Copilot",
            description="Requires a GitHub account with Copilot access (free or paid).",
            instructions="Create and use a <em>fine-grained</em> personal access token with the <b>Copilot Requests</b> permission.",
            setup_fields=[
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "GitHub Token",
                    "placeholder": "Personal Access Token",
                    "required": True,
                    "help_url": "https://github.com/settings/personal-access-tokens/new",
                }
            ],
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the GitHub Copilot configuration"""
        github_token = config.get("api_key")
        if not github_token:
            return False, "GitHub token is required"

        try:
            client = self._create_client(github_token)
            async with client:
                try:
                    models = await client.list_models()
                    if not models:
                        return False, "Unable to validate. Ensure GitHub Copilot is enabled on your account."
                except Exception as e:
                    error_str = str(e)
                    if "403" in error_str or "unauthorized" in error_str.lower():
                        return False, "Not authorized for GitHub Copilot. Ensure Copilot is enabled on your account."
                    raise
                return True, "Valid"
        except Exception as e:
            logger.error(f"Copilot validation failed: {type(e).__name__}: {e}", exc_info=True)
            return False, f"Validation failed: {type(e).__name__}: {e}"

    """
    Known Copilot models to use as a fallback when the models.list API
    is unavailable (returns 403 with fine-grained PATs).
    """
    KNOWN_MODELS = [
        ModelInfo(id="gpt-4o", name="GPT-4o", supports_streaming=True),
        ModelInfo(id="gpt-4.1", name="GPT-4.1", supports_streaming=True),
        ModelInfo(id="gpt-5-mini", name="GPT-5 mini", supports_streaming=True),
        ModelInfo(id="gpt-5.1", name="GPT-5.1", supports_streaming=True),
        ModelInfo(id="gpt-5.2", name="GPT-5.2", supports_streaming=True),
        ModelInfo(id="claude-sonnet-4", name="Claude Sonnet 4", supports_streaming=True),
        ModelInfo(id="claude-sonnet-4.5", name="Claude Sonnet 4.5", supports_streaming=True),
        ModelInfo(id="claude-haiku-4.5", name="Claude Haiku 4.5", supports_streaming=True),
        ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro", supports_streaming=True),
    ]

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available Copilot models, falling back to known models if list_models() fails"""
        github_token = self._get_github_token()
        if not github_token:
            return []

        try:
            client = self._create_client(github_token)
            async with client:
                models = await client.list_models()
                model_list = []

                for model in models:
                    if isinstance(model, str):
                        model_id = model
                        model_name = model
                        context_length = None
                    elif isinstance(model, dict):
                        model_id = model.get("id", str(model))
                        model_name = model.get("name", model_id)
                        context_length = None
                    elif hasattr(model, "id"):
                        model_id = model.id
                        model_name = getattr(model, "name", model_id)
                        context_length = None
                        caps = getattr(model, "capabilities", None)
                        if caps:
                            limits = getattr(caps, "limits", None)
                            if limits:
                                context_length = getattr(limits, "max_context_window_tokens", None)
                    else:
                        model_id = str(model)
                        model_name = model_id
                        context_length = None

                    model_list.append(
                        ModelInfo(
                            id=model_id,
                            name=model_name,
                            context_length=context_length,
                            supports_streaming=True,
                        )
                    )

                if model_list:
                    model_list.sort(key=lambda m: m.name.lower())
                    return model_list

        except Exception as e:
            logger.warning(f"Copilot list_models() unavailable, using fallback model list: {e}")

        return list(self.KNOWN_MODELS)

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
        """Process transcriptions into chapter titles using GitHub Copilot"""

        if not transcriptions:
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, "Sending request to GitHub Copilot…")

        system_prompt = self._build_system_prompt(
            deselect_non_chapters=deselect_non_chapters,
            infer_opening_credits=infer_opening_credits,
            infer_end_credits=infer_end_credits,
            preferred_titles=preferred_titles,
            additional_instructions=additional_instructions,
        )

        chapter_data = [{"id": idx, "title": text} for idx, text in enumerate(transcriptions)]

        try:
            github_token = self._get_github_token()
            if not github_token:
                logger.error("GitHub token not configured")
                self._notify_progress(0, "GitHub Copilot not configured")
                raise ValueError("GitHub token not configured")

            parser = IncrementalJSONParser()
            total_chapters = len(transcriptions)

            content_received = ""
            done = asyncio.Event()

            def on_event(event):
                nonlocal content_received
                match event.type.value:
                    case "assistant.message_delta":
                        delta = event.data.delta_content or ""
                        if delta:
                            content_received += delta
                            result = parser.feed(delta)
                            if result["new_chapters"]:
                                progress = result["total_parsed"] / total_chapters * 100
                                self._notify_progress(
                                    progress,
                                    f"Processed {result['total_parsed']}/{total_chapters} chapters",
                                )
                    case "session.idle":
                        done.set()

            client = self._create_client(github_token)
            async with client:
                async with await client.create_session(
                    on_permission_request=PermissionHandler.approve_all,
                    model=model_id,
                    streaming=True,
                ) as session:
                    session.on(on_event)

                    message = f"{system_prompt}\n\n{json.dumps(chapter_data)}"
                    await session.send(message)

                    try:
                        await asyncio.wait_for(done.wait(), timeout=60.0)
                    except asyncio.TimeoutError:
                        raise TimeoutError("Copilot request timed out after 60 seconds")

            self._notify_progress(100, "Processing AI response…")

            # Strip markdown code block wrapping (```json ... ```) that may have been added
            stripped = content_received.strip()
            match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
            if match:
                stripped = match.group(1).strip()

            try:
                response_data = json.loads(stripped)

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
                logger.error(f"Failed to parse Copilot response: {e}")
                logger.error(f"Raw response: {content_received!r}")
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

        except TimeoutError:
            error_msg = "Copilot request timeout - the model may be taking longer than expected"
            logger.error(error_msg)
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse Copilot response - invalid JSON format: {str(e)}"
            logger.error(f"Copilot JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during Copilot processing (model: {model_id}): {str(e)}"
            logger.error(f"Copilot unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise
