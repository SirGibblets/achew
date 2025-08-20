import shelve
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel
from pydantic_settings import BaseSettings

# Development CORS origins (Vite) - only used when frontend runs separately
DEV_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

logger = logging.getLogger(__name__)


class ABSConfig(BaseModel):
    """ABS configuration section"""

    url: str = ""
    api_key: str = ""
    validated: bool = False
    last_validated: Optional[datetime] = None


class LLMProviderConfig(BaseModel):
    """Individual LLM provider configuration"""

    api_key: str = ""
    host: str = ""  # For providers like Ollama
    validated: bool = False
    last_validated: Optional[datetime] = None
    enabled: bool = False  # Default to disabled
    validation_status: str = "disabled"  # disabled, not_validated, validating, configured, error
    validation_message: Optional[str] = None
    config_changed: bool = False


class LLMConfig(BaseModel):
    """LLM providers configuration section"""

    openai: LLMProviderConfig = LLMProviderConfig()
    claude: LLMProviderConfig = LLMProviderConfig()
    gemini: LLMProviderConfig = LLMProviderConfig()
    ollama: LLMProviderConfig = LLMProviderConfig()
    lm_studio: LLMProviderConfig = LLMProviderConfig()

    # AI cleanup preferences
    last_used_provider: str = ""
    last_used_model: str = ""


class ASROptions(BaseModel):
    """ASR configuration options"""

    trim: bool = True


class UserPreferences(BaseModel):
    """User preferences configuration section"""

    preferred_asr_service: str = ""
    preferred_asr_variant: str = ""
    preferred_asr_language: str = ""
    theme: str = "auto"
    notifications: bool = True


class AppConfig(BaseModel):
    """Complete application configuration"""

    abs: ABSConfig = ABSConfig()
    llm: LLMConfig = LLMConfig()
    user_preferences: UserPreferences = UserPreferences()
    asr_options: ASROptions = ASROptions()


class Settings(BaseSettings):
    # Web App Configuration (from environment)
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    class Config:
        case_sensitive = True

    @property
    def cors_origins_list(self) -> List[str]:
        """
        Get CORS origins based on environment.
        In development (when DEBUG=true), use development CORS origins for Vite.
        In production, no CORS needed as frontend is served from same origin.
        """
        if self.DEBUG:
            # Development mode - allow Vite dev server
            return DEV_CORS_ORIGINS
        else:
            # Production mode - no CORS needed, frontend served from same origin
            return []


def get_config_db_path() -> Path:
    """Get the path to the configuration database"""
    return Path(__file__).parent.parent / "config" / "app_config"


def _ensure_config_dir():
    """Ensure the config directory exists"""
    config_path = get_config_db_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """Load complete application configuration from shelve database"""
    _ensure_config_dir()
    config_db_path = str(get_config_db_path())

    try:
        with shelve.open(config_db_path, "c") as db:
            # Load each section, with defaults if not present
            abs_data = db.get("abs", {})
            llm_data = db.get("llm", {})
            user_prefs_data = db.get("user_preferences", {})
            asr_options_data = db.get("asr_options", {})

            # Create config objects with validation
            abs_config = ABSConfig(**abs_data) if abs_data else ABSConfig()
            llm_config = LLMConfig(**llm_data) if llm_data else LLMConfig()
            user_prefs = UserPreferences(**user_prefs_data) if user_prefs_data else UserPreferences()
            asr_options = ASROptions(**asr_options_data) if asr_options_data else ASROptions()

            return AppConfig(abs=abs_config, llm=llm_config, user_preferences=user_prefs, asr_options=asr_options)
    except Exception as e:
        logger.warning(f"Failed to load configuration from {config_db_path}: {e}")
        return AppConfig()


def save_config(config: AppConfig) -> bool:
    """Save complete application configuration to shelve database"""
    _ensure_config_dir()
    config_db_path = str(get_config_db_path())

    try:
        with shelve.open(config_db_path, "c") as db:
            db["abs"] = config.abs.model_dump()
            db["llm"] = config.llm.model_dump()
            db["user_preferences"] = config.user_preferences.model_dump()
            db["asr_options"] = config.asr_options.model_dump()
            db.sync()  # Ensure data is written to disk
        return True
    except Exception as e:
        logger.error(f"Failed to save configuration to {config_db_path}: {e}")
        return False


