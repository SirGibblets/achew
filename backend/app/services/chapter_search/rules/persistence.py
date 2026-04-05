"""Persist/load the chapter search rule set as a JSON file."""

import json
import logging
import os
from pathlib import Path

from ..rules.models import RuleSet, create_default_ruleset

logger = logging.getLogger(__name__)


def _get_ruleset_json_path() -> Path:
    from ....core.config import get_config_json_path
    return get_config_json_path().parent / "chapter_search_ruleset.json"


def load_ruleset() -> RuleSet:
    """Load the root rule set from persistent storage, creating defaults if absent."""
    try:
        path = _get_ruleset_json_path()
        if path.exists():
            with open(path, "r") as f:
                raw = json.load(f)
            return RuleSet.model_validate(raw)
    except Exception as e:
        logger.warning(f"Failed to load chapter search ruleset: {e}")
    return create_default_ruleset()


def save_ruleset(ruleset: RuleSet) -> bool:
    """Persist the root rule set to a JSON file."""
    try:
        path = _get_ruleset_json_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(ruleset.model_dump(mode="json"), f, indent=2)
        os.replace(str(tmp_path), str(path))
        return True
    except Exception as e:
        logger.error(f"Failed to save chapter search ruleset: {e}")
        return False
