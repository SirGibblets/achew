"""
ASR Service Options and Registry Management

This module handles the auto-registration and management of ASR service options,
providing a plugin-like architecture where services can register themselves
without the core system needing to know about them explicitly.
"""

import importlib
import logging
import os
import pkgutil
from typing import Dict, List, Optional, Tuple, Type, Any

from app.models.progress import ProgressCallback
from app.services.asr_service import ASRService

logger = logging.getLogger(__name__)


class ASRModelVariant:
    """Represents a specific model variant for an ASR service"""

    def __init__(
        self,
        model_id: str,
        name: str,
        desc: str,
        path: str,
        languages: List[Tuple[str, str]],
    ):
        self.model_id: str = model_id
        self.name: str = name
        self.desc: str = desc
        self.path: str = path
        self.languages: List[Tuple[str, str]] = languages


class ASRServiceOption:
    """Represents an available ASR service option with its metadata"""

    def __init__(
        self,
        service_id: str,
        name: str,
        desc: str,
        uses_gpu: bool = False,
        supports_bias_words: bool = False,
        variants: List[ASRModelVariant] = None,
        priority: int = 0,
    ):
        self.service_id = service_id
        self.name = name
        self.desc = desc
        self.uses_gpu = uses_gpu
        self.supports_bias_words = supports_bias_words
        self.variants = variants or []
        self.priority = priority

    def __repr__(self):
        return f"ASRServiceOption(id={self.service_id}, name={self.name}, desc={self.desc}, uses_gpu={self.uses_gpu}, supports_bias_words={self.supports_bias_words}, priority={self.priority})"


