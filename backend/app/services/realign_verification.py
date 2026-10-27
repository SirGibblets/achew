"""Transcription-enhanced realignment: check aligned chapters by listening to them.

After the cue-based aligner places every reference chapter, this transcribes the start of the
audio at chosen placements and compares it with the chapter's title (``title_matching``). A
strong match confirms the placement and becomes a PIN, so the aligner re-runs around it (see
ChapterAligner's pins) and nearby placements improve before they are checked. A poor match
starts a search: the chapter's nearby cues are transcribed, nearest first, until one announces
the title. The search is bounded by the confirmed chapters on either side (the true start must
lie between them), and when its cues run out while part of that span was never scanned, the
missing audio is scanned for more cues (auto-expansion) before giving up.

It works in ROUNDS of a handful of transcriptions, re-aligning between rounds:

1. Calibration. The first round checks a few high-confidence chapters spread across the book.
   Those are almost certainly placed right, so if few of them match, this book doesn't read its
   reference titles aloud (the narrator just says "One", or the titles were invented by whoever
   made the reference). Verification stops there and the plain alignment is kept.
2. Then chapters are taken in an order that spreads confirmed anchors out quickly — the
   unchecked chapter farthest from any resolved one first — while searches continue one
   candidate per round.

Each transcript is also compared against neighbouring chapters' titles: hearing "Chapter 13" at
Chapter 12's placement confirms 13 there, and tells 12 to look elsewhere. A transcript that
confirms several titles goes to the best match, and only to a chapter whose own placement is
within reach of it. A title heard a little AFTER a placement whose snippet is a preamble (end
credits, a "Part Two" heading) keeps the chapter at the preamble; after story text it moves the
chapter to the title. A part/disc-break announcement sends the search to later cues first.

Chapters can be CONCEDED: titles that can't confirm anything (credits, "Track 3", blank) up
front, and titles never heard after the search and any expansion. A conceded chapter keeps its
cue-based placement; one whose title was searched for but never heard is flagged as a guess.

Pure orchestration: transcription, region scanning and progress are injected, so the loop can
be simulated in tests without audio.
"""

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.api.routes.chapters import BasicChapter, DetectedCue
from app.core.constants import REALIGN_PADDING_EXPANDED

from .chapter_aligner import ChapterAligner
from .title_matching import (
    TitleMatch,
    TitleProfile,
    announces_chapter,
    is_interruption,
    is_preamble,
    match_title,
    title_profile,
)

logger = logging.getLogger(__name__)

# A transcript confirms a title when at least this fraction of the title's weight is heard, in
# order, at the start of the snippet, with no conflicting chapter number. 0.75 rejected a real
# "The offspring of a Kidner and Tiphon" (0.73) for "The Offspring of Echidna and Typhon"; most of a
# multi-word title heard in order right at the start is already specific.
STRONG_MATCH_SCORE = 0.7

# A title heard after more than this many content words of other speech means the snippet began
# before the real chapter start (e.g. inside the previous chapter's last sentence), so the cue
# is too early to confirm. The next cue is tried first instead.
MAX_LEAD_WORDS = 2

# A weaker or late hearing of the title still says the chapter start is near and later.
PARTIAL_MATCH_SCORE = 0.5

# Some chapters open with speech before their title (end credits, a "Part Two" heading). When the
# title is heard at a cue within this many seconds AFTER the chapter's original placement, and
# that placement's own snippet sounds like such a preamble, the chapter starts at the preamble.
# Otherwise a later title means the placement was too early (e.g. a pause inside the previous
# chapter's last lines) and the chapter moves to the title. Silence length can't make this call:
# on the real fixtures the wrong early cue usually has the LONGER silence.
PREAMBLE_WINDOW = 20.0

# A title's words heard right at the start of a snippet without its number ("Johns's Big
# Battle" for "Chapter 2: John's Big Battle") is ambiguous. Some narrators never say the
# number, so this is the chapter start; others pause between "Chapter Two." and the name, which
# leaves a cue a couple of seconds INTO the chapter (2s late on three real books). The cues up to
# this many seconds earlier are checked first: one that announces the number is the real start;
# if none does, the words-only spot is.
NUMBER_LOOKBACK = 6.0

