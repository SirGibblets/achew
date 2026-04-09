import json
import logging
from typing import Any, Optional

from ...models.sources import CueSourceType, ExistingCue, ExistingCueSource
from .base_parser import BaseCueParser
from .timestamp_utils import normalize_timestamps, parse_timestamp, score_timestamp
from .title_utils import score_title

logger = logging.getLogger(__name__)

_TIMESTAMP_POSITIVE = {"start", "time", "timestamp", "offset", "begin", "position"}
_TIMESTAMP_NEGATIVE = {"end", "length", "duration", "stop", "finish"}
_TITLE_KEYWORDS = {"title", "name", "chapter", "label", "heading", "text"}


def _score_array(items: list[dict]) -> tuple[float, Optional[str], Optional[str]]:
    """Score a list-of-dicts as a chapter array.

    Returns (score, timestamp_field, title_field).
    Higher overall score means higher likelihood of being the chapter array.
    """
    if not items or not isinstance(items[0], dict):
        return -float("inf"), None, None

    keys = {k for item in items for k in item.keys() if isinstance(k, str)}
    if not keys:
        return -float("inf"), None, None

    best_ts_field: Optional[str] = None
    best_ts_score = -float("inf")

    for k in keys:
        score = 0
        k_lower = k.lower()
        if any(pos in k_lower for pos in _TIMESTAMP_POSITIVE):
            score += 10
        if any(neg in k_lower for neg in _TIMESTAMP_NEGATIVE):
            score -= 10

        for item in items:
            if k in item:
                score += score_timestamp(item[k])

        if score > best_ts_score:
            best_ts_score = score
            best_ts_field = k

    best_title_field: Optional[str] = None
    best_title_score = -float("inf")

    for k in keys:
        if k == best_ts_field:
            continue

        score = 0
        k_lower = k.lower()
        if any(kw in k_lower for kw in _TITLE_KEYWORDS):
            score += 10

        for item in items:
            if k in item:
                score += score_title(item[k])

        if score > best_title_score:
            best_title_score = score
            best_title_field = k

    if best_ts_field is None or best_title_field is None:
        return -float("inf"), None, None

    has_valid_ts = any(
        parse_timestamp(item[best_ts_field]) is not None
        for item in items
        if best_ts_field in item
    )
    if not has_valid_ts:
        return -float("inf"), None, None

    return best_ts_score + best_title_score, best_ts_field, best_title_field


def _collect_arrays(obj: Any) -> list[list]:
    """Recursively collect all arrays found anywhere in a JSON structure."""
    results = []
    if isinstance(obj, list):
        results.append(obj)
        for item in obj:
            results.extend(_collect_arrays(item))
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_collect_arrays(v))
    return results


class JsonParser(BaseCueParser):
    short_name = "JSON"

    def parse(self, file_path: str, source_name: str, duration: float = 0.0) -> ExistingCueSource:
        """Parse a JSON file for chapter cue data using heuristic field scoring."""
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Could not read JSON: {e}") from e

        arrays = _collect_arrays(data)
        if not arrays:
            raise ValueError("No arrays found in JSON")

        best_score = -float("inf")
        best_array = None
        best_ts_field = None
        best_title_field = None

        for arr in arrays:
            score, ts_field, title_field = _score_array(arr)
            if score > best_score and ts_field and title_field:
                best_score = score
                best_array = arr
                best_ts_field = ts_field
                best_title_field = title_field

        if best_array is None or best_ts_field is None or best_title_field is None:
            raise ValueError("No plausible chapter array found in JSON (need timestamp + title fields)")

        raw_timestamps = []
        titles = []
        for item in best_array:
            ts = parse_timestamp(item.get(best_ts_field))
            title = str(item.get(best_title_field, "")).strip()
            if ts is not None:
                raw_timestamps.append(ts)
                titles.append(title)

        if not raw_timestamps:
            raise ValueError("No parseable timestamps found in the best array")

        normalised = normalize_timestamps(raw_timestamps)
        cues = list(zip(normalised, titles))

        name = self.ellipsize_name(source_name)
        logger.info(f"Parsed {source_name} as JSON cue source ({len(cues)} cues)")
        return ExistingCueSource(
            type=CueSourceType.JSON,
            name=f"[JSON] {name}",
            short_name=self.short_name,
            description=f"Chapter data parsed from JSON file \"{name}\"",
            metadata={"File": source_name},
            cues=[ExistingCue(timestamp=ts, title=t) for ts, t in cues],
            duration=duration,
        )
