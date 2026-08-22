"""Tests for collapsing Chapter References with identical chapter data (app/services/processing_pipeline.py)."""

from app.models.references import BasicChapter, ChapterReference, ChapterRefType
from app.services.processing_pipeline import _dedupe_chapter_refs


def _ref(
    name: str, chapters: list[tuple[float, str]], ref_type: ChapterRefType = ChapterRefType.ABS
) -> ChapterReference:
    return ChapterReference(
        type=ref_type,
        name=name,
        short_name=name,
        description="",
        chapters=[BasicChapter(timestamp=ts, title=title) for ts, title in chapters],
        duration=3600.0,
    )


def test_identical_chapters_are_merged():
    abs_ref = _ref("Audiobookshelf Chapters", [(0.0, "Chapter 1"), (600.0, "Chapter 2")])
    embedded_ref = _ref(
        "Embedded Chapters", [(0.0, "Chapter 1"), (600.0, "Chapter 2")], ref_type=ChapterRefType.EMBEDDED
    )

    result = _dedupe_chapter_refs([abs_ref, embedded_ref])

    assert [r.name for r in result] == ["Audiobookshelf Chapters"]
    assert result[0].merged_names == ["Embedded Chapters"]


def test_timestamps_within_tolerance_are_merged():
    ref_a = _ref("A", [(0.0, "Chapter 1"), (600.0, "Chapter 2")])
    ref_b = _ref("B", [(0.05, "Chapter 1"), (600.09, "Chapter 2")])

    result = _dedupe_chapter_refs([ref_a, ref_b])

    assert len(result) == 1
    assert result[0].merged_names == ["B"]


def test_timestamps_outside_tolerance_are_kept_separate():
    ref_a = _ref("A", [(0.0, "Chapter 1")])
    ref_b = _ref("B", [(0.2, "Chapter 1")])

    result = _dedupe_chapter_refs([ref_a, ref_b])

    assert [r.name for r in result] == ["A", "B"]
    assert result[0].merged_names == []


def test_different_chapter_counts_are_kept_separate():
    ref_a = _ref("A", [(0.0, "Chapter 1")])
    ref_b = _ref("B", [(0.0, "Chapter 1"), (600.0, "Chapter 2")])

    result = _dedupe_chapter_refs([ref_a, ref_b])

    assert [r.name for r in result] == ["A", "B"]


def test_different_titles_are_kept_separate():
    ref_a = _ref("A", [(0.0, "Chapter 1")])
    ref_b = _ref("B", [(0.0, "Prologue")])

    result = _dedupe_chapter_refs([ref_a, ref_b])

    assert [r.name for r in result] == ["A", "B"]


def test_multiple_duplicates_are_all_recorded_on_the_canonical_ref():
    ref_a = _ref("A", [(0.0, "Chapter 1")])
    ref_b = _ref("B", [(0.0, "Chapter 1")])
    ref_c = _ref("C", [(0.0, "Chapter 1")])

    result = _dedupe_chapter_refs([ref_a, ref_b, ref_c])

    assert [r.name for r in result] == ["A"]
    assert result[0].merged_names == ["B", "C"]