# Calibration: how many confident chapters the first rounds check, and what fraction must match
# for the book to count as one that reads its titles aloud. Each gets a few nearby cues before
# judging, so a badly misaligned book isn't mistaken for one whose titles aren't spoken.
CALIBRATION_SAMPLE = 6
CALIBRATION_TRIES = 3
CALIBRATION_MIN_MATCH_FRACTION = 1 / 3

# Transcriptions per round. Small enough that pins found in one round re-shape the alignment
# before the next round spends transcriptions on it.
ROUND_SIZE = 8

# Candidate cues tried for one chapter before its search area is expanded (or, if there is
# nothing left to scan, before it is conceded); and how many more after an expansion.
MAX_TRIES = 6
EXTRA_TRIES_AFTER_EXPANSION = 4

# Neighbouring chapters (each side) whose titles are also checked against every transcript.
CROSS_MATCH_SPAN = 3

# A chapter's candidates are cues within this distance of its current placement (and always
# between the confirmed chapters around it). Wide enough for the duration-mismatch drift the
# aligner itself allows.
MIN_SEARCH_REACH = 60.0

# Confirmed chapters must stay at least this far apart (the editor's minimum spacing).
MIN_SEPARATION = 1.0

# Unscanned audio shorter than this inside a search area isn't worth a scan.
MIN_SCAN_SECONDS = 2.0

# Overall budget, as transcriptions per chapter, so a book that matches badly can't run away.
MAX_TRANSCRIPTIONS_PER_CHAPTER = 3.0


def confirms_title(match: TitleMatch) -> bool:
    """Whether a transcript's match against a title confirms the chapter starts there, heard right
    at the start of the snippet and naming no other chapter number: most of the title, its own
    number, or every descriptive word with something misheard where the number goes. Evidence
    resting on a single word must also open the snippet as its own phrase."""
    if match.number_conflict or words_only(match):
        return False
    if match.score >= STRONG_MATCH_SCORE or match.announced_number:
        if match.single_word:
            return match.lead_words == 0 and match.standalone
        return match.lead_words <= MAX_LEAD_WORDS
    # "Fall Parliament of Owls": every word, and a word in the number's slot
    return (
        match.words_complete
        and match.content_words >= 2
        and match.lead_tokens >= 1
        and match.lead_words <= MAX_LEAD_WORDS
    )


def words_only(match: TitleMatch) -> bool:
    """A numbered title's words open the snippet but its number wasn't heard: provisional until
    the cues just before have been checked for the number (see NUMBER_LOOKBACK)."""
    if match.number_conflict or not match.numbered or match.number_heard or match.lead_tokens != 0:
        return False
    if not (match.words_complete or match.score >= STRONG_MATCH_SCORE):
        return False
    return match.content_words >= 2 or match.standalone


class ChapterStatus(str, Enum):
    PENDING = "pending"
    MATCHED = "matched"
    CONCEDED = "conceded"


@dataclass
class VerifiedChapter:
    timestamp: float
    confidence: float
    is_guess: bool
    # Confirmed by hearing its title; pinned in the editor
    verified: bool
    # What was heard at ``timestamp``, when that spot was transcribed
    transcript: str = ""


@dataclass
class VerificationProgress:
    resolved: int
    total: int
    matched: int
    message: str
    # Latest transcript line, for the progress feed
    feed_text: Optional[str] = None


@dataclass
class VerificationOutcome:
    chapters: List[VerifiedChapter]
    matched: int
    conceded: int
    transcriptions: int
    # The calibration round found the book doesn't read its titles aloud
    titles_not_spoken: bool
    # All cues, including any found by expansion scans
    cues: List[DetectedCue]
    scanned_regions: List[Tuple[float, float]]
    # Every transcript heard, keyed by snippet start time
    transcripts: Dict[float, str] = field(default_factory=dict)


Transcriber = Callable[[List[float]], Awaitable[List[Optional[str]]]]
RegionScanner = Callable[[List[Tuple[float, float]]], Awaitable[Optional[List[DetectedCue]]]]


@dataclass
class _ChapterState:
    profile: TitleProfile
    status: ChapterStatus
    tried: Set[float] = field(default_factory=set)
    # The first spot transcribed for this chapter: its cue-based placement
    first_try: Optional[float] = None
    max_tries: int = MAX_TRIES
    expanded: bool = False
    # A late/partial hearing of the title: the real start is probably after this time
    later_than: Optional[float] = None
    # Where the title's words were heard without its number; earlier cues are checked for the
    # number first (NUMBER_LOOKBACK)
    words_only_at: Optional[float] = None


