import re
from typing import Optional

# Audiobooks realistically range from 30 minutes to 100 hours.
# If the largest value treated as seconds would exceed 100 hours,
# we assume the values are in milliseconds.
_MAX_PLAUSIBLE_SECONDS = 360_000  # 100 hours

_HH_MM_SS = re.compile(r"^(\d+):(\d{2}):(\d{2})(?:[.,](\d+))?$")
_MM_SS = re.compile(r"^(\d+):(\d{2})(?:[.,](\d+))?$")


def score_timestamp(value) -> int:
    """Score the likelihood of a value being a timestamp.
    
    Higher positive values indicate it's a good timestamp candidate.
    Negative values indicate it is likely text or unparseable.
    """
    if isinstance(value, (int, float)):
        return 1

    if not isinstance(value, str):
        return -5

    s = value.strip()

    m = _HH_MM_SS.match(s)
    if m:
        # Check if ms group exists
        if m.group(4):
            return 5
        return 4

    m = _MM_SS.match(s)
    if m:
        # Check if ms group exists
        if m.group(3):
            return 5
        return 4

    # Bare numeric string
    try:
        float(s)
        return 1
    except ValueError:
        return -5


def parse_timestamp(value) -> Optional[float]:
    """Parse a single timestamp value to seconds.

    Accepts:
      - Strings: "HH:MM:SS", "HH:MM:SS.ms", "MM:SS", "MM:SS.ms"
      - Numeric (int/float): returned as-is (unit detection done later)
    Returns None if the value cannot be parsed.
    """
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        return None

    s = value.strip()

    m = _HH_MM_SS.match(s)
    if m:
        h, mn, sec = int(m.group(1)), int(m.group(2)), int(m.group(3))
        frac = float("0." + m.group(4)) if m.group(4) else 0.0
        return h * 3600 + mn * 60 + sec + frac

    m = _MM_SS.match(s)
    if m:
        mn, sec = int(m.group(1)), int(m.group(2))
        frac = float("0." + m.group(3)) if m.group(3) else 0.0
        return mn * 60 + sec + frac

    # Bare numeric string
    try:
        return float(s)
    except ValueError:
        return None


def normalize_timestamps(values: list[float]) -> list[float]:
    """Detect whether timestamps are in milliseconds or seconds and normalise to seconds.

    Heuristic: if the maximum value, when treated as seconds, exceeds
    _MAX_PLAUSIBLE_SECONDS (100 hours) it almost certainly represents
    milliseconds, so divide every value by 1000.
    """
    if not values:
        return values
    if max(values) > _MAX_PLAUSIBLE_SECONDS:
        return [v / 1000.0 for v in values]
    return values
