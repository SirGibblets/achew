"""Tests for Apply Titles → By Similarity (app/services/title_similarity.py).

The mangled names in the transcripts are real Whisper output (the same ones as in
tests/realignment/test_title_matching.py), since tolerating them is the point of reusing the
realignment matcher here.
"""

import itertools
import random

import pytest

from app.services.title_similarity import (
    CONFIDENT_SCORE,
    MIN_MATCH_SCORE,
    ChapterText,
    match_by_similarity,
    ordered_pairs,
    strip_track_number,
)

HP_REFS = [
    "Opening Credits",
    "Chapter 1: Owl Post",
    "Chapter 2: Aunt Marge's Big Mistake",
    "Chapter 3: The Knight Bus",
    "Chapter 4: The Leaky Cauldron",
    "Chapter 5: The Dementor",
    "Chapter 7: The Boggart in the Wardrobe",
    "Chapter 16: Professor Trelawney's Prediction",
    "Chapter 22: Owl Post Again",
    "End Credits",
]


def _pairs(chapters, refs):
    """{chapter index: (title, confident, source)}"""
    return {m.chapter_index: (refs[m.ref_index], m.confident, m.source) for m in match_by_similarity(chapters, refs)}


def _transcripts(*texts):
    return [ChapterText(title=t, transcript=t) for t in texts]


def test_transcripts_announcing_their_titles_are_paired_and_checked():
    chapters = _transcripts(
        "This is Audible.",
        "Chapter 1 Al Post. Harry Potter was a highly unusual boy in many ways.",
        "Chapter Two. Aunt Marge's big mistake. When Harry went down to breakfast",
        "Chapter 3 The Night Bus. Harry was several streets away before he",
        "Chapter 7 The Bogot in the Wardrobe. Malfoy didn't reappear in classes",
        "Chapter 16 Professor Trilone's Prediction. Harry's elation at finally",
        "End credits. This has been Harry Potter and the Prisoner of Azkaban.",
    )
    assert _pairs(chapters, HP_REFS) == {
        1: ("Chapter 1: Owl Post", True, "transcript"),
        2: ("Chapter 2: Aunt Marge's Big Mistake", True, "transcript"),
        3: ("Chapter 3: The Knight Bus", True, "transcript"),
        4: ("Chapter 7: The Boggart in the Wardrobe", True, "transcript"),
        5: ("Chapter 16: Professor Trelawney's Prediction", True, "transcript"),
        6: ("End Credits", True, "transcript"),
    }


def test_current_titles_match_by_number_or_by_words():
    """Chapters without transcripts (imported from Audiobookshelf, or cleaned up) still match: by
    their number alone, or by every descriptive word without the number."""
    chapters = [
        ChapterText(title="Chapter 4", transcript=""),
        ChapterText(title="The Dementor", transcript=""),
        ChapterText(title="Owl Post Again", transcript=""),
    ]
    assert _pairs(chapters, HP_REFS) == {
        0: ("Chapter 4: The Leaky Cauldron", True, "title"),
        1: ("Chapter 5: The Dementor", True, "title"),
        2: ("Chapter 22: Owl Post Again", True, "title"),
    }


def test_the_better_of_transcript_and_title_counts():
    chapters = [ChapterText(title="Chapter 3: The Knight Bus", transcript="Harry was several streets away")]
    assert _pairs(chapters, HP_REFS) == {0: ("Chapter 3: The Knight Bus", True, "title")}


def test_a_conflicting_number_rules_a_title_out():
    chapters = [ChapterText(title="Chapter 3", transcript="Chapter Three. The Leaky Cauldron.")]
    refs = ["Chapter 4: The Leaky Cauldron"]
    assert _pairs(chapters, refs) == {}


def test_book_order_tells_repeated_titles_apart():
    refs = [f"Part {p}, Chapter {c}" for p in (1, 2) for c in (1, 2, 3)]
    chapters = [ChapterText(title=f"Chapter {c}", transcript="") for _ in (1, 2) for c in (1, 2, 3)]
    assert {i: title for i, (title, _, _) in _pairs(chapters, refs).items()} == dict(enumerate(refs))


def test_a_repeated_title_goes_to_the_chapter_in_order():
    refs = ["Chapter 1", "Interlude", "Chapter 2", "Interlude", "Chapter 3"]
    chapters = _transcripts("Chapter one.", "Interlude.", "Chapter two.", "Interlude.", "Chapter three.")
    assert [m.ref_index for m in match_by_similarity(chapters, refs)] == [0, 1, 2, 3, 4]


def test_a_false_split_mentioning_a_title_is_left_alone():
    """A cue inside chapter 3 whose transcript happens to mention its title doesn't take the title
    from the chapter that announces it."""
    chapters = _transcripts(
        "Chapter 3 The Night Bus. Harry was several streets away before he",
        "He went outside and looked at the knight bus as it came round the corner.",
        "Chapter four. The leaky cauldron. It took Harry several days",
    )
    assert _pairs(chapters, HP_REFS) == {
        0: ("Chapter 3: The Knight Bus", True, "transcript"),
        2: ("Chapter 4: The Leaky Cauldron", True, "transcript"),
    }


def test_a_title_only_counts_when_heard_as_a_phrase():
    refs = ["Episode 6: The Star Egg"]
    assert _pairs(_transcripts("The star was bright that night over the egg farm and everyone watched."), refs) == {}
    # Its words coming up again in the narration after it is fine
    assert _pairs(_transcripts("The Star Egg. Nobody knew where the egg came from."), refs) == {
        0: ("Episode 6: The Star Egg", True, "transcript")
    }


