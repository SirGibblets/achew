"""Persist/load the chapter search rule set from the app's shelve config DB."""

import json
import logging
import shelve

from ..rules.models import RuleSet, create_default_ruleset

logger = logging.getLogger(__name__)

SHELVE_KEY = "chapter_search_ruleset"


def _get_config_db_path() -> str:
    from ....core.config import get_config_db_path
    return str(get_config_db_path())


def load_ruleset() -> RuleSet:
    """Load the root rule set from persistent storage, creating defaults if absent."""
    try:
        with shelve.open(_get_config_db_path(), "c") as db:
            raw = db.get(SHELVE_KEY)
        if raw:
            return RuleSet.model_validate(raw)
    except Exception as e:
        logger.warning(f"Failed to load chapter search ruleset: {e}")
    return create_default_ruleset()


def save_ruleset(ruleset: RuleSet) -> bool:
    """Persist the root rule set to the shelve config DB."""
    try:
        with shelve.open(_get_config_db_path(), "c") as db:
            db[SHELVE_KEY] = ruleset.model_dump()
            db.sync()
        return True
    except Exception as e:
        logger.error(f"Failed to save chapter search ruleset: {e}")
        return False