class RealignVerifier:
    def __init__(
        self,
        ref_chapters: Sequence[BasicChapter],
        cues: Sequence[DetectedCue],
        ref_duration: float,
        book_duration: float,
        padding: float,
        scanned_regions: Sequence[Tuple[float, float]],
        transcribe: Transcriber,
        scan: Optional[RegionScanner] = None,
        on_progress: Callable[[VerificationProgress], Any] = lambda _: None,
        should_stop: Callable[[], bool] = lambda: False,
    ):
        self.ref = list(ref_chapters)
        self.cues = sorted(cues, key=lambda c: c.timestamp)
        self.ref_duration = ref_duration
        self.book_duration = book_duration
        self.padding = padding
        self.scanned = _merge(list(scanned_regions))
        self.transcribe = transcribe
        self.scan = scan
        self.on_progress = on_progress
        self.should_stop = should_stop
        self.aligner = ChapterAligner(max_drift=padding)
        self.heard: Dict[float, str] = {}
        self.pins: Dict[int, float] = {}
        self.transcriptions = 0
        self.budget = int(MAX_TRANSCRIPTIONS_PER_CHAPTER * len(self.ref)) + 10
        self.state: List[_ChapterState] = []
        for i, chapter in enumerate(self.ref):
            profile = title_profile(chapter.title)
            status = ChapterStatus.PENDING if i > 0 and profile.verifiable else ChapterStatus.CONCEDED
            self.state.append(_ChapterState(profile=profile, status=status))
        # Chapter 0 is fixed at 0:00; it counts as resolved
        if self.state:
            self.state[0].status = ChapterStatus.MATCHED
        self.placements: List[Dict[str, Any]] = []

    # ── public ──────────────────────────────────────────────────────────────

    async def run(self, initial: List[Dict[str, Any]]) -> VerificationOutcome:
        self.placements = initial
        titles_not_spoken = False
        self._report("Checking chapter titles…")

        sample = self._calibration_sample()
        if sample:
            needed = max(1, math.ceil(len(sample) * CALIBRATION_MIN_MATCH_FRACTION))
            for _ in range(CALIBRATION_TRIES):
                batch = [
                    (i, t)
                    for i in sample
                    if self.state[i].status == ChapterStatus.PENDING
                    for t in [self._next_candidate(i)]
                    if t is not None
                ]
                if not batch or self._heard_titles() >= needed or self.should_stop():
                    break
                await self._run_batch(batch)
                self._resolve_words_only()
            if self._heard_titles() < needed and not self.should_stop():
                logger.info(f"Realign verification: {self._heard_titles()}/{len(sample)} titles heard; not spoken")
                titles_not_spoken = True
                # Any lone "match" in a book that doesn't announce its titles is a coincidence
                self.pins.clear()
                for i in range(1, len(self.state)):
                    self.state[i].status = ChapterStatus.CONCEDED
            self._realign()

        while not titles_not_spoken and self._pending() and not self.should_stop():
            if self.transcriptions >= self.budget:
                logger.info("Realign verification: transcription budget spent")
                break
            # An empty batch means every pending chapter is out of candidates, which the
            # expand-or-concede step below always resolves, so the loop makes progress.
            batch = self._next_batch()
            if batch:
                await self._run_batch(batch)
            await self._expand_or_concede()
            self._realign()

        return self._outcome(titles_not_spoken)

    # ── rounds ──────────────────────────────────────────────────────────────

    def _calibration_sample(self) -> List[int]:
        """A few confident chapters spread evenly across the book."""
        confident = [
            i
            for i in self._pending()
            if not self.placements[i]["is_guess"] and self.placements[i]["confidence"] >= 0.75
        ]
        if not confident:
            confident = self._pending()
        k = min(CALIBRATION_SAMPLE, len(confident))
        if k == 0:
            return []
        return list(dict.fromkeys(confident[round(j * (len(confident) - 1) / max(1, k - 1))] for j in range(k)))

    def _next_batch(self) -> List[Tuple[int, float]]:
        """Searching chapters continue one candidate each; the rest of the round goes to the
        unchecked chapters farthest from anything already resolved, so confirmed anchors spread
        across the book early."""
        searching = [i for i in self._pending() if self.state[i].tried]
        unchecked = [i for i in self._pending() if not self.state[i].tried]
        resolved = [i for i, s in enumerate(self.state) if s.status != ChapterStatus.PENDING] + [len(self.ref)]
        unchecked.sort(key=lambda i: (-min(abs(i - r) for r in resolved), self.placements[i]["confidence"]))

        batch: List[Tuple[int, float]] = []
        times: Set[float] = set()
        for i in searching + unchecked:
            if len(batch) >= ROUND_SIZE:
                break
            t = self._next_candidate(i)
            if t is None or t in times:
                continue
            batch.append((i, t))
            times.add(t)
        return batch

    async def _run_batch(self, batch: List[Tuple[int, float]]) -> None:
        todo = sorted({t for _, t in batch if t not in self.heard})
        if todo:
            transcripts = await self.transcribe(todo)
            self.transcriptions += len(todo)
            for t, text in zip(todo, transcripts):
                if text is not None:
                    self.heard[t] = text

        for i, t in batch:
            if t not in self.heard:
                continue  # aborted (finish/cancel) before it was transcribed; not a real try
            if self.state[i].first_try is None:
                self.state[i].first_try = t
            self.state[i].tried.add(t)
            if self.state[i].status != ChapterStatus.PENDING:
                continue  # resolved by an earlier transcript in this batch (cross-match)
            self._evaluate(i, t)

    def _evaluate(self, i: int, t: float) -> None:
        """Judge the transcript at ``t`` for chapter ``i``, and for its pending neighbours: a
        snippet can announce a neighbouring chapter instead (an off-by-one placement). When it
        confirms several titles, it belongs to the best match — "A Request" is confirmed by
        "Request 2", but "A Request II" matches it better."""
        text = self.heard.get(t, "")
        state = self.state[i]
        if (
            state.words_only_at is not None
            and t < state.words_only_at
            and announces_chapter(text)
            and self._fits(i, t)
            and self._within_reach(i, t)
        ):
            # Looking back from where the title's words were heard: a chapter announcement just
            # before them is the start, even when ASR garbled the number ("CHAPTER FORTY
            # THRIENDING…" for Forty-Three, "Chapter 11" for One Hundred Eleven)
            self._confirm(i, t, text)
            return

        own = match_title(text, state.profile)
        best: Optional[Tuple[float, int, TitleMatch]] = None
        for j in range(max(1, i - CROSS_MATCH_SPAN), min(len(self.ref), i + CROSS_MATCH_SPAN + 1)):
            if self.state[j].status != ChapterStatus.PENDING:
                continue
            match = own if j == i else match_title(text, self.state[j].profile)
            if not confirms_title(match) or not self._fits(j, t) or not self._within_reach(j, t):
                continue
            # Ties go to the chapter this spot was transcribed for
            score = match.score + (match.announced_number and 1.0) + (j == i and 1e-6)
            if best is None or score > best[0]:
                best = (score, j, match)

        if best is not None:
            j = self._earlier_title_in_snippet(best[1], best[2], text, t)
            self._confirm(j, self._preamble_start(j, t) if j == i else t, text)
            self.state[j].tried.add(t)
            if j == i:
                return

        if state.words_only_at is None and words_only(own) and self._fits(i, t) and self._within_reach(i, t):
            # A cue just before that was already heard (e.g. this chapter's own placement, tried
            # first) may be the announcement; untried ones are checked next (_next_candidate)
            for earlier in sorted((h for h in self.heard if t - NUMBER_LOOKBACK <= h < t), reverse=True):
                if announces_chapter(self.heard[earlier]) and self._fits(i, earlier) and self._within_reach(i, earlier):
                    self._confirm(i, earlier, self.heard[earlier])
                    return
            state.words_only_at = t
            self._report(None, feed=f"? {self._label(i)} — “{_clip(text)}” (checking just before)")
            return

        if (own.score >= PARTIAL_MATCH_SCORE and own.lead_words > MAX_LEAD_WORDS) or is_interruption(text):
            # The title is (probably) still to come: heard late in this snippet, or this is a
            # part/disc-break announcement that precedes the next chapter
            self.state[i].later_than = t
        self._report(None, feed=f"✗ {self._label(i)} — “{_clip(text)}”" if text else None)

    def _earlier_title_in_snippet(self, j: int, match: TitleMatch, text: str, t: float) -> int:
        """Chapter ``j``'s title was heard after something; when that something is the previous
        chapter's title ("Heracles, the line of Perseus" — a part heading and its first chapter in
        one breath), the snippet starts with the previous chapter, so it belongs to that one."""
        k = j - 1
        if match.lead_tokens == 0 or k < 1 or self.state[k].status != ChapterStatus.PENDING:
            return j
        prev = match_title(text, self.state[k].profile)
        opens = prev.lead_tokens == 0 and prev.score >= STRONG_MATCH_SCORE and not prev.number_conflict
        return k if opens and self._fits(k, t) and self._within_reach(k, t) else j

    def _within_reach(self, i: int, t: float) -> bool:
        return abs(t - float(self.placements[i]["timestamp"])) <= self._reach()

    def _preamble_start(self, i: int, t: float) -> float:
        """Where chapter ``i`` starts given its title was heard at ``t``: its original placement
        when that came shortly before ``t`` and sounds like a preamble, otherwise ``t``."""
        first = self.state[i].first_try
        if first is None or not 0 < t - first <= PREAMBLE_WINDOW or not self._fits(i, first):
            return t
        return first if is_preamble(self.heard.get(first, "")) else t

    def _confirm(self, i: int, t: float, text: str) -> None:
        self.state[i].status = ChapterStatus.MATCHED
        self.pins[i] = t
        self._report(None, feed=f"✓ {self._label(i)} — “{_clip(text)}”")

    # ── candidates and search areas ─────────────────────────────────────────

    def _bounds(self, i: int) -> Tuple[float, float]:
        """The span chapter ``i`` must start in: after the confirmed chapter before it and
        before the confirmed chapter after it (chapter 0 at 0:00 and the book's end otherwise)."""
        lo = max((t for k, t in self.pins.items() if k < i), default=0.0)
        hi = min((t for k, t in self.pins.items() if k > i), default=self.book_duration)
        return lo + MIN_SEPARATION, hi - MIN_SEPARATION

    def _fits(self, i: int, t: float) -> bool:
        lo, hi = self._bounds(i)
        return lo <= t <= hi and all(abs(t - p) >= MIN_SEPARATION for p in self.pins.values())

    def _reach(self) -> float:
        return max(MIN_SEARCH_REACH, self.padding, abs(self.book_duration - self.ref_duration) * 2.0)

    def _next_candidate(self, i: int) -> Optional[float]:
        """The next untried cue for chapter ``i``: its placement first, then the nearest cues
        around it inside its bounds, later cues first once the title was heard late."""
        state = self.state[i]
        if len(state.tried) >= state.max_tries:
            return None
        lo, hi = self._bounds(i)
        expected = float(self.placements[i]["timestamp"])
        reach = self._reach()
        taken = set(self.pins.values())

        def usable(t: float) -> bool:
            return lo <= t <= hi and t not in state.tried and all(abs(t - p) >= MIN_SEPARATION for p in taken)

        if state.words_only_at is not None:
            # Only the cues just before the words-only spot, latest first
            heard_at = state.words_only_at
            before = [c.timestamp for c in self.cues if heard_at - NUMBER_LOOKBACK <= c.timestamp < heard_at]
            before = [t for t in before if usable(t)]
            return max(before) if before else None

        candidates = [c.timestamp for c in self.cues if abs(c.timestamp - expected) <= reach and usable(c.timestamp)]
        if not candidates:
            return None
        if state.later_than is not None:
            later = [t for t in candidates if t > state.later_than]
            if later:
                return min(later)
        return min(candidates, key=lambda t: abs(t - expected))

    async def _expand_or_concede(self) -> None:
        """Resolve chapters that ran out of candidates: scan unscanned audio in their search
        area for more cues (once per chapter), or concede them."""
        self._resolve_words_only()
        stuck = [i for i in self._pending() if self._next_candidate(i) is None]
        if not stuck:
            return

        regions: List[Tuple[float, float]] = []
        for i in stuck:
            state = self.state[i]
            lo, hi = self._bounds(i)
            expected = float(self.placements[i]["timestamp"])
            area = (max(lo, expected - REALIGN_PADDING_EXPANDED), min(hi, expected + REALIGN_PADDING_EXPANDED))
            gaps = [g for g in _subtract(area, self.scanned) if g[1] - g[0] >= MIN_SCAN_SECONDS]
            if self.scan is not None and not state.expanded and gaps:
                state.expanded = True
                state.max_tries = len(state.tried) + EXTRA_TRIES_AFTER_EXPANSION
                regions.extend(gaps)
            else:
                state.status = ChapterStatus.CONCEDED
                self._report(None)

        if regions and self.scan is not None:
            regions = _merge(regions)
            self._report("Scanning more of the audio for chapter cues…")
            found = await self.scan(regions)
            self.scanned = _merge(self.scanned + regions)
            if found:
                known = [c.timestamp for c in self.cues]
                added = [c for c in found if all(abs(c.timestamp - k) >= 0.75 for k in known)]
                self.cues = sorted(self.cues + added, key=lambda c: c.timestamp)
                logger.info(f"Realign verification: expansion scanned {len(regions)} regions, {len(added)} new cues")

    def _resolve_words_only(self) -> None:
        """Confirm words-only spots once no cue just before them announced the number."""
        for i in self._pending():
            heard_at = self.state[i].words_only_at
            if heard_at is not None and self._next_candidate(i) is None and self._fits(i, heard_at):
                self._confirm(i, heard_at, self.heard.get(heard_at, ""))

    # ── alignment ───────────────────────────────────────────────────────────

    def _realign(self) -> None:
        self.placements, _ = self.aligner.align(
            self.ref,
            self.cues,
            self.ref_duration,
            self.book_duration,
            scanned_regions=self.scanned,
            pins={i: t for i, t in self.pins.items() if i > 0},
        )

    def _outcome(self, titles_not_spoken: bool) -> VerificationOutcome:
        self._realign()
        chapters = []
        for i, placed in enumerate(self.placements):
            t = float(placed["timestamp"])
            state = self.state[i]
            heard = self.heard.get(t, "")
            if i in self.pins:
                chapters.append(VerifiedChapter(t, 1.0, False, True, heard))
                continue
            # Searched for but never heard: the cue-based placement is only an estimate
            searched = bool(state.tried) and not titles_not_spoken
            chapters.append(
                VerifiedChapter(
                    t,
                    min(float(placed["confidence"]), 0.35) if searched else float(placed["confidence"]),
                    bool(placed["is_guess"]) or searched,
                    False,
                    heard,
                )
            )
        return VerificationOutcome(
            chapters=chapters,
            matched=self._heard_titles(),
            conceded=sum(1 for i, s in enumerate(self.state) if i > 0 and s.status == ChapterStatus.CONCEDED),
            transcriptions=self.transcriptions,
            titles_not_spoken=titles_not_spoken,
            cues=self.cues,
            scanned_regions=self.scanned,
            transcripts=dict(self.heard),
        )

    # ── bookkeeping ─────────────────────────────────────────────────────────

    def _pending(self) -> List[int]:
        return [i for i, s in enumerate(self.state) if s.status == ChapterStatus.PENDING]

    def _heard_titles(self) -> int:
        return len(self.pins)

    def _label(self, i: int) -> str:
        return self.ref[i].title.strip() or f"Chapter {i + 1}"

    def _report(self, message: Optional[str], feed: Optional[str] = None) -> None:
        total = len(self.ref)
        resolved = sum(1 for s in self.state if s.status != ChapterStatus.PENDING)
        matched = self._heard_titles()
        self.on_progress(
            VerificationProgress(
                resolved=resolved,
                total=total,
                matched=matched,
                message=message or f"Verified {resolved} of {total} chapters…",
                feed_text=feed,
            )
        )


def _clip(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _merge(regions: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    merged: List[Tuple[float, float]] = []
    for s, e in sorted(regions):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _subtract(area: Tuple[float, float], covered: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """The parts of ``area`` not inside any ``covered`` region."""
    lo, hi = area
    gaps = []
    pos = lo
    for s, e in covered:
        if e <= pos:
            continue
        if s >= hi:
            break
        if s > pos:
            gaps.append((pos, min(s, hi)))
        pos = max(pos, e)
        if pos >= hi:
            break
    if pos < hi:
        gaps.append((pos, hi))
    return gaps
