"""One-time migration from shelve config database to JSON files."""

import json
import logging
import os
import shelve
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_config_dir() -> Path:
    return Path(__file__).parent.parent / "config"


def _get_shelve_base() -> str:
    return str(_get_config_dir() / "app_config")


def _get_shelve_files() -> list[Path]:
    """Find all shelve-related files in the config directory."""
    config_dir = _get_config_dir()
    if not config_dir.exists():
        return []

    shelve_files = []
    for path in config_dir.iterdir():
        if not path.is_file():
            continue
        if path.name == "app_config" or (
            path.name.startswith("app_config.") and path.suffix not in (".json", ".tmp")
        ):
            shelve_files.append(path)
    return shelve_files


def _delete_shelve_files():
    """Remove all shelve-related files from the config directory."""
    for path in _get_shelve_files():
        try:
            path.unlink()
            logger.info(f"Deleted legacy shelve file: {path.name}")
        except OSError as e:
            logger.warning(f"Failed to delete {path.name}: {e}")


def migrate_shelve_to_json() -> str:
    """
    Migrate config from shelve to JSON.

    Returns:
        "ok"      — migration succeeded
        "skipped" — no migration needed (fresh install or already migrated)
        "failed"  — shelve exists but could not be read
    """
    from .config import get_config_json_path, AppConfig, ABSConfig, LLMConfig, UserPreferences, ASROptions, CustomInstructionsConfig

    config_dir = _get_config_dir()
    json_path = get_config_json_path()
    shelve_files = _get_shelve_files()

    has_json = json_path.exists()
    has_shelve = len(shelve_files) > 0

    if has_json and has_shelve:
        logger.info("JSON config exists alongside legacy shelve files — cleaning up shelve files")
        _delete_shelve_files()
        return "skipped"

    if has_json or not has_shelve:
        return "skipped"

    # Shelve files exist but no JSON — attempt migration
    logger.info("Migrating configuration from shelve to JSON…")
    try:
        with shelve.open(_get_shelve_base(), "r") as db:
            abs_data = db.get("abs", {})
            llm_data = db.get("llm", {})
            user_prefs_data = db.get("user_preferences", {})
            asr_options_data = db.get("asr_options", {})
            custom_instructions_data = db.get("custom_instructions", {})
            ruleset_data = db.get("chapter_search_ruleset", None)

        # Reconstruct through Pydantic to validate and normalize datetimes
        app_config = AppConfig(
            abs=ABSConfig(**abs_data) if abs_data else ABSConfig(),
            llm=LLMConfig(**llm_data) if llm_data else LLMConfig(),
            user_preferences=UserPreferences(**user_prefs_data) if user_prefs_data else UserPreferences(),
            asr_options=ASROptions(**asr_options_data) if asr_options_data else ASROptions(),
            custom_instructions=CustomInstructionsConfig(**custom_instructions_data) if custom_instructions_data else CustomInstructionsConfig(),
        )

        config_data = {
            "abs": app_config.abs.model_dump(mode="json"),
            "llm": app_config.llm.model_dump(mode="json"),
            "user_preferences": app_config.user_preferences.model_dump(mode="json"),
            "asr_options": app_config.asr_options.model_dump(mode="json"),
            "custom_instructions": app_config.custom_instructions.model_dump(mode="json"),
        }

        # Write app config JSON atomically
        config_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = json_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(config_data, f, indent=2)
        os.replace(str(tmp_path), str(json_path))

        # Migrate chapter search ruleset to its own JSON file
        if ruleset_data:
            from ..services.chapter_search.rules.models import RuleSet
            ruleset = RuleSet.model_validate(ruleset_data)
            ruleset_path = config_dir / "chapter_search_ruleset.json"
            tmp_ruleset_path = ruleset_path.with_suffix(".tmp")
            with open(tmp_ruleset_path, "w") as f:
                json.dump(ruleset.model_dump(mode="json"), f, indent=2)
            os.replace(str(tmp_ruleset_path), str(ruleset_path))

        _delete_shelve_files()
        logger.info("Configuration migration completed successfully")
        return "ok"

    except Exception as e:
        logger.warning(f"Configuration migration failed: {e}")
        return "failed"


def reset_after_migration_failure():
    """Delete unreadable shelve files so the app can start fresh."""
    _delete_shelve_files()
    logger.info("Legacy shelve files removed after user-initiated reset")