def save_abs_config(abs_config: ABSConfig) -> bool:
    """Save only ABS configuration section"""
    try:
        config = load_config()
        config.abs = abs_config
        return save_config(config)
    except Exception as e:
        logger.error(f"Failed to save ABS configuration: {e}")
        return False


def save_llm_config(llm_config: LLMConfig) -> bool:
    """Save only LLM configuration section"""
    try:
        config = load_config()
        config.llm = llm_config
        return save_config(config)
    except Exception as e:
        logger.error(f"Failed to save LLM configuration: {e}")
        return False


def save_llm_provider_config(provider: str, provider_config: LLMProviderConfig) -> bool:
    """Save configuration for a specific LLM provider"""
    try:
        config = load_config()
        if hasattr(config.llm, provider):
            setattr(config.llm, provider, provider_config)
            return save_config(config)
        else:
            logger.error(f"Unknown LLM provider: {provider}")
            return False
    except Exception as e:
        logger.error(f"Failed to save {provider} provider configuration: {e}")
        return False


def save_user_preferences(preferences: UserPreferences) -> bool:
    """Save only user preferences section"""
    try:
        config = load_config()
        config.user_preferences = preferences
        return save_config(config)
    except Exception as e:
        logger.error(f"Failed to save user preferences: {e}")
        return False


# Global configuration cache
_settings: Optional[Settings] = None
_app_config: Optional[AppConfig] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        # Debug logging to verify settings
        logger.info(f"Loaded settings - HOST: {_settings.HOST}")
        logger.info(f"Loaded settings - PORT: {_settings.PORT}")
        logger.info(f"Loaded settings - DEBUG: {_settings.DEBUG}")
        if _settings.DEBUG:
            logger.info(f"Loaded settings - CORS_ORIGINS (dev mode): {_settings.cors_origins_list}")
        else:
            logger.info("Loaded settings - CORS disabled (production mode)")
    return _settings


def get_app_config() -> AppConfig:
    """Get the current application configuration"""
    global _app_config
    if _app_config is None:
        _app_config = load_config()
        logger.info(f"Loaded app config - ABS_URL: {_app_config.abs.url}")
        logger.info(f"Loaded app config - ABS_API_KEY: {'***' if _app_config.abs.api_key else 'EMPTY'}")
        logger.info(f"Loaded app config - OPENAI_API_KEY: {'***' if _app_config.llm.openai.api_key else 'EMPTY'}")
        logger.info(f"Loaded app config - GEMINI_API_KEY: {'***' if _app_config.llm.gemini.api_key else 'EMPTY'}")
        logger.info(f"Loaded app config - CLAUDE_API_KEY: {'***' if _app_config.llm.claude.api_key else 'EMPTY'}")
    return _app_config


def refresh_app_config():
    """Force reload of application configuration from database"""
    global _app_config
    _app_config = None
    get_app_config()


def update_app_config(config: AppConfig) -> bool:
    """Update the application configuration and save to database"""
    global _app_config
    if save_config(config):
        _app_config = config
        return True
    return False


def get_user_preferences() -> UserPreferences:
    """Get user preferences"""
    config = get_app_config()
    return config.user_preferences


def update_user_preferences(preferences: UserPreferences) -> bool:
    """Update user preferences"""
    return save_user_preferences(preferences)


def is_abs_configured() -> bool:
    """Check if ABS is properly configured"""
    config = get_app_config()
    return bool(config.abs.url and config.abs.api_key)


def get_configuration_status() -> Dict[str, Any]:
    """Get overall configuration status for session management"""
    config = get_app_config()

    return {
        "abs_configured": is_abs_configured(),
        "abs_validated": config.abs.validated,
        "needs_abs_setup": not is_abs_configured(),
        "needs_llm_setup": False,  # LLM setup is always optional
    }
