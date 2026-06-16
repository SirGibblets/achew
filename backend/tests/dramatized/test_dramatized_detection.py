"""Tests for the dramatized auto-detection heuristic (``classify_dramatized``).

Two layers:
- Synthetic unit tests that drive ``classify_dramatized`` directly with hand-built cues,
  written against the module constants so they survive threshold tuning.
- A fixture gate that replays real captures exported from the DEBUG "Dramatized fixture"
  button (``fixtures/*.json``) and asserts the heuristic agrees with the ground-truth label.
  Skipped cleanly until fixtures are committed.
"""

import json
from pathlib import Path
from typing import List

import pytest

from app.api.routes.chapters import DetectedCue
from app.services.dramatized_detection import (
    CUE_MATCH_TOLERANCE_SECONDS,
    DRAMATIZED_MIN_UNMATCHED_CUES,
    MASK_MARGIN_SECONDS,
    NOTABLE_GAP_SECONDS,
    classify_dramatized,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# A notable gap comfortably above the structural-cue threshold.
NOTABLE = NOTABLE_GAP_SECONDS + 2.0
# A gap below the structural-cue threshold (an ordinary pause).
TINY = max(0.0, NOTABLE_GAP_SECONDS - 0.5)
# Far enough apart that cues never accidentally match across lists.
FAR = CUE_MATCH_TOLERANCE_SECONDS + 100.0


def cues(*pairs: tuple[float, float]) -> List[DetectedCue]:
    """Build DetectedCues from (timestamp, gap) pairs."""
    return [DetectedCue(timestamp=ts, gap=gap) for ts, gap in pairs]


def notable_cues_at(timestamps: List[float]) -> List[DetectedCue]:
    return cues(*((ts, NOTABLE) for ts in timestamps))


def test_dramatized_when_vad_has_unmatched_notable_cues():
    # Just enough notable VAD cues with no nearby standard cue to trip the threshold.
    standard = notable_cues_at([10.0])
    vad_timestamps = [FAR * (i + 1) for i in range(DRAMATIZED_MIN_UNMATCHED_CUES)]
    vad = notable_cues_at(vad_timestamps)

    result = classify_dramatized(standard, vad)

    assert result.is_dramatized is True
    assert len(result.unmatched_notable_cues) == DRAMATIZED_MIN_UNMATCHED_CUES


def test_not_dramatized_when_vad_matches_standard():
    # Every VAD cue sits right on a standard cue, so none are unmatched.
    positions = [FAR * (i + 1) for i in range(DRAMATIZED_MIN_UNMATCHED_CUES + 2)]
    standard = notable_cues_at(positions)
    vad = notable_cues_at(positions)

    result = classify_dramatized(standard, vad)

    assert result.is_dramatized is False
    assert result.unmatched_notable_cues == []


def test_below_min_unmatched_count_is_not_dramatized():
    standard = notable_cues_at([10.0])
    vad_timestamps = [FAR * (i + 1) for i in range(DRAMATIZED_MIN_UNMATCHED_CUES - 1)]
    vad = notable_cues_at(vad_timestamps)

    result = classify_dramatized(standard, vad)

    assert result.is_dramatized is False
    assert len(result.unmatched_notable_cues) == DRAMATIZED_MIN_UNMATCHED_CUES - 1


def test_tiny_gaps_are_ignored_even_when_unmatched():
    # Many unmatched VAD cues, but all below the notable-gap threshold (ordinary pauses).
    standard = notable_cues_at([10.0])
    vad = cues(*((FAR * (i + 1), TINY) for i in range(DRAMATIZED_MIN_UNMATCHED_CUES + 3)))

    result = classify_dramatized(standard, vad)

    assert result.is_dramatized is False
    assert result.unmatched_notable_cues == []


def test_cue_within_tolerance_counts_as_matched():
    # A VAD cue exactly at the tolerance distance from a standard cue is matched.
    standard = notable_cues_at([1000.0])
    vad = notable_cues_at([1000.0 + CUE_MATCH_TOLERANCE_SECONDS])

    result = classify_dramatized(standard, vad)

    assert result.unmatched_notable_cues == []


def test_cue_just_beyond_tolerance_is_unmatched():
    standard = notable_cues_at([1000.0])
    vad = notable_cues_at([1000.0 + CUE_MATCH_TOLERANCE_SECONDS + 0.5])

    result = classify_dramatized(standard, vad)

    assert len(result.unmatched_notable_cues) == 1


def test_long_vad_gap_over_small_nearby_standard_cue_is_masked():
    # The masking signature: a brief standard pause sits right beside a long VAD gap.
    # Proximity alone would call this "matched"; magnitude must still flag it, because
    # silence detection only caught a sliver of the music-covered transition.
    standard = cues((1000.0, max(0.0, NOTABLE_GAP_SECONDS - 1.0)))
    long_gap = NOTABLE_GAP_SECONDS + MASK_MARGIN_SECONDS + 5.0
    vad = cues((1000.0 + 1.0, long_gap))

    result = classify_dramatized(standard, vad)

    assert len(result.unmatched_notable_cues) == 1


def test_vad_gap_matched_in_magnitude_is_not_masked():
    # VAD measures a slightly longer non-speech window than standard at a shared pause, but
    # within the mask margin — an ordinary pause both detectors saw, not a masked transition.
    shared_gap = NOTABLE_GAP_SECONDS + 5.0
    standard = cues((1000.0, shared_gap))
    vad = cues((1000.5, shared_gap + (MASK_MARGIN_SECONDS - 0.5)))

    result = classify_dramatized(standard, vad)

    assert result.unmatched_notable_cues == []


def test_empty_inputs_are_not_dramatized():
    result = classify_dramatized([], [])

    assert result.is_dramatized is False
    assert result.standard_cue_count == 0
    assert result.vad_cue_count == 0
    assert result.unmatched_notable_cues == []


def test_counts_reflect_inputs():
    standard = notable_cues_at([10.0, 20.0])
    vad = notable_cues_at([FAR, FAR * 2, FAR * 3])

    result = classify_dramatized(standard, vad)

    assert result.standard_cue_count == 2
    assert result.vad_cue_count == 3


def _load_fixtures() -> List[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", _load_fixtures(), ids=lambda p: p.stem)
def test_real_fixture_matches_ground_truth(fixture_path: Path):
    """Each captured fixture: the heuristic's verdict must match the ground-truth label."""
    data = json.loads(fixture_path.read_text())
    standard = cues(*((float(p[0]), float(p[1])) for p in data["standard_cues"]))
    vad = cues(*((float(p[0]), float(p[1])) for p in data["vad_cues"]))

    result = classify_dramatized(standard, vad)

    assert result.is_dramatized == data["ground_truth_dramatized"], (
        f"{fixture_path.name}: expected dramatized={data['ground_truth_dramatized']}, "
        f"got {result.is_dramatized} (standard={result.standard_cue_count}, "
        f"vad={result.vad_cue_count}, unmatched={len(result.unmatched_notable_cues)})"
    )
