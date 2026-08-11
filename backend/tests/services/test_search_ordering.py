"""Tests for library-search result ordering (app/services/abs_service.py).

`_apply_series_order` is the rule that puts a series into reading order without
disturbing the ranking that placed it. Books are built straight from the Pydantic
models, so no Audiobookshelf server is involved.
"""

import math

from app.models.abs import Book, BookMedia, BookMetadata, MatchType, SeriesDetails
from app.services.abs_service import _apply_series_order, _series_sequence


def make_book(title: str, series: str | None = None, sequence: str | None = None) -> Book:
    metadata = BookMetadata(
        title=title,
        genres=[],
        publishedYear=None,
        description=None,
        series=([SeriesDetails(id=series, name=series, sequence=sequence)] if series is not None else None),
    )
    return Book(
        id=title,
        addedAt=0,
        updatedAt=0,
        media=BookMedia(metadata=metadata, coverPath="/cover.jpg", numAudioFiles=1),
    )


def order(books: list[Book]) -> list[str]:
    entries = [(b, MatchType.TITLE, "") for b in books]
    return [b.media.metadata.title for b, _, _ in _apply_series_order(entries)]


class TestSeriesSequence:
    def test_parses_a_plain_number(self):
        assert _series_sequence(make_book("A", "S", "3")) == 3.0

    def test_parses_a_decimal_interlude(self):
        assert _series_sequence(make_book("A", "S", "8.5")) == 8.5

    def test_takes_the_first_number_of_an_omnibus_range(self):
        assert _series_sequence(make_book("A", "S", "1-2")) == 1.0

    def test_sorts_unnumbered_entries_last(self):
        assert _series_sequence(make_book("A", "S", None)) == math.inf
        assert _series_sequence(make_book("A", "S", "")) == math.inf

    def test_sorts_unparseable_sequences_last(self):
        assert _series_sequence(make_book("A", "S", "bonus")) == math.inf

    def test_treats_a_book_with_no_series_as_unnumbered(self):
        assert _series_sequence(make_book("A")) == math.inf


class TestApplySeriesOrder:
    def test_puts_a_scattered_series_into_reading_order(self):
        # A scattered ordering, the way a relevance-ranked search returns a series.
        books = [
            make_book("Sample Six", "Sample Series", "6"),
            make_book("Sample Interlude", "Sample Series", "8.5"),
            make_book("Sample Eight", "Sample Series", "8"),
            make_book("Sample Seven", "Sample Series", "7"),
            make_book("Sample Nine", "Sample Series", "9"),
            make_book("Sample Five", "Sample Series", "5"),
        ]
        assert order(books) == [
            "Sample Five",
            "Sample Six",
            "Sample Seven",
            "Sample Eight",
            "Sample Interlude",
            "Sample Nine",
        ]

    def test_keeps_series_where_the_incoming_ranking_put_them(self):
        # Interleaved on the way in; each series collapses to its first position
        # rather than being re-sorted alphabetically.
        books = [
            make_book("Stone Gate", "Foundations", "1"),
            make_book("First Light", "Chronicles", "1"),
            make_book("Iron Gate", "Foundations", "2"),
            make_book("Second Light", "Chronicles", "2"),
        ]
        assert order(books) == ["Stone Gate", "Iron Gate", "First Light", "Second Light"]

    def test_leaves_standalone_books_in_place(self):
        books = [make_book("Solo One"), make_book("Solo Two"), make_book("Solo Three")]
        assert order(books) == ["Solo One", "Solo Two", "Solo Three"]

    def test_does_not_pull_standalone_books_into_a_series_run(self):
        books = [
            make_book("Series B2", "S", "2"),
            make_book("Standalone"),
            make_book("Series A1", "S", "1"),
        ]
        # The series anchors at index 0 and orders internally; the standalone book
        # keeps its own slot after it.
        assert order(books) == ["Series A1", "Series B2", "Standalone"]

    def test_sorts_unnumbered_series_entries_after_numbered_ones(self):
        books = [
            make_book("Companion", "S", None),
            make_book("Book One", "S", "1"),
            make_book("Book Two", "S", "2"),
        ]
        assert order(books) == ["Book One", "Book Two", "Companion"]

    def test_is_stable_for_equal_sequences(self):
        books = [
            make_book("First", "S", "1"),
            make_book("Second", "S", "1"),
            make_book("Third", "S", "1"),
        ]
        assert order(books) == ["First", "Second", "Third"]

    def test_handles_an_empty_list(self):
        assert order([]) == []

    def test_groups_by_series_name_across_separated_appearances(self):
        books = [
            make_book("S1 #2", "Alpha", "2"),
            make_book("Other", "Beta", "1"),
            make_book("S1 #1", "Alpha", "1"),
        ]
        assert order(books) == ["S1 #1", "S1 #2", "Other"]
