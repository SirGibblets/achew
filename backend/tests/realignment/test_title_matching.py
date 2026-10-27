"""Tests for the transcript-vs-title matcher (app/services/title_matching.py).

The transcripts here are real Whisper (tiny.en) output from transcription-enhanced realignment
of a real audiobook, so they include the name mangling the matcher has to tolerate.
"""

import pytest

from app.services.realign_verification import confirms_title, words_only
from app.services.title_matching import (
    announces_chapter,
    is_interruption,
    is_preamble,
    match_title,
    normalize,
    title_profile,
)


def _strong(transcript: str, title: str) -> bool:
    return confirms_title(match_title(transcript, title_profile(title)))


@pytest.mark.parametrize(
    "text, tokens",
    [
        ("Chapter One Hundred and Twenty-Three", ["chapter", "123"]),
        ("Chapter XII: The Storm", ["chapter", "12", "the", "storm"]),
        ("Part II", ["part", "2"]),
        ("I went home", ["i", "went", "home"]),
        ("one two three", ["1", "2", "3"]),
        ("The Twenty-First Chapter", ["the", "21", "chapter"]),
        ("1st", ["1"]),
        ("two thousand and five", ["2005"]),
        ("Café — Naïve’s", ["cafe", "naives"]),
        # Multi-letter Roman numerals anywhere; single letters only after a keyword
        ("A Request II", ["a", "request", "2"]),
        ("Rocky III", ["rocky", "3"]),
        ("Who Am I", ["who", "am", "i"]),
        ("the mix tape", ["the", "mix", "tape"]),
        ("civil war", ["civil", "war"]),
    ],
)
def test_normalize(text, tokens):
    assert normalize(text) == tokens


@pytest.mark.parametrize(
    "transcript, title",
    [
        # Real ASR output: names mangled, number and remaining words carry it
        ("Chapter 1 Al Post", "Chapter 1: Owl Post"),
        ("Chapter 3 The Night Bus", "Chapter 3: The Knight Bus"),
        ("Chapter 7 The Bogot in the Wardrobe", "Chapter 7: The Boggart in the Wardrobe"),
        ("Chapter 16 Professor Trilone's Prediction", "Chapter 16: Professor Trelawney's Prediction"),
        ("Chapter 21 Herman is Secret", "Chapter 21: Hermione's Secret"),
        ("Chapter 22 I'll post again", "Chapter 22: Owl Post Again"),
        ("Chapter 13 Gryffindor vs. Ravenclaw", "Chapter 13: Gryffindor versus Ravenclaw"),
        # Trimming cut the rest of the title off after the announced number
        ("Chapter 18", "Chapter 18: Moony, Wormtail, Padfoot and Prongs"),
        # Number words, number-only titles, and a title without "Chapter"
        ("Chapter twelve. The storm rolled in.", "Chapter 12: The Storm"),
        ("One. Harry woke early", "1"),
        ("Chapter one. The boy who lived. Mr and Mrs Dursley", "The Boy Who Lived"),
        ("Part two. Chapter nine.", "Chapter 9"),
        ("Prologue. In the beginning", "Prologue"),
        ("Chapter five. Rand althor.", "Chapter 5: Rand al'Thor"),
        # Real output: one word of a long title mangled ("Echidna" -> "a Kidner")
        ("The offspring of a Kidner and Tiphon", "The Offspring of Echidna and Typhon"),
        ("Harpies. The Argonauts sailed on", "Harpies"),
        # Real output: one-word titles come through as just the title (trimming cuts after it)
        ("Purpose", "Purpose"),
        ("Request 2", "A Request II"),
        # Real output: the number misheard, something heard in its place, every descriptive word heard
        ("Fall Parliament of Owls It is a very funny thing that the sl", "Chapter Four: A Parliament of Owls"),
        # Real Parakeet output: caps, a misspelled number word, a part heading for a numbered title
        ("CHAPTER SEVENTEEEN CORK IsLAND", "Chapter 17"),
        ("Part One: Volunteers", "I. Volunteers"),
        ("Prologue: The Rubble Covenant Occupation", "Prologue"),
    ],
)
def test_strong_matches(transcript, title):
    assert _strong(transcript, title)


@pytest.mark.parametrize(
    "transcript, title",
    [
        # A different chapter's number: definitely not this chapter
        ("Chapter 13. The storm.", "Chapter 12: The Storm"),
        ("Chapter 17 Cat Rat and Dog", "Chapter 18: Moony, Wormtail, Padfoot and Prongs"),
        # Story text: the snippet started after the title (a pause just after it)
        ("It took a few seconds for the absurdity of the statement to sink in", "Chapter 18: Moony"),
        ("The rain fell on the roof for hours", "Chapter 12"),
        # The title heard only after the end of the previous chapter: the cue is too early
        ("and then he said the storm was coming. Chapter twelve", "Chapter 12: The Storm"),
        # A one-word title mentioned in passing (real output, a listing of episodes)
        ("H's Harpies, Hyles and Heracles Explained Idmon", "Harpies"),
        # A story sentence that happens to open with a one-word title
        ("Anger welled up in him as he walked", "Anger"),
        ("Files were scattered across the desk", "13. Files"),
        # Real output: an ASR split this badly is beyond matching (stays flagged for review)
        ("Pro-Lon The Rubble Covenant Occupied System", "Prologue"),
    ],
)
def test_not_strong(transcript, title):
    assert not _strong(transcript, title)


