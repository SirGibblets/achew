"""Tests for re-running realignment from the editor (ProcessingPipeline.rerun_realignment) and the
pin-related chapter operations (app/models/chapter_operation.py).

Pinned chapters and chapters the user added keep their timestamps and are ground truth for the
aligner; every other realigned chapter is re-aligned. The whole re-run is one undo step.
"""

import random

import pytest

from app.api.routes.chapters import DetectedCue
from app.models.chapter import ChapterData, RealignmentData
from app.models.chapter_operation import EditTimestampOperation, SetPinnedOperation
from app.services.processing_pipeline import ProcessingPipeline, RealignmentContext

# A small book whose true boundaries all sit 3 s after the reference, each with a strong cue,
# plus weak decoy silences around them.
N_CHAPTERS = 12
OFFSET = 3.0


class _Pipeline(ProcessingPipeline):
    """A pipeline with a fixed book duration and no loaded book."""

    duration = 0.0

    @property
    def book_duration(self) -> float:
        return self.duration


def _book(seed: int = 1):
    rng = random.Random(seed)
    ref = [0.0]
    for _ in range(N_CHAPTERS - 1):
        ref.append(ref[-1] + rng.uniform(600.0, 1500.0))
    true = [0.0] + [r + OFFSET for r in ref[1:]]
    cues = []
    for t in true[1:]:
        cues.append(DetectedCue(timestamp=t, gap=3.0))
        cues.append(DetectedCue(timestamp=t + rng.uniform(8.0, 20.0), gap=0.6))
        cues.append(DetectedCue(timestamp=t - rng.uniform(8.0, 20.0), gap=0.5))
    cues.sort(key=lambda c: c.timestamp)
    return ref, true, cues, ref[-1] + 900.0


@pytest.fixture
def setup():
    ref, true, cues, duration = _book()
    pipeline = _Pipeline("item-1", lambda *args, **kwargs: None)
    pipeline.duration = duration
    pipeline.detected_cues = cues
    pipeline._realignment_context = RealignmentContext(ref_duration=duration, padding=15.0)
    pipeline.chapters = [
        ChapterData(
            timestamp=t,
            title=f"Chapter {i + 1}",
            realignment=RealignmentData(original_timestamp=r, confidence=0.85, is_guess=False),
        )
        for i, (r, t) in enumerate(zip(ref, true))
    ]
    yield pipeline, true
    pipeline.cleanup_all_files()


def _by_title(pipeline: ProcessingPipeline, title: str) -> ChapterData:
    return next(ch for ch in pipeline.chapters if ch.title == title)


def _state(pipeline: ProcessingPipeline):
    return [(ch.id, ch.timestamp, ch.realignment, ch.deleted) for ch in pipeline.chapters]


def _pin(pipeline: ProcessingPipeline, chapter: ChapterData, timestamp: float):
    chapter.timestamp = timestamp
    assert chapter.realignment is not None
    chapter.realignment = chapter.realignment.model_copy(update={"pinned": True})
    pipeline.chapters.sort(key=lambda c: c.timestamp)


def test_rerun_moves_free_chapters_back_onto_their_boundaries(setup):
    pipeline, true = setup
    # Knock two free chapters off their boundaries
    for title in ("Chapter 4", "Chapter 9"):
        _by_title(pipeline, title).timestamp += 7.0

    result = pipeline.rerun_realignment()

    assert result.realigned == N_CHAPTERS - 1
    assert result.moved == 2
    assert [ch.timestamp for ch in pipeline.chapters] == pytest.approx(true)
    assert all(ch.realignment and not ch.realignment.pinned for ch in pipeline.chapters)


def test_pinned_added_and_deleted_chapters_are_left_alone(setup):
    pipeline, _ = setup
    pinned = _by_title(pipeline, "Chapter 5")
    _pin(pipeline, pinned, pinned.timestamp + 2.0)
    pinned_before = (pinned.timestamp, pinned.realignment)

    chapter_8 = _by_title(pipeline, "Chapter 8")
    added = ChapterData(timestamp=chapter_8.timestamp + 120.0, title="Interlude")
    pipeline.chapters.append(added)
    pipeline.chapters.sort(key=lambda c: c.timestamp)

    deleted = _by_title(pipeline, "Chapter 11")
    deleted.deleted = True
    deleted.timestamp += 30.0
    deleted_before = (deleted.timestamp, deleted.realignment)

    pipeline.rerun_realignment()

    assert (pinned.timestamp, pinned.realignment) == pinned_before
    assert added.timestamp == chapter_8.timestamp + 120.0 and added.realignment is None
    assert (deleted.timestamp, deleted.realignment) == deleted_before
    # No realigned chapter lands on the added one
    assert all(abs(ch.timestamp - added.timestamp) >= 1.0 for ch in pipeline.chapters if ch is not added)


