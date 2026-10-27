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
from typing import Optional

import pytest
from realignment_helpers import (
    SYNTHETIC_BUILDERS,
    Fixture,
    cues_in_regions,
    extraction_regions,
    load_real_fixtures,
    make_clean,
    make_front_matter_decoy,
    make_missing_chapter,
    make_parallel_decoy_chain,
    production_padding,
    score_alignment,
)

from app.core.constants import REALIGN_PADDING_DEFAULT, REALIGN_PADDING_EXPANDED
from app.services.chapter_aligner import FIXED_CUE_EXCLUSION, ChapterAligner

# Seeds give us a handful of distinct books per scenario while staying deterministic.
SEEDS = [1, 2, 3, 7, 11]

BASELINE_PATH = Path(__file__).parent / "realignment_baseline.json"
# A placement within this of ground truth counts as correct: wide of the 0.01s ground-truth
# quantization, far inside any decoy distance.
SCORE_TOLERANCE = 0.1

# Loaded once: fixtures are read-only test inputs shared by the gate and the
# expansion-signal tests below.
REAL_FIXTURES = load_real_fixtures()


def _first_pass(fx: Fixture, padding: Optional[float] = None):
    """Simulate a production realignment pass: detection only sees the cues inside the
    extraction regions for ``padding`` (the fixture's own capture padding by default), and
    the aligner is told which regions were scanned so it can request expansion."""
    pad = production_padding(fx) if padding is None else padding
    regions = extraction_regions([c.timestamp for c in fx.ref_chapters], fx.book_duration, pad)
    cues = cues_in_regions(fx.detected_cues, regions)
    aligner = ChapterAligner(max_drift=pad)
    result, stats = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, scanned_regions=regions)
    return result, stats, cues


def _align(fx: Fixture):
    return _first_pass(fx)[0]


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


# ── Expansion signal ────────────────────────────────────────────────────────────
# First-pass detection only scans ±padding around each reference timestamp; the aligner
# reports expansion_needed when a chapter ends up on no cue and part of its search window
# was never scanned. The pipeline then widens to REALIGN_PADDING_EXPANDED and re-runs once.


def _max_shift(fx: Fixture) -> float:
    refs = [c.timestamp for c in fx.ref_chapters]
    shifts = [abs(gt - refs[i]) for i, gt in enumerate(fx.ground_truth) if i > 0 and gt is not None]
    return max(shifts, default=0.0)


# Real fixtures with boundaries shifted >20s from the reference. Had these books paired a
# similar-duration reference (forcing the padding to its floor), the shifted boundaries
# would fall outside first-pass coverage — so they are the candidates for exercising the
# expansion signal on real cue data.
HIGH_SHIFT_FIXTURES = [fx for fx in REAL_FIXTURES if _max_shift(fx) > 20.0]

# A shifted region can be fully captured by a chain of decoy cues inside the scanned windows;
# nothing is left unplaced, so the signal cannot see it (documented limit in chapter_aligner.py).
# Strict xfail: starts failing if the aligner ever learns to catch it.
#   - 164638: decoy-masked even at production coverage.
#   - 192245: only its last two chapters shift (~20.8s), just past this test's forced 15s floor,
#     and a decoy grabs them. Its real production padding is 31.5s (durdiff-driven), which covers
#     those shifts — it aligns 20/20 in production and never actually needs expansion; it appears
#     here only because the test artificially forces the floor.
EXPANSION_BLIND_FIXTURES = {
    "realignment_fixture_20260606_164638",
    "realignment_fixture_20260612_192245",
}


def test_no_expansion_requested_at_production_coverage():
    """Zero false positives: at its production coverage no real fixture may request a wider
    scan when the pipeline would honour it (padding below the expanded value), since an
    expansion re-runs the whole extraction/detection pass."""
    fired = []
    for fx in REAL_FIXTURES:
        if production_padding(fx) >= REALIGN_PADDING_EXPANDED:
            continue  # pipeline ignores the signal once padding is already at/above expanded
        _, stats, _ = _first_pass(fx)
        if stats["expansion_needed"]:
            fired.append(fx.name)
    assert not fired, f"expansion requested at production coverage: {fired}"


