import logging
from typing import Dict, List, Optional, Type
from .base import AIService, ProviderInfo, ModelInfo
from .openai_service import OpenAIService
from .ollama_service import OllamaService
from .gemini_service import GeminiService
from .claude_service import ClaudeService
from .lm_studio_service import LMStudioService
from .openrouter_service import OpenRouterService

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry for LLM providers"""

    def __init__(self):
        self._providers: Dict[str, Type[AIService]] = {}
        self._register_builtin_providers()

    def _register_builtin_providers(self):
        """Register built-in providers"""
        self.register_provider(OpenAIService)
        self.register_provider(ClaudeService)
        self.register_provider(GeminiService)
        self.register_provider(OpenRouterService)
        self.register_provider(OllamaService)
        self.register_provider(LMStudioService)

    def register_provider(self, provider_class: Type[AIService]):
        """Register a new provider"""
        if not issubclass(provider_class, AIService):
            raise ValueError(f"{provider_class} must inherit from AIService")

        provider_info = provider_class.get_provider_info()
        self._providers[provider_info.id] = provider_class
        logger.info(f"Registered LLM provider: {provider_info.name} ({provider_info.id})")

    def get_provider_class(self, provider_id: str) -> Optional[Type[AIService]]:
        """Get a provider class by ID"""
        return self._providers.get(provider_id)

    def get_all_providers(self) -> List[ProviderInfo]:
        """Get information about all registered providers"""
        providers = []
        for provider_class in self._providers.values():
            try:
                provider_info = provider_class.get_provider_info()
                providers.append(provider_info)
            except Exception as e:
                logger.error(f"Failed to get provider info for {provider_class}: {e}")

        return providers

    def create_provider(self, provider_id: str, progress_callback, **config) -> Optional[AIService]:
        """Create an instance of a provider"""
        provider_class = self.get_provider_class(provider_id)
        if not provider_class:
            logger.error(f"Unknown provider: {provider_id}")
            return None

        try:
            return provider_class(progress_callback, **config)
        except Exception as e:
            logger.error(f"Failed to create provider {provider_id}: {e}")
            return None

    async def get_provider_states(self) -> List[ProviderInfo]:
        """Get current state of all providers"""
        states = []
        for provider_class in self._providers.values():
            try:
                # Create a temporary instance to get state (no config needed now)
                provider = provider_class(lambda *args: None)
                state = provider.get_provider_state()
                states.append(state)
            except Exception as e:
                logger.error(f"Failed to get state for provider {provider_class}: {e}")
                # Return basic info if we can't get full state
                try:
                    info = provider_class.get_provider_info()
                    info.validation_status = "error"
                    info.validation_message = f"Failed to get state: {str(e)}"
                    states.append(info)
                except Exception:
                    pass

        return states

    async def validate_provider_config(self, provider_id: str, **config) -> tuple[bool, str]:
        """Validate configuration for a specific provider and auto-save if successful"""
        provider_class = self.get_provider_class(provider_id)
        if not provider_class:
            return False, f"Unknown provider: {provider_id}"

        try:
            provider = provider_class(lambda *args: None, **config)
            valid, message = await provider.validate_config(**config)

            # If validation succeeds, automatically save the configuration
            if valid:
                try:
                    save_success, save_message = await provider.save_config(**config)
                    if not save_success:
                        logger.warning(f"Validation succeeded but save failed for {provider_id}: {save_message}")
                        # Still return validation success since the config is valid
                        return True, f"Valid (save warning: {save_message})"
                except Exception as save_error:
                    logger.error(f"Failed to auto-save config for {provider_id}: {save_error}")
                    # Still return validation success since the config is valid
                    return True, f"Valid (save failed: {str(save_error)})"

            return valid, message

        except Exception as e:
            logger.error(f"Failed to validate provider {provider_id}: {e}")
            return False, f"Validation error: {str(e)}"

    async def save_provider_config(self, provider_id: str, **config) -> tuple[bool, str]:
        """Save configuration for a specific provider"""
        provider_class = self.get_provider_class(provider_id)
        if not provider_class:
            return False, f"Unknown provider: {provider_id}"

        try:
            provider = provider_class(lambda *args: None, **config)
            return await provider.save_config(**config)
        except Exception as e:
            logger.error(f"Failed to save config for provider {provider_id}: {e}")
            return False, f"Save error: {str(e)}"

    async def set_provider_enabled(self, provider_id: str, enabled: bool) -> bool:
        """Enable or disable a specific provider"""
        provider_class = self.get_provider_class(provider_id)
        if not provider_class:
            return False

        try:
            provider = provider_class(lambda *args: None)
            return await provider.set_enabled(enabled)
        except Exception as e:
            logger.error(f"Failed to set enabled state for provider {provider_id}: {e}")
            return False

    async def get_provider_models(self, provider_id: str, **config) -> List[ModelInfo]:
        """Get available models for a provider"""
        try:
            provider = self.create_provider(provider_id, lambda *args: None, **config)
            if provider:
                return await provider.get_available_models()
            return []
        except Exception as e:
            logger.error(f"Failed to get models for provider {provider_id}: {e}")
            return []


# Global registry instance
_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get the global provider registry"""
    return _registry


def register_provider(provider_class: Type[AIService]):
    """Register a provider with the global registry"""
    _registry.register_provider(provider_class)


def get_all_providers() -> List[ProviderInfo]:
    """Get all registered providers"""
    return _registry.get_all_providers()


async def get_all_provider_states() -> List[ProviderInfo]:
    """Get current state of all providers"""
    return await _registry.get_provider_states()


def create_provider(provider_id: str, progress_callback, **config) -> Optional[AIService]:
    """Create a provider instance"""
    return _registry.create_provider(provider_id, progress_callback, **config)


async def validate_provider_config(provider_id: str, **config) -> tuple[bool, str]:
    """Validate configuration for a specific provider and auto-save if successful"""
    return await _registry.validate_provider_config(provider_id, **config)


async def save_provider_config(provider_id: str, **config) -> tuple[bool, str]:
    """Save configuration for a specific provider"""
    return await _registry.save_provider_config(provider_id, **config)


async def set_provider_enabled(provider_id: str, enabled: bool) -> bool:
    """Enable or disable a specific provider"""
    return await _registry.set_provider_enabled(provider_id, enabled)


async def get_provider_models(provider_id: str, **config) -> List[ModelInfo]:
    """Get available models for a provider"""
    return await _registry.get_provider_models(provider_id, **config)
