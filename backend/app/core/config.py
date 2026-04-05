import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field
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
    copilot: LLMProviderConfig = LLMProviderConfig()
    openrouter: LLMProviderConfig = LLMProviderConfig()
    ollama: LLMProviderConfig = LLMProviderConfig()
    lm_studio: LLMProviderConfig = LLMProviderConfig()

    # AI cleanup preferences
    last_used_provider: str = ""
    last_used_model: str = ""


class ASROptions(BaseModel):
    """ASR configuration options"""

    trim: bool = True
    use_bias_words: bool = False
    bias_words: str = ""
    segment_length: float = 8.0


class EditorSettings(BaseModel):
    """Chapter editor settings"""

    tab_navigation: bool = False
    hide_transcriptions: bool = False
    show_formatted_time: bool = True


class CustomInstruction(BaseModel):
    """Individual custom instruction for AI cleanup"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    checked: bool = True
    order: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class CustomInstructionsConfig(BaseModel):
    """Custom instructions configuration section"""

    instructions: List[CustomInstruction] = Field(default_factory=list)
    last_updated: Optional[datetime] = None


class UserPreferences(BaseModel):
    """User preferences configuration section"""

    preferred_asr_service: str = ""
    preferred_asr_variant: str = ""
    preferred_asr_language: str = ""
    editor_settings: EditorSettings = EditorSettings()


class AppConfig(BaseModel):
    """Complete application configuration"""

    abs: ABSConfig = ABSConfig()
    llm: LLMConfig = LLMConfig()
    user_preferences: UserPreferences = UserPreferences()
    asr_options: ASROptions = ASROptions()
    custom_instructions: CustomInstructionsConfig = CustomInstructionsConfig()


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
    """Get the path to the legacy shelve configuration database (used by migration only)"""
    return Path(__file__).parent.parent / "config" / "app_config"


def get_config_json_path() -> Path:
    """Get the path to the JSON configuration file"""
    return Path(__file__).parent.parent / "config" / "app_config.json"


def _ensure_config_dir():
    """Ensure the config directory exists"""
    config_path = get_config_json_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """Load complete application configuration from JSON file"""
    _ensure_config_dir()
    config_path = get_config_json_path()

    try:
        if config_path.exists():
            with open(config_path, "r") as f:
                data = json.load(f)

            return AppConfig(
                abs=ABSConfig(**data["abs"]) if data.get("abs") else ABSConfig(),
                llm=LLMConfig(**data["llm"]) if data.get("llm") else LLMConfig(),
                user_preferences=UserPreferences(**data["user_preferences"]) if data.get("user_preferences") else UserPreferences(),
                asr_options=ASROptions(**data["asr_options"]) if data.get("asr_options") else ASROptions(),
                custom_instructions=CustomInstructionsConfig(**data["custom_instructions"]) if data.get("custom_instructions") else CustomInstructionsConfig(),
            )
        return AppConfig()
    except Exception as e:
        logger.warning(f"Failed to load configuration from {config_path}: {e}")
        return AppConfig()


def save_config(config: AppConfig) -> bool:
    """Save complete application configuration to JSON file"""
    _ensure_config_dir()
    config_path = get_config_json_path()

    try:
        data = {
            "abs": config.abs.model_dump(mode="json"),
            "llm": config.llm.model_dump(mode="json"),
            "user_preferences": config.user_preferences.model_dump(mode="json"),
            "asr_options": config.asr_options.model_dump(mode="json"),
            "custom_instructions": config.custom_instructions.model_dump(mode="json"),
        }

        tmp_path = config_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(str(tmp_path), str(config_path))
        return True
    except Exception as e:
        logger.error(f"Failed to save configuration to {config_path}: {e}")
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


def save_custom_instructions(custom_instructions: CustomInstructionsConfig) -> bool:
    """Save only custom instructions section"""
    try:
        config = load_config()
        config.custom_instructions = custom_instructions
        return save_config(config)
    except Exception as e:
        logger.error(f"Failed to save custom instructions: {e}")
        return False


def get_default_custom_instructions() -> List[CustomInstruction]:
    """Get default example custom instructions"""
    examples = [
        "Fix any misspellings of…",
        "Use this format: Chapter [number] - [title]",
        "Use Roman Numerals for chapter numbers",
        "Return the results in Spanish",
        "Do not include title text",
    ]

    default_instructions = []
    for i, text in enumerate(examples):
        default_instructions.append(
            CustomInstruction(text=text, checked=False, order=i)
        )

    return default_instructions


# Global configuration cache
_settings: Optional[Settings] = None
_app_config: Optional[AppConfig] = None
_migration_failed: bool = False


def is_migration_failed() -> bool:
    return _migration_failed


def set_migration_failed(failed: bool):
    global _migration_failed
    _migration_failed = failed


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
        logger.info(f"Loaded app config - OPENROUTER_API_KEY: {'***' if _app_config.llm.openrouter.api_key else 'EMPTY'}")
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
        "migration_failed": is_migration_failed(),
    }
