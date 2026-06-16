"""Heuristic that decides whether an audiobook is *dramatized* (contains music /
sound-effects) by comparing standard silence detection against VAD detection.

Silence detection (ffmpeg ``silencedetect``) only sees true silence, so a chapter or
scene transition masked by music or sound-effects is invisible to it. VAD detects
*non-speech* gaps, so it still surfaces those transitions. The tell-tale of masking is
not merely a VAD cue with no standard cue beside it — it is a VAD cue whose non-speech
gap is *much longer* than any standard silence at the same spot. When music covers a
transition, ``silencedetect`` still catches the sliver of true silence at its edge and
reports a short gap there; VAD reports the whole long gap. Comparing the two by
**magnitude** (not just proximity) is what separates a masked transition from an
ordinary shared pause, where both detectors measure a near-equal gap.

This module operates on already-detected cues and performs no audio I/O, so it can be
driven directly by synthetic tests and real captured fixtures.
"""

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from app.api.routes.chapters import DetectedCue

# Length of audio (seconds) sampled from the start and the end of the book for the probe.
SAMPLE_WINDOW_SECONDS = 90.0

# A VAD cue and a standard cue can describe the same silence only when their timestamps
# fall within this many seconds of each other; beyond it, standard detection saw nothing
# at the VAD cue's location.
CUE_MATCH_TOLERANCE_SECONDS = 4.0

# Minimum non-speech gap for a VAD cue to count as a structural (chapter/scene) cue
# rather than an ordinary pause in narration.
NOTABLE_GAP_SECONDS = 3.0

# How much longer a VAD cue's gap must be than the nearest standard cue's gap before it
# counts as music-masked. An ordinary shared pause shows near-equal gaps (margin ~0); a
# masked transition shows a long VAD gap over a short-or-absent standard one. Requiring a
# real magnitude difference stops a brief narration pause from "explaining away" a long
# masked VAD gap merely because it happens to sit nearby.
MASK_MARGIN_SECONDS = 2.0

# Classify the book as dramatized once at least this many masked VAD cues appear. One is
# enough: across 65 real standard books not a single masked cue occurred (the magnitude
# rule above filters ordinary pauses hard), while every one of 35 dramatized books surfaced
# at least one. The verdict's costs are also asymmetric — a missed dramatized book gets the
# wrong silence-only detection path (masked chapters lost), whereas a wrongly-flagged
# standard book merely runs the slower VAD path, which still finds its real boundaries.
DRAMATIZED_MIN_UNMATCHED_CUES = 1


@dataclass
class DramatizedAnalysis:
    """Result of comparing standard vs VAD cues across the sampled windows."""

    is_dramatized: bool
    standard_cue_count: int
    vad_cue_count: int
    # (timestamp, gap) of each notable VAD cue whose gap a nearby standard cue could not
    # account for (music-masked transition).
    unmatched_notable_cues: List[Tuple[float, float]] = field(default_factory=list)


def _nearby_standard_gap(timestamp: float, standard_cues: Sequence[DetectedCue], tolerance: float) -> float:
    """Largest standard-cue gap within ``tolerance`` of ``timestamp`` (0.0 if none).

    Standard detection may report several short silences around a VAD cue; the longest is
    the most generous account of the true silence it actually saw there, so it sets the bar
    a VAD gap must clear to look masked.
    """
    nearby = [c.gap for c in standard_cues if abs(c.timestamp - timestamp) <= tolerance]
    return max(nearby, default=0.0)


def classify_dramatized(
    standard_cues: Sequence[DetectedCue],
    vad_cues: Sequence[DetectedCue],
) -> DramatizedAnalysis:
    """Decide whether the sampled audio looks dramatized.

    A notable (``NOTABLE_GAP_SECONDS``) VAD cue is "unmatched" — masked by music/SFX — when
    its gap exceeds the longest nearby standard gap by more than ``MASK_MARGIN_SECONDS``:
    VAD found a long non-speech region where silence detection saw only a sliver (or
    nothing). The book is dramatized when at least ``DRAMATIZED_MIN_UNMATCHED_CUES`` such
    cues exist.
    """
    unmatched_notable_cues: List[Tuple[float, float]] = []
    for cue in vad_cues:
        if cue.gap < NOTABLE_GAP_SECONDS:
            continue
        standard_gap = _nearby_standard_gap(cue.timestamp, standard_cues, CUE_MATCH_TOLERANCE_SECONDS)
        if cue.gap - standard_gap > MASK_MARGIN_SECONDS:
            unmatched_notable_cues.append((cue.timestamp, cue.gap))

    return DramatizedAnalysis(
        is_dramatized=len(unmatched_notable_cues) >= DRAMATIZED_MIN_UNMATCHED_CUES,
        standard_cue_count=len(standard_cues),
        vad_cue_count=len(vad_cues),
        unmatched_notable_cues=unmatched_notable_cues,
    )