@pytest.mark.parametrize("scenario", ["offsetting_shift", "tail_shift"])
@pytest.mark.parametrize("seed", SEEDS)
def test_shift_beyond_padding_triggers_expansion_and_recovers(scenario, seed):
    """Boundaries shifted beyond the default padding while total durations match (offsetting
    insertion/removal): invisible to the padding formula, so the first pass must request
    expansion, and the expanded pass must align without confident errors."""
    fx = SYNTHETIC_BUILDERS[scenario](random.Random(seed))

    _, stats, _ = _first_pass(fx, padding=REALIGN_PADDING_DEFAULT)
    assert stats["expansion_needed"], f"seed {seed}: first pass did not request expansion"

    result, _, _ = _first_pass(fx, padding=REALIGN_PADDING_EXPANDED)
    score = score_alignment(result, fx.ground_truth, tolerance=SCORE_TOLERANCE)
    assert not score.confident_wrong, f"seed {seed}: confident errors after expansion: {score.confident_wrong}"
    assert score.accuracy >= 0.85, f"seed {seed}: accuracy {score.accuracy:.2f} after expansion"


@pytest.mark.parametrize(
    "fx",
    [
        pytest.param(
            fx,
            id=fx.name,
            marks=(
                [pytest.mark.xfail(reason="decoy-masked shift: known expansion blind spot", strict=True)]
                if fx.name in EXPANSION_BLIND_FIXTURES
                else []
            ),
        )
        for fx in HIGH_SHIFT_FIXTURES
    ],
)
def test_expansion_fires_on_real_high_shift_fixtures(fx):
    """Each high-shift fixture, re-run as if its reference had a similar duration (padding at
    the floor, so the shifted boundaries sit outside coverage), must request expansion."""
    _, stats, _ = _first_pass(fx, padding=REALIGN_PADDING_DEFAULT)
    assert stats["expansion_needed"], f"{fx.name}: shifted boundaries outside coverage but no expansion requested"


# ── Pins (re-running realignment from the editor) ──────────────────────────────
# Pinned chapters are ground truth: returned exactly, and the skeleton chains through them. The
# behaviour gates below are aggregate because a pin changes the optimisation problem, so it can
# occasionally flip a borderline placement elsewhere; what must hold is a clear net benefit.


def _pin_inputs(fx: Fixture):
    pad = production_padding(fx)
    regions = extraction_regions([c.timestamp for c in fx.ref_chapters], fx.book_duration, pad)
    return ChapterAligner(max_drift=pad), cues_in_regions(fx.detected_cues, regions)


def _wrong(result, fx: Fixture) -> set:
    return set(score_alignment(result, fx.ground_truth, tolerance=SCORE_TOLERANCE).wrong)


@pytest.mark.parametrize("seed", SEEDS)
def test_pins_are_returned_as_ground_truth(seed):
    fx = SYNTHETIC_BUILDERS["per_chapter_jitter"](random.Random(seed))
    aligner, cues = _pin_inputs(fx)
    rng = random.Random(seed)
    pins = {i: fx.ref_chapters[i].timestamp + rng.uniform(-3.0, 3.0) for i in sorted(rng.sample(range(1, 20), 4))}

    result, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, pins=pins)

    for i, t in pins.items():
        assert result[i]["timestamp"] == t
        assert result[i]["confidence"] == 1.0 and not result[i]["is_guess"]
    times = [r["timestamp"] for r in result]
    assert times == sorted(times), "placements must stay in chapter order around the pins"


def test_out_of_order_pins_are_rejected():
    fx = make_clean(random.Random(0))
    aligner, cues = _pin_inputs(fx)
    t3, t5 = fx.ref_chapters[3].timestamp, fx.ref_chapters[5].timestamp
    with pytest.raises(ValueError):
        aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, pins={3: t5, 5: t3})


