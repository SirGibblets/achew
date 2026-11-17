"""Pair the editor's chapters with a Reference's titles by what each chapter says (the Apply Titles
dialog's **By Similarity** mode).

A chapter is compared through its transcript (what is heard at its start: "Chapter Twelve. The
Storm. It was...") and through its current title (a cleaned-up "Chapter 12", or a title imported
from Audiobookshelf). Each is scored against the Reference titles with the matcher behind
transcription-enhanced realignment (``title_matching``), so the same tolerance applies: numbers
written any way agree, ASR misspellings of names still count, and a conflicting chapter number
rules a title out.

The pairs are then chosen in book order. Chapters and Reference titles run in the same order, so a
chapter can't take a title that comes before the previous chapter's; that is what tells apart the
"Chapter 1" of Part One from the "Chapter 1" of Part Two, or a repeated "Interlude".

Pure and audio-free.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from .title_matching import (
    HEAD_SLACK_TOKENS,
    MIN_FUZZY_LEN,
    MIN_VERIFIABLE_WEIGHT,
    NUMBER_HEAD_TOKENS,
    NUMBER_KEYWORDS,
    WEIGHT_WORD,
    HeardText,
    TitleProfile,
    expand_leading_roman,
    hear,
    match_title,
    normalize,
    title_profile,
)

Source = Literal["transcript", "title"]

# A chapter and a title are offered as a pair at this similarity, unchecked...
MIN_MATCH_SCORE = 0.5

# ...and checked at this one. The realignment verifier's STRONG_MATCH_SCORE: most of a title heard
# in order at the start of the text is already specific.
CONFIDENT_SCORE = 0.7

# The title's own number announced at the start ("Chapter 18", or "Eighteen." on its own) identifies
# it even when the rest of the title isn't there: trimming cut it off, the narrator doesn't read it,
# or the current title was cleaned to just "Chapter 18".
NUMBER_ANNOUNCED_SCORE = 0.75

# Every descriptive word of the title heard in order, without its number ("The Boy Who Lived" for
# "Chapter 1: The Boy Who Lived"): narrators who never say numbers, and titles cleaned without them.
WORDS_HEARD_SCORE = 0.75

# A title counts as heard only as a phrase: within its own length plus this many tokens from its first
# heard word (ASR fillers, "Chapter Seven. Uh, the Boggart..."). The words of a title scattered
# through the narration ("The star was bright that night over the egg farm" for "The Star Egg")
# don't add up to it.
PHRASE_SLACK_TOKENS = 2

# A title heard only after more than this many content words of other speech is more likely the
# narration mentioning it than the chapter announcing it (the verifier's MAX_LEAD_WORDS).
MAX_LEAD_WORDS = 2

# Late evidence, and a one-word title ("Harpies") that doesn't open the text as a phrase of its
# own, counts this much: enough to be offered unchecked, not to be checked.
WEAK_EVIDENCE_FACTOR = 0.6

# Titles scored against each text, picked by how much of each title the text's head shares. A book
# with many alike titles ("Genesis 1" ... "Revelation 22") would otherwise score every chapter
# against hundreds of titles that share only a number.
MAX_CANDIDATES = 24

# A number in front of a title that is a track number rather than the chapter's: "Track 3 - ...",
# zero-padded ("01 - Chapter 1", "003. Prologue"), or ahead of a numbered heading ("3 - Chapter 2").
# A plain "12. The Storm" keeps its number, since that's how many tables of contents number their
# chapters.
_LEADING_NUMBER_RE = re.compile(r"^\s*(track\s*)?(\d+)\s*[-–—.:)_]+\s*(?=\S)", re.IGNORECASE)


@dataclass(frozen=True)
class ChapterText:
    """What a chapter offers to identify its title."""

    title: str
    transcript: str


@dataclass(frozen=True)
class SimilarityMatch:
    chapter_index: int
    ref_index: int
    # 0..1, see ``similarity``
    score: float
    # Strong enough to apply as it is (checked in the dialog)
    confident: bool
    # The chapter text the match was found in
    source: Source


def strip_track_number(title: str) -> str:
    """``title`` without a leading track number (see ``_LEADING_NUMBER_RE``)."""
    match = _LEADING_NUMBER_RE.match(title)
    if not match:
        return title
    rest = title[match.end() :]
    number = match.group(2)
    padded = len(number) > 1 and number.startswith("0")
    heading = normalize(rest)[:2]
    numbered_heading = len(heading) == 2 and heading[0] in NUMBER_KEYWORDS and heading[1].isdigit()
    if match.group(1) or padded or numbered_heading:
        return rest
    return title


def reference_profile(title: str) -> Optional[TitleProfile]:
    """The profile to match a Reference title by, or None when the title has nothing to identify
    it by (blank, or just "Chapter")."""
    profile = title_profile(strip_track_number(title.strip()))
    informative = sum(w for w in profile.weights if w >= WEIGHT_WORD)
    return profile if informative >= MIN_VERIFIABLE_WEIGHT else None


def chapter_texts(chapter: ChapterText) -> List[Tuple[Source, HeardText]]:
    """The chapter's transcript and current title, ready to match. A title that is still the raw
    transcript counts once, as the transcript."""
    texts: List[Tuple[Source, HeardText]] = []
    transcript = hear(chapter.transcript)
    if transcript.tokens:
        texts.append(("transcript", transcript))
    title = hear(expand_leading_roman(strip_track_number(chapter.title.strip())))
    if title.tokens and title.tokens != transcript.tokens:
        texts.append(("title", title))
    return texts


def similarity(text: HeardText, profile: TitleProfile) -> float:
    """How well ``text`` identifies the title: the share of the title's weight heard in order at
    its start (``match_title``), raised for a number or words that identify the title on their own,
    lowered for evidence that may just be the narration, and 0 for a conflicting chapter number."""
    if text.tokens == profile.tokens:
        return 1.0
    whole = match_title(text, profile)
    if whole.number_conflict:
        return 0.0
    early = whole.lead_words <= MAX_LEAD_WORDS
    announced = _announces_number(text, profile)
    # Score the title as heard as a phrase, from its first heard token
    match = match_title(_phrase(text, whole.lead_tokens, len(profile.tokens) + PHRASE_SLACK_TOKENS), profile)
    score = match.score
    if early and announced:
        score = max(score, NUMBER_ANNOUNCED_SCORE)
    if early and match.words_complete and (match.content_words >= 2 or (match.lead_words == 0 and match.standalone)):
        score = max(score, WORDS_HEARD_SCORE)
    weak = (
        not early
        # "Harpies flew over the city..."
        or (match.single_word and not (match.lead_words == 0 and match.standalone))
        # "Two hours later..." for "Chapter 2: The Vanishing Glass"
        or (match.number_heard and not announced and match.words_heard == 0)
    )
    return score * WEAK_EVIDENCE_FACTOR if weak else score


def _phrase(text: HeardText, start: int, length: int) -> HeardText:
    """The ``length`` tokens of ``text`` from ``start``."""
    end = start + length
    return HeardText(
        tokens=text.tokens[start:end], roman=text.roman[start:end], sentence_len=text.sentence_len[start:end]
    )


def _announces_number(text: HeardText, profile: TitleProfile) -> bool:
    """Whether ``text`` opens by announcing one of the title's numbers: after a structural keyword
    ("Part One. Chapter Three"), or as a sentence of its own ("Three."). A number merely opening
    the narration ("Two hours later...") doesn't count."""
    head = text.tokens[:NUMBER_HEAD_TOKENS]
    if any(token in profile.numbers and head[k - 1] in NUMBER_KEYWORDS for k, token in enumerate(head) if k > 0):
        return True
    return text.sentence_len[0] == 1 and text.tokens[0] in profile.numbers