def test_late_title_reports_lead_words():
    m = match_title("and then he said the storm was coming. Chapter twelve", title_profile("Chapter 12: The Storm"))
    assert m.lead_words > 2 and m.score >= 0.5


@pytest.mark.parametrize("title", ["Opening Credits", "End Credits", "Track 3", "Chapter", "", "Untitled"])
def test_unverifiable_titles(title):
    assert not title_profile(title).verifiable


@pytest.mark.parametrize("title", ["Chapter 1", "1", "Prologue", "The Boy Who Lived", "Part II"])
def test_verifiable_titles(title):
    assert title_profile(title).verifiable


@pytest.mark.parametrize(
    "transcript, expected",
    [
        ("Harry Potter and the Prisoner of Azkaban by JK Rowling was read by Stephen Fry", True),
        ("Part two.", True),
        ("Book Three. The Storm", True),
        ("Audible Studios presents", True),
        ("This has been Lord of Chaos", True),
        ("and he walked home in the rain", False),
        ("The end of the world was near", False),
        ("it was barely audible", False),
        ("Christmas presents piled high", False),
    ],
)
def test_preamble(transcript, expected):
    assert is_preamble(transcript) is expected


@pytest.mark.parametrize(
    "transcript, expected",
    [
        # Real output: a multi-part download's disc break, before the next chapter
        ("This audiobook has been broken into multiple parts to make the download", True),
        ("Audible hopes you have enjoyed this program", True),
        ("This is Audible Earth Unaware by Orson Scott Card and Aaron Johnston", True),
        ("Lamb looked through the mining reports in the cargo bay", False),
    ],
)
def test_interruption(transcript, expected):
    assert is_interruption(transcript) is expected


@pytest.mark.parametrize(
    "transcript, title",
    [
        # Real output: a cue in the pause after "Chapter Two." — the chapter started 2 s earlier
        ("Jon's Big Battle", "Chapter 2: John's Big Battle"),
        ("Who are you?", "Chapter Fourteen — Who Are You?"),
        # Real output: a narrator who never says the numbers (the title is the opening epigraph)
        (
            "Mind of Man is Holy but the heart of man is corrupt",
            "Chapter 3 (The mind of man is holy but the heart of man is corrupt)",
        ),
        ("Files", "13. Files"),
    ],
)
def test_words_without_the_number_are_provisional(transcript, title):
    """The title's words open the snippet but its number wasn't heard: not a confirmation yet;
    the verifier first checks the cues just before for the number."""
    m = match_title(transcript, title_profile(title))
    assert words_only(m) and not confirms_title(m)


@pytest.mark.parametrize(
    "transcript, title",
    [
        ("Chapter 2 Jon's Big Battle", "Chapter 2: John's Big Battle"),
        ("Fall Parliament of Owls It is a very funny thing", "Chapter Four: A Parliament of Owls"),
        ("Purpose", "Purpose"),
        ("Files were scattered across the desk", "13. Files"),
    ],
)
def test_not_words_only(transcript, title):
    assert not words_only(match_title(transcript, title_profile(title)))


def test_a_roman_numeral_heard_never_contradicts_the_title():
    """Real Parakeet output renders spoken chapter numbers as (wrong) Roman numerals:
    "CHAPTER XXXIV AN EMBASSY" for Chapter 24. Such a numeral can agree with a title's number but
    can't rule a title out, so the words decide (provisionally, like any unheard number)."""
    m = match_title("CHAPTER XXXIV AN EMBASSY", title_profile("Chapter 24: An Embassy"))
    assert not m.number_conflict
    assert words_only(m)
    assert confirms_title(match_title("Chapter XII. The Storm", title_profile("Chapter 12: The Storm")))
    # A number in words or digits still contradicts
    assert match_title("Chapter 13. The storm", title_profile("Chapter 12: The Storm")).number_conflict


@pytest.mark.parametrize(
    "title, tokens",
    [
        ("I. Volunteers", ["1", "volunteers"]),
        ("IV: The Storm", ["4", "the", "storm"]),
        ("I Am Legend", ["i", "am", "legend"]),
    ],
)
def test_leading_roman_numeral_in_a_title(title, tokens):
    assert title_profile(title).tokens == tokens


@pytest.mark.parametrize(
    "transcript, title",
    [
        # Real Parakeet output: part of a spoken number lost
        ("CHAPTER FORTY THRIENDING IN THEY UNEXPECTED", "Chapter Forty-Three — Unexpected"),
        ("Chapter 11 Waiting Game", "Chapter One Hundred Eleven — Waiting Game"),
        ("Chapter 100. Waiting game", "Chapter 111: Waiting Game"),
    ],
)
def test_a_partly_heard_number_does_not_contradict(transcript, title):
    assert not match_title(transcript, title_profile(title)).number_conflict


@pytest.mark.parametrize(
    "transcript, expected",
    [
        ("CHAPTER FORTY THRIENDING IN THEY UNEXPECTED", True),
        ("Chapter 11 Waiting Game", True),
        ("Three.", True),
        ("Part Two", True),
        ("and then he said", False),
        ("Chapter of the night", False),
    ],
)
def test_announces_chapter(transcript, expected):
    assert announces_chapter(transcript) is expected
