"""Tests for transcription-enhanced realignment (app/services/realign_verification.py).

The verifier is driven by a simulated transcriber that knows each fixture's ground truth: a
snippet starting at a chapter's true start announces its title (optionally after a preamble);
anywhere else it is story text. That isolates the search/pin/concede logic from ASR quality,
which the matcher's own tests (test_title_matching.py, real Whisper output) cover.
"""

import random
from typing import Dict, List, Optional, Tuple

import pytest
from realignment_helpers import (
    SYNTHETIC_BUILDERS,
    Fixture,
    cues_in_regions,
    extraction_regions,
    load_real_fixtures,
    make_clean,
    make_parallel_decoy_chain,
    production_padding,
    score_alignment,
)

from app.api.routes.chapters import BasicChapter, DetectedCue
from app.services.chapter_aligner import ChapterAligner
from app.services.realign_verification import (
    CALIBRATION_SAMPLE,
    CALIBRATION_TRIES,
    MAX_TRANSCRIPTIONS_PER_CHAPTER,
    RealignVerifier,
)

REAL_FIXTURES = load_real_fixtures()
SEEDS = [1, 2, 3, 7, 11]

_STORY = "the rain fell softly across the valley as she walked toward the old house remembering".split()
_UNITS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split()
_UNITS += "sixteen seventeen eighteen nineteen".split()
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _spoken(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else f" {_UNITS[n % 10]}")
    return str(n)


def _titles(n: int) -> List[str]:
    return ["Opening Credits"] + [f"Chapter {i}" for i in range(1, n)]


class SimulatedAudio:
    """What a transcriber hears at a snippet start, from a fixture's ground truth."""

    def __init__(
        self,
        fx: Fixture,
        spoken: bool = True,
        preambles: Optional[Dict[int, Tuple[str, float]]] = None,
        announcements: Optional[Dict[int, str]] = None,
        spots: Optional[Dict[float, str]] = None,
    ):
        self.gt = fx.ground_truth
        self.spoken = spoken
        # Exact times -> what is heard there, overriding everything else
        self.spots = spots or {}
        # chapter -> what is heard at its start instead of "Chapter N"
        self.announcements = announcements or {}
        # chapter -> (preamble text heard at its true start, seconds until its title is heard)
        self.preambles = preambles or {}
        self.rng = random.Random(0)
        self.calls = 0

    def hear(self, t: float) -> str:
        story = " ".join(self.rng.choice(_STORY) for _ in range(self.rng.randint(4, 9)))
        for spot, text in self.spots.items():
            if abs(t - spot) <= 0.4:
                return text
        for j, g in enumerate(self.gt):
            if j == 0 or g is None or not self.spoken:
                continue
            title = f"{self.announcements.get(j, f'Chapter {_spoken(j)}')}. {story}"
            if j in self.preambles:
                text, delay = self.preambles[j]
                if abs(t - g) <= 0.4:
                    return text
                if abs(t - (g + delay)) <= 0.4:
                    return title
            elif abs(t - g) <= 0.4:
                return title
        return story

    async def transcribe(self, times: List[float]) -> List[Optional[str]]:
        self.calls += len(times)
        return [self.hear(t) for t in times]


def _first_pass(fx: Fixture, padding: Optional[float] = None, titles: Optional[Dict[int, str]] = None):
    pad = production_padding(fx) if padding is None else padding
    regions = extraction_regions([c.timestamp for c in fx.ref_chapters], fx.book_duration, pad)
    cues = cues_in_regions(fx.detected_cues, regions)
    names = _titles(len(fx.ref_chapters))
    for i, title in (titles or {}).items():
        names[i] = title
    ref = [BasicChapter(timestamp=c.timestamp, title=t) for c, t in zip(fx.ref_chapters, names)]
    initial, _ = ChapterAligner(max_drift=pad).align(
        ref, cues, fx.ref_duration, fx.book_duration, scanned_regions=regions
    )
    return ref, cues, regions, pad, initial