def _keys(token: str) -> List[str]:
    """Index keys for a token: itself, or for a word long enough to be fuzzy-matched, its first
    and last three letters (an ASR misspelling seldom changes both ends)."""
    if token.isdigit() or len(token) < MIN_FUZZY_LEN:
        return [token]
    return [f"{token[:3]}<", f">{token[-3:]}"]


class _TitleIndex:
    """Finds the Reference titles worth scoring against a text: those sharing a number or a
    descriptive word with the head of it."""

    def __init__(self, profiles: Sequence[Optional[TitleProfile]]):
        self.profiles = profiles
        self.weights: List[float] = [0.0] * len(profiles)
        self.keys: Dict[str, Dict[int, float]] = {}
        longest = 0
        for j, profile in enumerate(profiles):
            if profile is None:
                continue
            longest = max(longest, len(profile.tokens))
            self.weights[j] = profile.total_weight
            for token, weight in zip(profile.tokens, profile.weights):
                if weight < WEIGHT_WORD:
                    continue
                for key in _keys(token):
                    refs = self.keys.setdefault(key, {})
                    refs[j] = max(refs.get(j, 0.0), weight)
        # match_title only looks this far into a text
        self.head_len = longest + HEAD_SLACK_TOKENS

    def candidates(self, text: HeardText, position: float) -> List[int]:
        """The ``MAX_CANDIDATES`` titles sharing the largest part of their weight with the head of
        ``text``; among equals, those nearest the chapter's ``position`` (0..1) in the book."""
        shared: Dict[int, float] = {}
        for token in set(text.tokens[: self.head_len]):
            found: Dict[int, float] = {}
            for key in _keys(token):
                for j, weight in self.keys.get(key, {}).items():
                    found[j] = max(found.get(j, 0.0), weight)
            for j, weight in found.items():
                shared[j] = shared.get(j, 0.0) + weight
        count = len(self.profiles)
        ranked = sorted(
            shared,
            key=lambda j: (-shared[j] / self.weights[j], abs(position - (j + 0.5) / count), j),
        )
        return ranked[:MAX_CANDIDATES]


