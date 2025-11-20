import json
import logging
from typing import List, Optional
import httpx
import time

from .base import AIService, ProviderInfo, ModelInfo, IncrementalJSONParser

logger = logging.getLogger(__name__)


class OpenRouterService(AIService):
    """OpenRouter implementation of AIService"""

    def __init__(self, progress_callback, **config):
        super().__init__(progress_callback, **config)

    def _get_api_key(self, config=None):
        """Get the current API key from config or saved configuration"""
        if config and config.get("api_key"):
            return config["api_key"]
        else:
            from ...core.config import get_app_config

            app_config = get_app_config()
            return app_config.llm.openrouter.api_key

    def _create_headers(self, api_key=None):
        """Create headers for OpenRouter API requests"""
        if not api_key:
            api_key = self._get_api_key()

        if not api_key:
            raise ValueError("OpenRouter API key configuration is required")

        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def load_saved_config(self) -> dict:
        """Load saved configuration for OpenRouter provider"""
        from ...core.config import get_app_config

        config = get_app_config()
        return {
            "api_key": config.llm.openrouter.api_key,
            "enabled": config.llm.openrouter.enabled,
            "validated": config.llm.openrouter.validated,
            "validation_status": config.llm.openrouter.validation_status,
            "validation_message": config.llm.openrouter.validation_message,
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

            success = save_llm_provider_config("openrouter", provider_config)
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
        return config.llm.openrouter.enabled

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable this provider"""
        from ...core.config import get_app_config, save_llm_provider_config

        try:
            config = get_app_config()
            config.llm.openrouter.enabled = enabled
            if not enabled:
                config.llm.openrouter.validation_status = "disabled"
            else:
                if config.llm.openrouter.validated and config.llm.openrouter.api_key:
                    config.llm.openrouter.validation_status = "configured"
                else:
                    config.llm.openrouter.validation_status = "not_validated"
            return save_llm_provider_config("openrouter", config.llm.openrouter)
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

        # Compare relevant fields
        return new_config.get("api_key", "") != self._saved_config.get("api_key", "")

    def get_provider_state(self) -> ProviderInfo:
        """Get current provider state including enabled/configured status"""
        from ...core.config import get_app_config

        config = get_app_config()

        provider_info = self.get_provider_info()
        provider_info.is_available = bool(config.llm.openrouter.api_key)
        provider_info.is_enabled = config.llm.openrouter.enabled
        provider_info.is_configured = config.llm.openrouter.validated

        if config.llm.openrouter.enabled:
            if config.llm.openrouter.validated:
                provider_info.validation_status = "configured"
                provider_info.validation_message = "Configured"
            else:
                provider_info.validation_status = config.llm.openrouter.validation_status or "not_validated"
                provider_info.validation_message = config.llm.openrouter.validation_message
        else:
            provider_info.validation_status = "disabled"
            provider_info.validation_message = None

        provider_info.config_changed = config.llm.openrouter.config_changed

        return provider_info

    @classmethod
    def get_provider_info(cls) -> ProviderInfo:
        """Get information about the OpenRouter provider"""
        return ProviderInfo(
            id="openrouter",
            name="OpenRouter",
            description="Requires an OpenRouter account with prepaid credits.",
            setup_fields=[
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "placeholder": "OpenRouter API Key",
                    "required": True,
                    "help_url": "https://openrouter.ai/settings/keys",
                }
            ],
        )

    async def validate_config(self, **config) -> tuple[bool, str]:
        """Validate the OpenRouter configuration"""
        api_key = config.get("api_key")
        if not api_key:
            return False, "API key is required"

        try:
            headers = self._create_headers(api_key)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/key",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return True, "Valid"
                elif response.status_code == 401:
                    return False, "Invalid API key"
                else:
                    return False, f"API error: HTTP {response.status_code}"
                    
        except httpx.TimeoutException:
            return False, "Connection timeout"
        except httpx.ConnectError:
            return False, "Connection failed"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    async def get_available_models(self) -> List[ModelInfo]:
        """Get list of available OpenRouter models"""
        try:
            api_key = self._get_api_key()
            if not api_key:
                return []

            headers = self._create_headers(api_key)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers=headers
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get OpenRouter models: HTTP {response.status_code}")
                    return []

                models_data = response.json()
                models = []

                for model in models_data.get("data", []):
                    model_id = model.get("id", "")
                    model_name = model.get("name", model_id)
                    
                    # Filter models based on modality requirements
                    architecture = model.get("architecture", {})
                    input_modalities = architecture.get("input_modalities", [])
                    output_modalities = architecture.get("output_modalities", [])
                    
                    if ("text" not in input_modalities or
                        output_modalities != ["text"]):
                        continue
                    
                    if any(skip_term in model_id.lower() for skip_term in ["(free)"]):
                        continue
                        
                    context_length = model.get("context_length")
                    description = model.get("description", "")
                    
                    model_info = ModelInfo(
                        id=model_id,
                        name=model_name,
                        description=description,
                        context_length=context_length,
                        supports_streaming=True,
                    )
                    models.append(model_info)

                models.sort(key=lambda model: model.name.lower())
                return models

        except Exception as e:
            logger.error(f"Failed to get OpenRouter models: {e}")
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
        """Process transcriptions into chapter titles using OpenRouter"""

        if not transcriptions:
            return []

        additional_instructions = additional_instructions or []

        self._notify_progress(0, f"Sending request to OpenRouter...")

        system_prompt = self._build_system_prompt(
            deselect_non_chapters=deselect_non_chapters,
            infer_opening_credits=infer_opening_credits,
            infer_end_credits=infer_end_credits,
            preferred_titles=preferred_titles,
            additional_instructions=additional_instructions,
        )

        chapter_data = [{"id": idx, "title": text} for idx, text in enumerate(transcriptions)]

        try:
            api_key = self._get_api_key()
            if not api_key:
                logger.error("OpenRouter API key not configured")
                self._notify_progress(0, "OpenRouter not configured")
                raise ValueError("OpenRouter API key not configured")

            headers = self._create_headers(api_key)

            parser = IncrementalJSONParser()
            total_chapters = len(transcriptions)

            is_thinking_model = any(term in model_id.lower() for term in ["reasoning", "thinking"])

            payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(chapter_data)}
                ],
                "stream": True,
                "response_format": {"type": "json_object"}
            }

            if is_thinking_model:
                payload["reasoning"] = {
                    "max_tokens": 1024
                }

            content_received = ""
            last_thinking_update = 0

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.atext()
                        logger.error(f"OpenRouter API error: {response.status_code} - {error_text}")
                        raise Exception(f"OpenRouter API error: {response.status_code}")

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
                            
                            if "delta" in choice and choice["delta"].get("reasoning"):
                                current_time = time.time()
                                if current_time - last_thinking_update >= 1.0:
                                    self._notify_progress(0, "Thinking...")
                                    last_thinking_update = current_time
                                continue
                                
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

            self._notify_progress(100, "Processing AI response...")

            try:
                response_data = json.loads(content_received)
                
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
                logger.error(f"Failed to parse OpenRouter response: {e}")
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
            error_msg = f"OpenRouter request timeout - the model may be taking longer than expected"
            logger.error(f"OpenRouter timeout error")
            self._notify_progress(0, error_msg)
            raise
        except httpx.HTTPStatusError as e:
            error_msg = f"OpenRouter API error ({e.response.status_code}): {str(e)}"
            logger.error(f"OpenRouter HTTP error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except httpx.RequestError as e:
            error_msg = f"Failed to connect to OpenRouter - please check your internet connection: {str(e)}"
            logger.error(f"OpenRouter connection error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse OpenRouter response - invalid JSON format: {str(e)}"
            logger.error(f"OpenRouter JSON decode error: {e}")
            self._notify_progress(0, error_msg)
            raise
        except Exception as e:
            error_msg = f"Unexpected error during OpenRouter processing (model: {model_id}): {str(e)}"
            logger.error(f"OpenRouter unexpected error: {e}", exc_info=True)
            self._notify_progress(0, error_msg)
            raise