def _fixture_scan(fx: Fixture, log: Optional[List[Tuple[float, float]]] = None):
    """Expansion scanning: reveals the fixture's own cues inside the requested regions."""

    async def scan(regions):
        if log is not None:
            log.extend(regions)
        return [c for c in fx.detected_cues if any(s <= c.timestamp <= e for s, e in regions)]

    return scan


async def _verify(
    fx: Fixture,
    audio: SimulatedAudio,
    padding: Optional[float] = None,
    scan=None,
    should_stop=None,
    titles: Optional[Dict[int, str]] = None,
):
    ref, cues, regions, pad, initial = _first_pass(fx, padding, titles)
    verifier = RealignVerifier(
        ref,
        cues,
        fx.ref_duration,
        fx.book_duration,
        pad,
        regions,
        audio.transcribe,
        scan or _fixture_scan(fx),
        should_stop=should_stop or (lambda: False),
    )
    return initial, await verifier.run(initial)


def _placements(outcome):
    return [{"timestamp": c.timestamp, "is_guess": c.is_guess} for c in outcome.chapters]


def _cases():
    return REAL_FIXTURES + [SYNTHETIC_BUILDERS[name](random.Random(s)) for name in SYNTHETIC_BUILDERS for s in SEEDS]


async def test_spoken_titles_fix_alignment_errors():
    """Over every case, verification never leaves a book worse, removes nearly all errors and
    nearly all unflagged (confidently wrong) placements, and stays near one transcription per
    chapter."""
    before_wrong = after_wrong = before_unflagged = after_unflagged = 0
    for fx in _cases():
        audio = SimulatedAudio(fx)
        initial, outcome = await _verify(fx, audio)
        before = score_alignment(initial, fx.ground_truth)
        after = score_alignment(_placements(outcome), fx.ground_truth)
        assert len(after.wrong) <= len(before.wrong), f"{fx.name}: {before.wrong} -> {after.wrong}"
        assert outcome.transcriptions <= MAX_TRANSCRIPTIONS_PER_CHAPTER * len(fx.ref_chapters) + 10
        before_wrong += len(before.wrong)
        after_wrong += len(after.wrong)
        before_unflagged += len(before.confident_wrong)
        after_unflagged += len(after.confident_wrong)
    assert after_wrong * 10 <= before_wrong, f"wrong placements {before_wrong} -> {after_wrong}"
    assert after_unflagged * 10 <= before_unflagged, f"confidently wrong {before_unflagged} -> {after_unflagged}"


@pytest.mark.parametrize("fx", REAL_FIXTURES[:12], ids=lambda fx: fx.name[-15:])
async def test_unspoken_titles_bail_out_and_change_nothing(fx):
    """When the narrator never reads the titles, calibration gives up after a few
    transcriptions and the cue-based alignment is kept untouched."""
    audio = SimulatedAudio(fx, spoken=False)
    initial, outcome = await _verify(fx, audio)
    assert outcome.titles_not_spoken
    assert outcome.transcriptions <= CALIBRATION_SAMPLE * CALIBRATION_TRIES
    assert [c.timestamp for c in outcome.chapters] == [r["timestamp"] for r in initial]
    assert [c.is_guess for c in outcome.chapters] == [r["is_guess"] for r in initial]
    assert not any(c.verified for c in outcome.chapters)


async def test_parallel_decoy_chain_is_fixed():
    """The aligner's known limit — a louder pause just after every title in a run, forming a
    decoy chain with the same spacing — is resolved by hearing where the titles are."""
    for seed in SEEDS:
        fx, _, _ = make_parallel_decoy_chain(random.Random(seed))
        initial, outcome = await _verify(fx, SimulatedAudio(fx), padding=15.0)
        assert score_alignment(initial, fx.ground_truth).wrong, f"seed {seed}: decoy chain not reproduced"
        assert score_alignment(_placements(outcome), fx.ground_truth).wrong == [], f"seed {seed}"


