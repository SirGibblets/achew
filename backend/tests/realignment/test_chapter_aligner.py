"""Tests for ChapterAligner.

Two layers:
- Strict tests for specific designed behaviours (the chapter-2 decoy, a missing chapter,
  edge cases).
- A regression gate (``test_no_regression_vs_baseline``) that scores the aligner on every
  synthetic case and every real captured fixture and fails if any case got worse than the
  committed baseline in ``realignment_baseline.json``. After an intentional aligner change,
  regenerate the baseline with ``--update-aligner-baseline`` and review/commit the diff.
"""

import json
import random
from pathlib import Path

import pytest
from realignment_helpers import (
    SYNTHETIC_BUILDERS,
    Fixture,
    load_real_fixtures,
    make_front_matter_decoy,
    make_missing_chapter,
    score_alignment,
)

from app.services.chapter_aligner import ChapterAligner

# Seeds give us a handful of distinct books per scenario while staying deterministic.
SEEDS = [1, 2, 3, 7, 11]

BASELINE_PATH = Path(__file__).parent / "realignment_baseline.json"
# A placement within this of ground truth counts as correct: wide of the 0.01s ground-truth
# quantization, far inside any decoy distance.
SCORE_TOLERANCE = 0.1


def _padding(fx: Fixture) -> float:
    # Mirror the pipeline's extraction padding, which also bounds the match window.
    return max(30.0, abs(fx.book_duration - fx.ref_duration) * 1.5)


def _align(fx: Fixture):
    aligner = ChapterAligner(max_drift=_padding(fx))
    result, _ = aligner.align(fx.ref_chapters, fx.detected_cues, fx.ref_duration, fx.book_duration)
    return result


# ── Specific designed behaviours ────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS)
def test_first_real_chapter_not_fooled_by_decoy(seed):
    """The real-world 'chapter 2' failure: a strong decoy silence ~6 s from the first
    real boundary must not capture chapter 1."""
    fx = make_front_matter_decoy(random.Random(seed))
    result = _align(fx)

    gt = fx.ground_truth[1]
    assert gt is not None
    assert abs(result[1]["timestamp"] - gt) <= 0.05, (
        f"seed {seed}: chapter 1 landed on {result[1]['timestamp']:.2f}, expected {gt:.2f} (decoy at {gt - 6.0:.2f})"
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_missing_chapter_is_guessed_not_stolen(seed):
    """A reference chapter with no real boundary is flagged as a guess, and its
    neighbours stay correct."""
    fx = make_missing_chapter(random.Random(seed))
    # The builder nulls the missing chapter's ground truth; recover its index.
    missing = next(i for i, gt in enumerate(fx.ground_truth) if gt is None and i != 0)
    result = _align(fx)
    score = score_alignment(result, fx.ground_truth)

    assert result[missing]["is_guess"], f"seed {seed}: missing chapter {missing} not flagged as a guess"
    assert missing - 1 not in score.wrong and missing + 1 not in score.wrong, (
        f"seed {seed}: a neighbour of the missing chapter was misplaced ({score.wrong})"
    )
    assert score.accuracy >= 0.95


def test_no_cues_falls_back_to_duration_scaling():
    """With no detected cues the aligner still returns one entry per chapter."""
    fx = SYNTHETIC_BUILDERS["linear_drift"](random.Random(0))
    aligner = ChapterAligner()
    result, _ = aligner.align(fx.ref_chapters, [], fx.ref_duration, fx.book_duration)
    assert len(result) == len(fx.ref_chapters)
    assert all(r["is_guess"] for r in result[1:])


def test_empty_reference_returns_empty():
    aligner = ChapterAligner()
    result, _ = aligner.align([], [], 100.0, 100.0)
    assert result == []


# ── Regression gate ─────────────────────────────────────────────────────────────


def _score_case(fx: Fixture) -> dict:
    """Over chapters that have a detected cue at their ground-truth boundary (the matchable
    ones): how many the aligner placed within tolerance, and how many it got wrong while
    asserting confidence (``is_guess`` false)."""
    cue_times = [c.timestamp for c in fx.detected_cues]
    result = _align(fx)
    matchable = correct = confident_wrong = 0
    for i, gt in enumerate(fx.ground_truth):
        if gt is None or not any(abs(c - gt) <= 0.1 for c in cue_times):
            continue
        matchable += 1
        if abs(result[i]["timestamp"] - gt) <= SCORE_TOLERANCE:
            correct += 1
        elif not result[i]["is_guess"]:
            confident_wrong += 1
    return {"matchable": matchable, "correct": correct, "confident_wrong": confident_wrong}


def _scorecard() -> dict:
    cases = {}
    for scenario in SYNTHETIC_BUILDERS:
        for seed in SEEDS:
            cases[f"synthetic/{scenario}/{seed}"] = _score_case(SYNTHETIC_BUILDERS[scenario](random.Random(seed)))
    for fx in load_real_fixtures():
        cases[f"real/{fx.name}"] = _score_case(fx)
    return cases


def test_no_regression_vs_baseline(request):
    """Fail if any synthetic case or real fixture has fewer correct or more confident-wrong
    placements than the committed baseline. Regenerate after an intentional change with
    ``uv run pytest tests/realignment/test_chapter_aligner.py --update-aligner-baseline`` and review the
    diff before committing."""
    current = _scorecard()

    if request.config.getoption("--update-aligner-baseline"):
        payload = {"tolerance": SCORE_TOLERANCE, "cases": current}
        BASELINE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"regenerated {BASELINE_PATH.name} ({len(current)} cases)")

    if not BASELINE_PATH.exists():
        pytest.fail(f"{BASELINE_PATH.name} is missing — create it with: pytest --update-aligner-baseline")

    baseline = json.loads(BASELINE_PATH.read_text())["cases"]
    regressions = []
    for name, base in sorted(baseline.items()):
        cur = current.get(name)
        if cur is None:
            regressions.append(f"{name}: in baseline but missing from this run")
            continue
        if cur["correct"] < base["correct"]:
            regressions.append(f"{name}: correct {cur['correct']} < baseline {base['correct']}")
        if cur["confident_wrong"] > base["confident_wrong"]:
            regressions.append(f"{name}: confident_wrong {cur['confident_wrong']} > baseline {base['confident_wrong']}")

    assert not regressions, "Aligner regressed vs baseline (regenerate if intentional):\n  " + "\n  ".join(regressions)