def test_free_chapters_follow_pins_and_keep_their_reference_timestamps(setup):
    pipeline, true = setup
    originals = {ch.id: ch.realignment.original_timestamp for ch in pipeline.chapters if ch.realignment}
    for title in ("Chapter 6", "Chapter 7"):
        _by_title(pipeline, title).timestamp += 9.0

    pipeline.rerun_realignment()

    assert [ch.timestamp for ch in pipeline.chapters] == pytest.approx(true)
    assert {ch.id: ch.realignment.original_timestamp for ch in pipeline.chapters if ch.realignment} == originals


def test_rerun_is_a_single_undo_step(setup):
    pipeline, _ = setup
    for title in ("Chapter 3", "Chapter 10"):
        _by_title(pipeline, title).timestamp -= 6.0
    before = _state(pipeline)

    pipeline.rerun_realignment()
    assert _state(pipeline) != before
    assert len(pipeline.history_stack) == 1

    pipeline.undo()
    assert _state(pipeline) == before

    pipeline.redo()
    assert _state(pipeline) != before


def test_rerun_with_nothing_to_change_adds_no_history(setup):
    pipeline, _ = setup

    result = pipeline.rerun_realignment()

    assert result.moved == 0
    assert pipeline.history_stack == []


def test_pin_out_of_reference_order_is_kept_in_place(setup):
    """A pin the user moved before an earlier chapter's pin can't anchor the reference; it stays
    where the user put it instead of failing the re-run."""
    pipeline, _ = setup
    chapter_6 = _by_title(pipeline, "Chapter 6")
    chapter_8 = _by_title(pipeline, "Chapter 8")
    _pin(pipeline, chapter_6, chapter_6.timestamp)
    _pin(pipeline, chapter_8, chapter_6.timestamp - 200.0)
    misplaced = chapter_8.timestamp

    pipeline.rerun_realignment()

    assert chapter_8.timestamp == misplaced


def test_rerun_requires_a_realignment(setup):
    pipeline, _ = setup
    pipeline._realignment_context = None
    with pytest.raises(ValueError):
        pipeline.rerun_realignment()


def test_rerun_requires_an_unpinned_chapter(setup):
    pipeline, _ = setup
    for chapter in pipeline.chapters[1:]:
        _pin(pipeline, chapter, chapter.timestamp)
    with pytest.raises(ValueError):
        pipeline.rerun_realignment()


def test_timestamp_edit_pins_the_chapter_and_undo_unpins_it(setup):
    pipeline, _ = setup
    chapter = _by_title(pipeline, "Chapter 4")

    operation = EditTimestampOperation(chapter_id=chapter.id, new_timestamp=chapter.timestamp + 5.0)
    operation.apply(pipeline)
    assert chapter.realignment is not None and chapter.realignment.pinned

    operation.undo(pipeline)
    assert chapter.realignment is not None and not chapter.realignment.pinned


def test_set_pinned_toggles_and_undoes(setup):
    pipeline, _ = setup
    chapter = _by_title(pipeline, "Chapter 2")

    operation = SetPinnedOperation(chapter_id=chapter.id, pinned=True)
    operation.apply(pipeline)
    assert chapter.realignment is not None and chapter.realignment.pinned

    operation.undo(pipeline)
    assert chapter.realignment is not None and not chapter.realignment.pinned


def test_set_pinned_rejects_chapters_without_realignment(setup):
    pipeline, _ = setup
    added = ChapterData(timestamp=100.0, title="Added")
    pipeline.chapters.append(added)
    with pytest.raises(ValueError):
        SetPinnedOperation(chapter_id=added.id, pinned=True).apply(pipeline)