async def test_preamble_keeps_the_chapter_start():
    """End credits (or a part heading) before a chapter's title: the chapter starts at the
    preamble, not at the later title announcement."""
    fx = make_clean(random.Random(5))
    k = 10
    title_cue = fx.ground_truth[k] + 6.0
    fx.detected_cues = sorted(fx.detected_cues + [DetectedCue(timestamp=title_cue, gap=1.4)], key=lambda c: c.timestamp)
    audio = SimulatedAudio(fx, preambles={k: ("This book was read by Jane Doe", 6.0)})

    _, outcome = await _verify(fx, audio)

    assert outcome.chapters[k].timestamp == pytest.approx(fx.ground_truth[k], abs=0.05)
    assert outcome.chapters[k].verified


async def test_story_before_a_late_title_moves_the_chapter():
    """The same shape without a preamble — story text, then the title a few seconds later —
    means the placement was too early: the chapter moves to the title."""
    fx = make_clean(random.Random(5))
    k = 10
    true_start = fx.ground_truth[k] + 6.0
    fx.detected_cues = sorted(
        fx.detected_cues + [DetectedCue(timestamp=true_start, gap=1.4)], key=lambda c: c.timestamp
    )
    fx.ground_truth[k] = true_start  # the "true" start is the later cue; the original one is a pause before it
    audio = SimulatedAudio(fx)

    _, outcome = await _verify(fx, audio)

    assert outcome.chapters[k].timestamp == pytest.approx(true_start, abs=0.05)
    assert outcome.chapters[k].verified


async def test_finish_now_keeps_confirmed_chapters():
    fx = (
        next(f for f in REAL_FIXTURES if len(f.ref_chapters) > 60)
        if REAL_FIXTURES
        else make_clean(random.Random(1), 80)
    )
    audio = SimulatedAudio(fx)
    _, outcome = await _verify(fx, audio, should_stop=lambda: audio.calls >= 20)

    verified = sum(c.verified for c in outcome.chapters)
    assert 0 < verified < len(fx.ref_chapters) - 2
    assert outcome.transcriptions <= 20 + 8


async def test_expansion_scans_unscanned_audio():
    """Boundaries shifted beyond the first pass's coverage (and missed by the aligner's own
    expansion signal) are found by scanning the unscanned part of their search area."""
    fixed = 0
    for seed in SEEDS:
        fx = SYNTHETIC_BUILDERS["offsetting_shift"](random.Random(seed))
        scanned: List[Tuple[float, float]] = []
        initial, outcome = await _verify(fx, SimulatedAudio(fx), padding=15.0, scan=_fixture_scan(fx, scanned))
        before = score_alignment(initial, fx.ground_truth)
        after = score_alignment(_placements(outcome), fx.ground_truth)
        assert len(after.wrong) <= len(before.wrong)
        if before.wrong and not after.wrong and scanned:
            fixed += 1
    assert fixed >= 3, f"expansion recovered only {fixed} of {len(SEEDS)} shifted books"


def test_a_transcript_goes_to_the_best_matching_title():
    """Neighbouring titles that share words ("A Request", "A Request II"):
    when one chapter's search lands on another's start and hears "Request 2", that confirms
    both titles, but belongs to the closer match — not to whichever neighbour is checked first."""
    fx = make_clean(random.Random(3))
    titles = {7: "A Request", 8: "A Request II", 9: "A Request III"}
    ref, cues, regions, pad, initial = _first_pass(fx, titles=titles)
    verifier = RealignVerifier(
        ref, cues, fx.ref_duration, fx.book_duration, pad, regions, SimulatedAudio(fx).transcribe
    )
    verifier.placements = initial
    start_8 = fx.ground_truth[8]
    assert start_8 is not None
    verifier.heard[start_8] = "Request 2. The rain fell softly across the valley"
    # An off-by-one placement left chapter 7 within reach of chapter 8's start
    verifier.placements[7] = {**initial[7], "timestamp": start_8 - 20.0}

    verifier._evaluate(9, start_8)

    assert verifier.pins == {8: start_8}