def match_by_similarity(chapters: Sequence[ChapterText], ref_titles: Sequence[str]) -> List[SimilarityMatch]:
    """Pair ``chapters`` (in book order) with ``ref_titles`` (in Reference order): each chapter
    gets at most one title and each title at most one chapter, in the same order on both sides."""
    profiles = [reference_profile(title) for title in ref_titles]
    index = _TitleIndex(profiles)
    pairs: Dict[Tuple[int, int], Tuple[float, Source]] = {}
    for i, chapter in enumerate(chapters):
        position = (i + 0.5) / len(chapters)
        for source, text in chapter_texts(chapter):
            for j in index.candidates(text, position):
                profile = profiles[j]
                assert profile is not None
                score = similarity(text, profile)
                if score >= MIN_MATCH_SCORE and score > pairs.get((i, j), (0.0, source))[0]:
                    pairs[(i, j)] = (score, source)
    chosen = ordered_pairs({pair: score for pair, (score, _) in pairs.items()})
    return [
        SimilarityMatch(
            chapter_index=i,
            ref_index=j,
            score=round(pairs[(i, j)][0], 3),
            confident=pairs[(i, j)][0] >= CONFIDENT_SCORE,
            source=pairs[(i, j)][1],
        )
        for i, j in chosen
    ]


def ordered_pairs(scores: Dict[Tuple[int, int], float]) -> List[Tuple[int, int]]:
    """The (chapter, title) pairs to keep: strictly increasing on both sides, with the largest
    total of squared scores, so one strong pair outweighs two weak ones that cross it.

    A weighted longest-increasing-subsequence over the candidate pairs, with a Fenwick tree of
    prefix maxima over title indexes: for each chapter, the best chain ending at a title before
    ``j`` is looked up before that chapter's own chains are added, so a chapter can't take two."""
    if not scores:
        return []
    pairs = sorted(scores)
    size = max(j for _, j in pairs) + 1
    # tree[k]: (best total, pair index) over a range of title positions (1-based)
    tree: List[Tuple[float, int]] = [(0.0, -1)] * (size + 1)

    def best_before(j: int) -> Tuple[float, int]:
        best, k = (0.0, -1), j
        while k > 0:
            if tree[k][0] > best[0]:
                best = tree[k]
            k -= k & -k
        return best

    def record(j: int, entry: Tuple[float, int]) -> None:
        k = j + 1
        while k <= size:
            if entry[0] > tree[k][0]:
                tree[k] = entry
            k += k & -k

    totals = [0.0] * len(pairs)
    previous = [-1] * len(pairs)
    start = 0
    while start < len(pairs):
        end = start
        while end < len(pairs) and pairs[end][0] == pairs[start][0]:
            end += 1
        for p in range(start, end):
            total, back = best_before(pairs[p][1])
            totals[p] = total + scores[pairs[p]] ** 2
            previous[p] = back
        for p in range(start, end):
            record(pairs[p][1], (totals[p], p))
        start = end

    p = max(range(len(pairs)), key=lambda k: totals[k])
    chain: List[Tuple[int, int]] = []
    while p != -1:
        chain.append(pairs[p])
        p = previous[p]
    return chain[::-1]