@pytest.mark.parametrize("seed", SEEDS)
def test_fixed_times_are_never_reused(seed):
    """A user-added chapter takes its boundary: with a fixed time on a true boundary, no
    reference chapter may land on (or within the exclusion distance of) it."""
    fx = make_clean(random.Random(seed))
    aligner, cues = _pin_inputs(fx)
    taken = fx.ref_chapters[7].timestamp

    result, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, fixed_times=[taken])

    assert all(abs(r["timestamp"] - taken) >= FIXED_CUE_EXCLUSION for r in result)


def test_pinning_both_ends_breaks_a_parallel_decoy_chain():
    """Across a run where a louder, equally-spaced decoy chain captures every chapter, pinning
    the run's two ends must correct most of it and leave everything outside the run alone."""
    unpinned_wrong = pinned_wrong = 0
    for seed in [1, 2, 3, 7, 11, 13, 17]:
        fx, first, last = make_parallel_decoy_chain(random.Random(seed))
        aligner, cues = _pin_inputs(fx)
        before, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration)
        pins = {first: fx.ground_truth[first], last: fx.ground_truth[last]}
        after, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, pins=pins)

        assert _wrong(before, fx) == set(range(first, last + 1)), f"seed {seed}: decoy chain not reproduced"
        assert _wrong(after, fx) <= set(range(first + 1, last)), f"seed {seed}: a pin disturbed the rest of the book"
        unpinned_wrong += len(_wrong(before, fx))
        pinned_wrong += len(_wrong(after, fx))
    assert pinned_wrong * 3 <= unpinned_wrong, f"pins fixed too little: {unpinned_wrong} -> {pinned_wrong} wrong"


def _pinning_cases():
    return REAL_FIXTURES + [SYNTHETIC_BUILDERS[name](random.Random(s)) for name in SYNTHETIC_BUILDERS for s in SEEDS]


def test_pinning_the_first_wrong_chapter_helps_more_than_it_hurts():
    """Simulate the editor workflow on every case: the user fixes (pins at ground truth) the
    first misplaced chapter and re-runs, up to three times. Re-running should correct further
    chapters on its own far more often than it disturbs ones that were already right."""
    auto_fixed = broke = 0
    for fx in _pinning_cases():
        aligner, cues = _pin_inputs(fx)
        result, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration)
        wrong, pins = _wrong(result, fx), {}
        for _ in range(3):
            if not wrong:
                break
            fix = min(wrong)
            pins[fix] = fx.ground_truth[fix]
            result, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, pins=pins)
            now = _wrong(result, fx)
            auto_fixed += len(wrong - {fix} - now)
            broke += len(now - wrong)
            wrong = now
    assert broke * 5 <= auto_fixed, f"re-run auto-fixed {auto_fixed} chapters but broke {broke}"


@pytest.mark.parametrize("n_pins", [1, 3])
def test_pinning_correct_chapters_helps_more_than_it_hurts(n_pins):
    """Users also pin chapters they've verified as right. Doing so should, on balance, fix
    other chapters rather than disturb them."""
    fixed = broke = 0
    rng = random.Random(42)
    for fx in _pinning_cases():
        aligner, cues = _pin_inputs(fx)
        result, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration)
        wrong = _wrong(result, fx)
        correct = [i for i in range(1, len(result)) if fx.ground_truth[i] is not None and i not in wrong]
        for _ in range(5):
            if len(correct) < n_pins:
                break
            pins = {i: fx.ground_truth[i] for i in rng.sample(correct, n_pins)}
            result, _ = aligner.align(fx.ref_chapters, cues, fx.ref_duration, fx.book_duration, pins=pins)
            now = _wrong(result, fx)
            fixed += len(wrong - now)
            broke += len(now - wrong)
    assert broke <= fixed, f"pinning correct chapters fixed {fixed} others but broke {broke}"


# ── Regression gate ─────────────────────────────────────────────────────────────


def _score_case(fx: Fixture) -> dict:
    """Over chapters that have a detected cue at their ground-truth boundary (the matchable
    ones): how many the aligner placed within tolerance, and how many it got wrong while
    asserting confidence (``is_guess`` false). Cues outside the production extraction
    coverage are excluded — detection would never have produced them."""
    result, _, cues = _first_pass(fx)
    cue_times = [c.timestamp for c in cues]
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
    for fx in REAL_FIXTURES:
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