def test_a_neighbour_is_only_confirmed_within_its_own_reach():
    """A snippet can't confirm a neighbouring chapter whose own placement is far away — the
    example failure: "Request 2" at a chapter's start pinned "A Request" 11 minutes late."""
    fx = make_clean(random.Random(3))
    titles = {7: "A Request", 8: "Ambush"}
    ref, cues, regions, pad, initial = _first_pass(fx, titles=titles)
    verifier = RealignVerifier(
        ref, cues, fx.ref_duration, fx.book_duration, pad, regions, SimulatedAudio(fx).transcribe
    )
    verifier.placements = initial
    start_8 = fx.ground_truth[8]
    assert start_8 is not None
    verifier.heard[start_8] = "Request 2. The rain fell softly across the valley"

    verifier._evaluate(8, start_8)

    assert 7 not in verifier.pins


@pytest.mark.parametrize("garbled", [False, True], ids=["clear", "garbled"])
async def test_a_number_said_before_a_pause_keeps_the_chapter_start(garbled):
    """ "Chapter Two." [pause] "John's Big Battle.": the pause leaves a louder cue 2 s into
    the chapter, where only the name is heard. The chapter belongs at the number, not 2 s late —
    even when ASR garbles the number (e.g. Parakeet output: "CHAPTER FORTY THRIENDING" for 43)."""
    fx = make_clean(random.Random(9), n=30)
    titles, spots, extra = {}, {}, []
    for k in (23, 25, 27):
        start = fx.ground_truth[k]
        assert start is not None
        titles[k] = f"Chapter {k}: The Long Night"
        spots[start] = f"CHAPTER {_spoken(k).split()[0].upper()} THRIENDING" if garbled else f"Chapter {_spoken(k)}"
        spots[start + 2.0] = "The long night. The rain fell softly"
        extra.append(DetectedCue(timestamp=start + 2.0, gap=6.0))
    fx.detected_cues = sorted(fx.detected_cues + extra, key=lambda c: c.timestamp)

    _, outcome = await _verify(fx, SimulatedAudio(fx, spots=spots), titles=titles)

    for k in titles:
        assert outcome.chapters[k].verified, f"chapter {k} not confirmed"
        assert outcome.chapters[k].timestamp == pytest.approx(fx.ground_truth[k], abs=0.05), f"chapter {k}"


async def test_titles_whose_numbers_are_never_spoken_are_confirmed():
    """A narrator who reads only the words ("Chapter 3 (The mind of man is holy…)" read as its
    epigraph): with no number announced just before, the words-only spot is the start."""
    fx = make_clean(random.Random(9))
    n = len(fx.ref_chapters)
    titles = {k: f"Chapter {k} (The {_STORY[k % len(_STORY)]} of the valley)" for k in range(1, n)}
    spots = {}
    for k in range(1, n):
        start = fx.ground_truth[k]
        assert start is not None
        spots[start] = f"The {_STORY[k % len(_STORY)]} of the valley. She walked on"

    _, outcome = await _verify(fx, SimulatedAudio(fx, spots=spots), titles=titles)

    assert not outcome.titles_not_spoken
    assert sum(c.verified for c in outcome.chapters) >= n - 2
    assert score_alignment(_placements(outcome), fx.ground_truth).wrong == []


def test_two_titles_in_one_breath_belong_to_the_first():
    """Sample output: a part heading and its first chapter read together — "Heracles, the line of
    Perseus". It confirms "The Line of Perseus" better, but the snippet starts with "Heracles",
    so it is that chapter's start; "The Line of Perseus" begins a moment later."""
    fx = make_clean(random.Random(3))
    titles = {7: "Heracles", 8: "The Line of Perseus"}
    ref, cues, regions, pad, initial = _first_pass(fx, titles=titles)
    verifier = RealignVerifier(
        ref, cues, fx.ref_duration, fx.book_duration, pad, regions, SimulatedAudio(fx).transcribe
    )
    verifier.placements = initial
    start_7 = fx.ground_truth[7]
    assert start_7 is not None
    verifier.placements[8] = {**initial[8], "timestamp": start_7 + 10.0}
    verifier.heard[start_7] = "Heracles, the line of Perseus"

    verifier._evaluate(7, start_7)

    assert verifier.pins == {7: start_7}