class ASRServiceRegistry:
    """Registry for managing ASR service options and their implementations"""

    def __init__(self):
        self._services: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._priorities_used: Dict[int, str] = {}  # priority -> service_id mapping

    def register(self, service_id: str, service_class: Type, option: ASRServiceOption):
        """Register an ASR service with its implementation and metadata"""
        # Check for priority collision
        if option.priority in self._priorities_used:
            existing_service = self._priorities_used[option.priority]
            raise ValueError(
                f"Priority {option.priority} already used by service '{existing_service}', cannot register '{service_id}' with same priority"
            )

        self._services[service_id] = {
            "class": service_class,
            "option": option,
        }
        self._priorities_used[option.priority] = service_id
        logger.debug(f"Registered ASR service: {service_id} (priority: {option.priority})")

    def get_available_services(self) -> List[ASRServiceOption]:
        """Get all registered ASR service options, sorted by priority (highest first)"""
        if not self._initialized:
            self._discover_services()

        options = [entry["option"] for entry in self._services.values()]
        # Sort by priority in descending order (highest priority first)
        return sorted(options, key=lambda x: x.priority, reverse=True)

    def get_service_class(self, service_id: str) -> Optional[Type]:
        """Get the implementation class for a service"""
        if not self._initialized:
            self._discover_services()

        entry = self._services.get(service_id)
        return entry["class"] if entry else None

    def get_service_option(self, service_id: str) -> Optional[ASRServiceOption]:
        """Get the service option metadata for a service"""
        if not self._initialized:
            self._discover_services()

        entry = self._services.get(service_id)
        return entry["option"] if entry else None

    def create_service(self, **kwargs) -> ASRService:
        """Factory method to create an ASR service instance"""
        if not self._initialized:
            self._discover_services()

        from app.core.config import get_user_preferences

        prefs = get_user_preferences()

        # Use preferred or first available service
        service_option = self.get_preferred_service()
        if not service_option:
            available = self.get_available_services()
            if not available:
                raise RuntimeError("No ASR services available")
            service_option = available[0]

        service_class = self._services[service_option.service_id]["class"]

        # Get the model variant to use
        model_variant = service_option.variants[0] if service_option.variants else None
        variant_model_id = None

        # Check if user has a preferred variant
        if prefs.preferred_asr_variant and service_option.service_id == prefs.preferred_asr_service:
            variant_model_id = prefs.preferred_asr_variant

        if variant_model_id and service_option.variants:
            variant = next((v for v in service_option.variants if v.model_id == variant_model_id), None)
            if variant:
                model_variant = variant
            else:
                logger.warning(
                    f"Model variant '{variant_model_id}' not found, using '{model_variant.model_id if model_variant else 'default'}'"
                )

        # Create the service instance with appropriate arguments
        return service_class(
            model_path=model_variant.path,
            language=prefs.preferred_asr_language,
            **kwargs,
        )

    def get_preferred_service(self) -> Optional[ASRServiceOption]:
        """Get the user's preferred ASR service"""
        if not self._initialized:
            self._discover_services()

        from app.core.config import get_user_preferences

        prefs = get_user_preferences()

        # If user has a preference, and it's available, use it
        if prefs.preferred_asr_service and prefs.preferred_asr_service in self._services:
            return self._services[prefs.preferred_asr_service]["option"]

        # Return highest priority available service as default
        available = self.get_available_services()
        return available[0] if available else None

    def set_preferred_service(
        self,
        service_id: str,
        variant_model_id: str = None,
        language: str = "",
    ):
        """Set the user's preferred ASR service"""
        if not self._initialized:
            self._discover_services()

        if service_id in self._services:
            # Save preference to config
            try:
                from app.core.config import get_user_preferences, update_user_preferences, UserPreferences

                prefs = get_user_preferences()
                prefs.preferred_asr_service = service_id
                prefs.preferred_asr_variant = variant_model_id or ""
                prefs.preferred_asr_language = language

                if update_user_preferences(prefs):
                    logger.info(f"Set preferred ASR service to: {service_id} ({variant_model_id})")
                else:
                    logger.error("Failed to save ASR service preference")
            except ImportError:
                logger.error("Could not save user preferences")
        else:
            raise ValueError(f"ASR service '{service_id}' not found")

    def _discover_services(self):
        """Discover and load all available ASR service plugins"""
        if self._initialized:
            return

        logger.debug("Discovering ASR service plugins...")

        # Import the providers module to trigger auto-registration
        try:
            # Try to import the providers package which will auto-register services
            import app.services.asr_providers

            logger.debug("Imported ASR providers package")
        except ImportError as e:
            logger.warning(f"Failed to import ASR providers package: {e}")

            # Fallback: try direct module discovery
            try:
                providers_path = os.path.join(os.path.dirname(__file__), "asr_providers")
                if os.path.exists(providers_path):
                    # Import all provider modules
                    for finder, name, ispkg in pkgutil.iter_modules([providers_path]):
                        if name.endswith("_service"):
                            try:
                                module_name = f"app.services.asr_providers.{name}"
                                importlib.import_module(module_name)
                                logger.debug(f"Loaded ASR provider module: {module_name}")
                            except Exception as e:
                                logger.warning(f"Failed to load ASR provider {name}: {e}")
                else:
                    logger.debug("ASR providers directory not found, skipping plugin discovery")
            except Exception as e:
                logger.warning(f"Error during ASR service discovery: {e}")

        self._initialized = True
        logger.info(f"Discovered {len(self._services)} ASR services")


# Global registry instance
_registry = ASRServiceRegistry()


def register_asr_service(
    service_id: str,
    name: str,
    desc: str,
    uses_gpu: bool = False,
    supports_bias_words: bool = False,
    variants: List[ASRModelVariant] = None,
    priority: int = 0,
):
    """
    Decorator to register an ASR service class

    Priority levels:
    - 100: Parakeet MLX (highest priority)
    - 90: Whisper MLX
    - 80: Whisper GPU
    - 70: Whisper CPU (lowest priority)

    Usage:
        @register_asr_service("my_service", "My Service", "Description", priority=50, variants=[...])
        class MyASRService(ASRService):
            pass
    """

    def decorator(service_class):
        option = ASRServiceOption(service_id, name, desc, uses_gpu, supports_bias_words, variants or [], priority)
        _registry.register(service_id, service_class, option)
        return service_class

    return decorator


# Public API functions
def get_available_services() -> List[ASRServiceOption]:
    """Get list of all available ASR services"""
    return _registry.get_available_services()


def get_preferred_service() -> Optional[ASRServiceOption]:
    """Get the user's preferred ASR service"""
    return _registry.get_preferred_service()


def set_preferred_service(service_id: str, variant_model_id: str = None, language: str = ""):
    """Set the user's preferred ASR service"""
    _registry.set_preferred_service(service_id, variant_model_id, language)


def create_asr_service(progress_callback: ProgressCallback = None):
    """Factory function to create an appropriate ASR service"""
    return _registry.create_service(progress_callback=progress_callback)
