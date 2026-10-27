"""Compare a transcribed snippet of audio against an expected chapter title.

Used by transcription-enhanced realignment to check whether a cue really is the start of a
chapter: the audio right after a true chapter boundary usually announces the chapter ("Chapter
Twelve. The Storm."), so its transcript should contain the reference title near the start.

Both sides are normalised the same way before comparing: case, accents and punctuation are
dropped, and English number words, ordinals and keyword-anchored Roman numerals become digits,
so "Chapter XII", "chapter twelve" and "Chapter 12" agree. The title is then aligned against the
head of the transcript with an in-order (LCS-style) match, weighted so the parts that identify
a chapter count most: numbers carry the most weight, content words next, and structural
keywords ("chapter", "part") and stop words little, since narrators often drop or add them.

Pure and audio-free so it can be tested on transcript strings directly.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Set, Tuple

# Structural words that commonly precede a chapter number (mirrors the frontend's
# NUMBER_KEYWORD_LIST in utils/titleTools.ts). A Roman numeral directly after one of these is
# read as a number; elsewhere "I", "V" and friends stay words.
NUMBER_KEYWORDS = {
    "chapter",
    "chap",
    "ch",
    "part",
    "pt",
    "book",
    "volume",
    "vol",
    "section",
    "episode",
    "ep",
    "letter",
    "act",
    "scene",
    "track",
    "disc",
    "number",
}

# Words that carry little identity in a title. Matching them is still rewarded, but missing
# them barely hurts (ASR drops and inserts these freely).
STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

# Token weights. A number is the single most identifying part of most chapter titles; a
# structural keyword is often omitted by the narrator ("One." for "Chapter 1").
WEIGHT_NUMBER = 2.0
WEIGHT_WORD = 1.0
WEIGHT_STOP = 0.25
WEIGHT_KEYWORD = 0.25

# A title needs at least this much informative weight (one content word, or a number) to be
# verifiable at all. "Chapter" alone or an empty title can't confirm anything.
MIN_VERIFIABLE_WEIGHT = 1.0

# Titles that name a part of the recording that is never read aloud as the title.
UNSPOKEN_TITLE_RE = re.compile(r"\b(credits?|track|untitled|logo|blank)\b")

# How far past the title's length into the transcript a match may start. Narrators sometimes
# lead with a book or part heading ("Harry Potter and the Prisoner of Azkaban. Chapter One. Owl
# Post."), and trimming can leave a word of the previous chapter at the start. A title found
# late is reported through ``lead_words``, so a wide window doesn't make late matches count.
HEAD_SLACK_TOKENS = 12

# Two words count as the same when they are this similar, absorbing ASR spelling slips on
# names ("Rand" vs "Rande"). Only applied to words of MIN_FUZZY_LEN letters or more; shorter
# words and numbers must match exactly.
FUZZY_WORD_RATIO = 0.8
MIN_FUZZY_LEN = 4

# A transcript whose head names one of these numbers in keyword position (or as its first
# token) while the title names a different one is a definite mismatch.
NUMBER_HEAD_TOKENS = 4

# Speech that opens a chapter before its title is announced: credits ("...was read by Stephen
# Fry. The Story Continues...") or a structural heading ("Part Two." before "Chapter Nine.").
# When the title is heard a few seconds after such a preamble, the chapter starts at the
# preamble, not at the announcement.
PREAMBLE_PHRASES_RE = re.compile(
    r"\b(read by|narrated by|performed by|this has been|you have been listening|copyright|"
    r"recorded (by|at|in)|a production of|(audible|audio|books|house|media) (studios|presents))\b"
)
PREAMBLE_HEADING_KEYWORDS = {"part", "pt", "book", "volume", "vol", "act"}

# Announcements that interrupt the book between chapters (multi-part downloads, disc changes).
# The next chapter starts after them, so a search that hears one should look later first.
INTERRUPTION_RE = re.compile(
    r"\b(broken into multiple parts|hopes you have enjoyed|this is audible|end of (part|disc|side|tape)|"
    r"continued (on|in) (part|disc))\b"
)

# One-word evidence ("Harpies", or "Files" for "13. Files" with the number unheard) only counts when
# the title is heard as its own phrase: the sentence it opens has at most this many words beyond
# the title. Real announcements come through as just the title (trimming cuts at the pause after
# it); a story sentence that happens to open with the word ("Anger welled up in him...") runs on.
STANDALONE_EXTRA_TOKENS = 2

_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_UNIT_ORDINALS = [
    "zeroth",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
]
_TENS_ORDINALS = [
    "",
    "",
    "twentieth",
    "thirtieth",
    "fortieth",
    "fiftieth",
    "sixtieth",
    "seventieth",
    "eightieth",
    "ninetieth",
]

_UNIT_VALUES = {w: i for i, w in enumerate(_UNITS)} | {w: i for i, w in enumerate(_UNIT_ORDINALS)}
_TENS_VALUES = {w: i * 10 for i, w in enumerate(_TENS) if w} | {w: i * 10 for i, w in enumerate(_TENS_ORDINALS) if w}
_SCALES = {"hundred": 100, "hundredth": 100, "thousand": 1000, "thousandth": 1000}

_ROMAN_RE = re.compile(r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
# Words (and acronyms) that also happen to be valid Roman numerals; mirrors the frontend's
# ROMAN_FALSE_FRIENDS in utils/titleTools.ts. Never read as numbers unless after a keyword.
_ROMAN_FALSE_FRIENDS = {"mix", "mm", "cm", "cd", "md", "dc", "di", "li", "mi"}
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_DIGIT_SUFFIX_RE = re.compile(r"^(\d+)(st|nd|rd|th)?$")


@dataclass(frozen=True)
class TitleProfile:
    """A normalised reference title, ready to match transcripts against."""

    tokens: List[str]
    weights: List[float]
    numbers: Set[str]
    total_weight: float
    # False when the title can't confirm a placement (unspoken or uninformative); such
    # chapters are conceded without transcribing them.
    verifiable: bool


@dataclass(frozen=True)
class TitleMatch:
    # Fraction of the title's weight found, in order, near the start of the transcript
    score: float
    # Content words heard before the title begins. Numbers, structural keywords and stop words
    # don't count, so "Chapter one. The Boy Who Lived" leads with 0. A title heard after a few
    # words of other speech means the snippet started early, before the real chapter start.
    lead_words: int
    # The transcript names a different chapter number than the title does
    number_conflict: bool
    # Tokens heard before the first word of the title (of any kind): something in the slot where
    # the chapter number would be announced
    lead_tokens: int = 0
    # The transcript opens by announcing the title's own number ("Chapter 18." with the rest of
    # the title cut off by trimming): decisive on its own
    announced_number: bool = False
    # The title is a single word with no number ("Harpies"): weak evidence, since such a word can
    # also come up in the narration, so it has to open the snippet as its own phrase to count
    single_word: bool = False
    # Every descriptive (non-number) word of the title was heard, in order, with its number not
    # heard: either misheard ("Fall Parliament of Owls" for "Chapter Four: A Parliament of Owls"),
    # never spoken, or said just before the snippet started (see the verifier's words-only rule)
    words_complete: bool = False
    # How many descriptive words the title has
    content_words: int = 0
    # The title has a number, and whether it was among the tokens heard
    numbered: bool = False
    number_heard: bool = False
    # The title opens a phrase of its own rather than a longer sentence (see STANDALONE_EXTRA_TOKENS)
    standalone: bool = False


def _roman_value(token: str) -> Optional[int]:
    if not token or not _ROMAN_RE.match(token):
        return None
    total = 0
    for i, ch in enumerate(token):
        value = _ROMAN_VALUES[ch]
        nxt = _ROMAN_VALUES[token[i + 1]] if i + 1 < len(token) else 0
        total += -value if value < nxt else value
    return total


def _words(text: str) -> List[str]:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", text).split()


def normalize(text: str) -> List[str]:
    """Lowercase, accent- and punctuation-free tokens with numbers written as digits."""
    return [token for token, _ in _normalize(text)]


def _normalize(text: str) -> List[Tuple[str, bool]]:
    """``normalize``, with each token flagged when it came from a Roman numeral."""
    words = _words(text)
    out: List[Tuple[str, bool]] = []
    i = 0
    while i < len(words):
        word = words[i]
        digit = _DIGIT_SUFFIX_RE.match(word)
        if digit:
            out.append((str(int(digit.group(1))), False))
            i += 1
            continue

        # A run of number words: "one hundred and twenty third" -> 123
        value, consumed = _parse_number_words(words, i)
        if consumed:
            out.append((str(value), False))
            i += consumed
            continue

        # Roman numerals: any multi-letter one ("A Request II") that isn't also a common word,
        # and single letters only after a structural keyword ("Part I"), so "I" stays a word
        after_keyword = bool(out) and out[-1][0] in NUMBER_KEYWORDS
        if after_keyword or (len(word) >= 2 and word not in _ROMAN_FALSE_FRIENDS):
            roman = _roman_value(word)
            if roman:
                out.append((str(roman), True))
                i += 1
                continue

        out.append((word, False))
        i += 1
    return out


_ORDINAL_WORDS = set(_UNIT_ORDINALS) | {w for w in _TENS_ORDINALS if w} | {"hundredth", "thousandth"}
_NUMBER_WORDS = sorted(set(_UNIT_VALUES) | set(_TENS_VALUES) | set(_SCALES))

# ASR sometimes misspells a number word ("SEVENTEEEN"). A word this close to a number word (and at
# least this long, so short words can't collide) is read as that number word.
FUZZY_NUMBER_RATIO = 0.9
MIN_FUZZY_NUMBER_LEN = 6


def _number_word(word: str) -> str:
    """``word`` itself when it's a number word, the number word it's a near-miss spelling of, or
    ``word`` unchanged."""
    if word in _UNIT_VALUES or word in _TENS_VALUES or word in _SCALES or len(word) < MIN_FUZZY_NUMBER_LEN:
        return word
    for candidate in _NUMBER_WORDS:
        if (
            abs(len(candidate) - len(word)) <= 2
            and SequenceMatcher(None, word, candidate).ratio() >= FUZZY_NUMBER_RATIO
        ):
            return candidate
    return word


def _parse_number_words(words: Sequence[str], start: int) -> "tuple[int, int]":
    """Parse an English number-word run at ``words[start]``; returns (value, tokens consumed),
    with 0 consumed when there is no number there. ``last`` tracks the previous component so
    two numbers in a row ("one two") stay separate rather than summing."""
    total = 0
    current = 0
    last: Optional[str] = None
    i = start
    while i < len(words):
        word = _number_word(words[i])
        if word in _UNIT_VALUES and _UNIT_VALUES[word] < 10:
            if last not in (None, "tens", "hundred", "thousand"):
                break
            current += _UNIT_VALUES[word]
            last = "unit"
        elif word in _UNIT_VALUES:
            if last not in (None, "hundred", "thousand"):
                break
            current += _UNIT_VALUES[word]
            last = "teen"
        elif word in _TENS_VALUES:
            if last not in (None, "hundred", "thousand"):
                break
            current += _TENS_VALUES[word]
            last = "tens"
        elif word in _SCALES and _SCALES[word] == 100:
            if last not in ("unit", "teen", "tens") or current % 100 == 0:
                break
            current *= 100
            last = "hundred"
        elif word in _SCALES:
            if last not in ("unit", "teen", "tens", "hundred"):
                break
            total += current * 1000
            current = 0
            last = "thousand"
        elif word == "and" and last in ("hundred", "thousand"):
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if nxt not in _UNIT_VALUES and nxt not in _TENS_VALUES:
                break
        else:
            break
        i += 1
        if word in _ORDINAL_WORDS:
            # An ordinal ends the number ("twenty first chapter")
            break
    consumed = i - start
    return (total + current, consumed) if consumed else (0, 0)


# A Roman numeral opening a title and set off by punctuation ("I. Volunteers", "IV: The Storm") is a
# number even as a single letter.
_LEADING_ROMAN_RE = re.compile(r"^\s*([IVXLCDM]+)\s*[.:)\-\u2013\u2014]\s+")


def title_profile(title: str) -> TitleProfile:
    leading = _LEADING_ROMAN_RE.match(title)
    if leading and _roman_value(leading.group(1).lower()):
        title = f"{_roman_value(leading.group(1).lower())} {title[leading.end() :]}"
    tokens = normalize(title)
    weights = []
    numbers: Set[str] = set()
    for token in tokens:
        if token.isdigit():
            weights.append(WEIGHT_NUMBER)
            numbers.add(token)
        elif token in NUMBER_KEYWORDS:
            weights.append(WEIGHT_KEYWORD)
        elif token in STOP_WORDS:
            weights.append(WEIGHT_STOP)
        else:
            weights.append(WEIGHT_WORD)
    total = sum(weights)
    informative = sum(w for w in weights if w >= WEIGHT_WORD)
    unspoken = bool(UNSPOKEN_TITLE_RE.search(" ".join(_words(title))))
    return TitleProfile(
        tokens=tokens,
        weights=weights,
        numbers=numbers,
        total_weight=total,
        verifiable=informative >= MIN_VERIFIABLE_WEIGHT and not unspoken,
    )


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    if a.isdigit() or b.isdigit() or min(len(a), len(b)) < MIN_FUZZY_LEN:
        return False
    return SequenceMatcher(None, a, b).ratio() >= FUZZY_WORD_RATIO


def _head_numbers(tokens: Sequence[str], roman: Sequence[bool], include_roman: bool) -> Set[str]:
    """Numbers the transcript announces at its start: the first token, or one directly after
    a structural keyword. Roman numerals in a TRANSCRIPT are unreliable — an ASR model can render
    "Chapter Twenty-Four" as "CHAPTER XXXIV" — so they can confirm a number but not contradict one."""
    found = set()
    for i, token in enumerate(tokens[:NUMBER_HEAD_TOKENS]):
        if roman[i] and not include_roman:
            continue
        if token.isdigit() and (i == 0 or tokens[i - 1] in NUMBER_KEYWORDS):
            found.add(token)
    return found


def match_title(transcript: str, profile: TitleProfile) -> TitleMatch:
    """Score how well ``transcript`` announces the title described by ``profile``."""
    # Normalise sentence by sentence (ASR punctuation marks the announcement's end), remembering
    # how long the sentence each token belongs to is
    heard: List[str] = []
    heard_roman: List[bool] = []
    sentence_len: List[int] = []
    for sentence in re.split(r"[.!?;:]+", transcript):
        tokens = _normalize(sentence)
        heard.extend(t for t, _ in tokens)
        heard_roman.extend(r for _, r in tokens)
        sentence_len.extend([len(tokens)] * len(tokens))
    if not profile.tokens or not heard:
        return TitleMatch(score=0.0, lead_words=0, number_conflict=False)

    head = heard[: len(profile.tokens) + HEAD_SLACK_TOKENS]
    n, m = len(profile.tokens), len(head)

    # Weighted LCS: best[i][j] = most title weight matched in order using title[:i], head[:j]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            keep = best[i - 1][j - 1] + profile.weights[i - 1] if _same(profile.tokens[i - 1], head[j - 1]) else 0.0
            best[i][j] = max(best[i - 1][j], best[i][j - 1], keep)

    # Where in the transcript the matched title starts: walk back to the earliest head token
    # used by an informative (non-filler) match.
    start = m
    first_heard = m
    matched: Set[int] = set()
    i, j = n, m
    while i > 0 and j > 0:
        if _same(profile.tokens[i - 1], head[j - 1]) and (
            abs(best[i][j] - (best[i - 1][j - 1] + profile.weights[i - 1])) < 1e-9
        ):
            matched.add(i - 1)
            first_heard = j - 1
            if profile.weights[i - 1] >= WEIGHT_WORD:
                start = j - 1
            i, j = i - 1, j - 1
        elif best[i - 1][j] >= best[i][j - 1]:
            i -= 1
        else:
            j -= 1

    lead = sum(1 for token in head[: start if start < m else 0] if _is_content(token))
    heard_numbers = _head_numbers(heard, heard_roman, include_roman=True)
    stated_numbers = _head_numbers(heard, heard_roman, include_roman=False)
    conflict = (
        bool(profile.numbers)
        and bool(stated_numbers)
        and not (profile.numbers & heard_numbers)
        and not any(_partial_number(h, n) for h in stated_numbers for n in profile.numbers)
    )
    score = best[n][m] / profile.total_weight if profile.total_weight > 0 else 0.0
    announced = bool(profile.numbers & heard_numbers) and not conflict
    words = [k for k, (t, w) in enumerate(zip(profile.tokens, profile.weights)) if w >= WEIGHT_WORD and not t.isdigit()]
    complete = bool(words) and all(k in matched for k in words)
    standalone = start < m and sentence_len[start] <= len(profile.tokens) + STANDALONE_EXTRA_TOKENS
    return TitleMatch(
        score=score,
        lead_words=lead,
        number_conflict=conflict,
        lead_tokens=first_heard if first_heard < m else 0,
        announced_number=announced,
        single_word=not profile.numbers and len(words) == 1,
        words_complete=complete,
        content_words=len(words),
        numbered=bool(profile.numbers),
        number_heard=any(k in matched for k, t in enumerate(profile.tokens) if t.isdigit()),
        standalone=standalone,
    )


def _partial_number(heard: str, title: str) -> bool:
    """Whether ``heard`` is ``title`` with part of it lost by the ASR, so it doesn't contradict
    it: "forty" for 43 ("forty-three" garbled to "forty thriending"), "11" for 111 ("one hundred"
    dropped), "100" for 111. (Real Parakeet output; it still isn't a match on its own.)"""
    h, n = int(heard), int(title)
    if h == n:
        return True
    if n > h and str(n).endswith(str(h)):
        return True
    for unit in (10, 100, 1000):
        if h % unit == 0 and h // unit == n // unit and h < n:
            return True
    return False


def announces_chapter(transcript: str) -> bool:
    """Whether a snippet opens by announcing a chapter: a structural keyword and a number
    ("Chapter 43", "CHAPTER FORTY THRIENDING…", "Part Two") or a number alone ("Three.")."""
    heard = normalize(transcript)
    if not heard:
        return False
    if heard[0].isdigit():
        return True
    return heard[0] in NUMBER_KEYWORDS and any(token.isdigit() for token in heard[1:3])


def is_interruption(transcript: str) -> bool:
    """Whether a snippet is a between-chapters announcement (part/disc breaks)."""
    return bool(INTERRUPTION_RE.search(" ".join(normalize(transcript))))


def is_preamble(transcript: str) -> bool:
    """Whether a snippet sounds like speech that opens a chapter ahead of its title: credits,
    or a part/book heading."""
    heard = normalize(transcript)
    if len(heard) >= 2 and heard[0] in PREAMBLE_HEADING_KEYWORDS and heard[1].isdigit():
        return True
    return bool(PREAMBLE_PHRASES_RE.search(" ".join(heard)))


def _is_content(token: str) -> bool:
    return not token.isdigit() and token not in NUMBER_KEYWORDS and token not in STOP_WORDS