def test_narration_opening_with_a_number_is_not_an_announcement():
    chapters = _transcripts("Two hours later they reached the zoo.")
    assert _pairs(chapters, ["Chapter 2: The Vanishing Glass"]) == {}


@pytest.mark.parametrize(
    "transcript, title",
    [
        ("Two. The Dursleys had been awake for hours.", "Chapter 2"),
        ("Part One. Chapter Three. Harry woke early", "Chapter 3: The Letters"),
        ("Chapter 18", "Chapter 18: Moony, Wormtail, Padfoot and Prongs"),
    ],
)
def test_an_announced_number_identifies_a_title(transcript, title):
    assert _pairs(_transcripts(transcript), [title]) == {0: (title, True, "transcript")}


def test_a_one_word_title_counts_only_as_a_phrase_of_its_own():
    refs = ["Harpies"]
    assert _pairs(_transcripts("Harpies. The city woke to screams."), refs) == {0: ("Harpies", True, "transcript")}
    # Opening a longer sentence it may just be the narration: offered, but unchecked
    assert _pairs(_transcripts("Harpies flew over the city at dawn, screaming."), refs) == {
        0: ("Harpies", False, "transcript")
    }


def test_a_title_heard_late_is_not_checked():
    chapters = _transcripts("And then he said that he would go, in the end. Chapter Four. The Leaky Cauldron.")
    match = _pairs(chapters, HP_REFS).get(0)
    assert match is None or not match[1]


def test_titles_with_nothing_to_identify_them_are_never_matched():
    chapters = [ChapterText(title="Chapter", transcript="Chapter."), ChapterText(title="", transcript="")]
    assert _pairs(chapters, ["", "Chapter", "   "]) == {}


def test_identical_titles_match_even_when_unspoken():
    chapters = [ChapterText(title="Opening Credits", transcript="")]
    assert _pairs(chapters, HP_REFS) == {0: ("Opening Credits", True, "title")}


def test_a_leading_roman_numeral_in_a_current_title_is_its_number():
    chapters = [ChapterText(title="I. Volunteers", transcript="")]
    assert _pairs(chapters, ["Chapter 1: Volunteers", "Chapter 2: Volunteers"]) == {
        0: ("Chapter 1: Volunteers", True, "title")
    }


def test_track_numbers_dont_conflict_with_chapter_numbers():
    """Titles from file names carry the track number, which is off by one once there's a prologue."""
    chapters = [ChapterText(title=t, transcript="") for t in ("01 - Prologue", "02 - Chapter 1", "03 - Chapter 2")]
    refs = ["Prologue", "Chapter 1: The Boy Who Lived", "Chapter 2: The Vanishing Glass"]
    assert {i: t for i, (t, _, _) in _pairs(chapters, refs).items()} == dict(enumerate(refs))


@pytest.mark.parametrize(
    "title, stripped",
    [
        ("01 - Chapter 1", "Chapter 1"),
        ("003. Prologue", "Prologue"),
        ("Track 3 - Down the Rabbit Hole", "Down the Rabbit Hole"),
        ("3 - Chapter 2", "Chapter 2"),
        ("03_Chapter 3", "Chapter 3"),
        # A table of contents' own chapter number stays
        ("12. The Storm", "12. The Storm"),
        ("3 - Part of the Plan", "3 - Part of the Plan"),
        ("12 Angry Men", "12 Angry Men"),
        ("Track 3", "Track 3"),
    ],
)
def test_strip_track_number(title, stripped):
    assert strip_track_number(title) == stripped


def test_scores_and_confidence_agree():
    chapters = _transcripts("Harpies flew over the city at dawn, screaming.", "Chapter 1 Al Post.")
    for m in match_by_similarity(chapters, ["Harpies", "Chapter 1: Owl Post"]):
        assert m.score >= MIN_MATCH_SCORE
        assert m.confident == (m.score >= CONFIDENT_SCORE)


def test_one_strong_pair_outweighs_two_weak_ones_crossing_it():
    # Chapter 0 strongly matches title 1; chapters 1 and 2 weakly match title 0 and... crossing it
    scores = {(0, 1): 1.0, (1, 0): 0.5, (2, 0): 0.5, (1, 2): 0.5}
    assert ordered_pairs(scores) == [(0, 1), (1, 2)]


def _brute_force_total(scores):
    best = 0.0
    items = list(scores)
    for r in range(1, len(items) + 1):
        for subset in itertools.combinations(sorted(items), r):
            if all(a[0] < b[0] and a[1] < b[1] for a, b in zip(subset, subset[1:])):
                best = max(best, sum(scores[p] ** 2 for p in subset))
    return best


@pytest.mark.parametrize("seed", range(40))
def test_ordered_pairs_is_the_best_increasing_chain(seed):
    rng = random.Random(seed)
    scores = {(rng.randrange(6), rng.randrange(6)): rng.uniform(0.5, 1.0) for _ in range(rng.randrange(1, 11))}
    chain = ordered_pairs(scores)
    assert all(a[0] < b[0] and a[1] < b[1] for a, b in zip(chain, chain[1:]))
    assert sum(scores[p] ** 2 for p in chain) == pytest.approx(_brute_force_total(scores))
