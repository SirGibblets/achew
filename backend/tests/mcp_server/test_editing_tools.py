"""Tests for the MCP server's chapter editor tools (app/mcp_server/tools_editing.py): listing,
batched edits as one undo step, selection, undo/redo, and the submit preview and guards."""

from mcp_helpers import (
    STARTS,
    call,
    call_error,
    connect,
    make_pipeline,
)

from app.mcp_server.runtime import short_id
from app.models.enums import Step


def _by_title(pipeline, title):
    return next(c for c in pipeline.chapters if c.title == title and not c.deleted)


async def test_list_chapters_shows_short_ids_lengths_and_times(app_state):
    app_state.pipeline = make_pipeline()
    async with connect() as client:
        data = await call(client, "list_chapters")
    chapters = data["chapters"]
    assert [c["title"] for c in chapters] == ["Opening Credits", "Chapter 1", "Chapter 2", "Chapter 3"]
    assert [c["n"] for c in chapters] == [1, 2, 3, 4]
    assert chapters[1]["time"] == "0:10:00.0"
    assert chapters[1]["length"] == "15:00"
    assert chapters[-1]["length"] == "20:00"
    assert all(len(c["id"]) == 8 for c in chapters)
    # Unset fields are left out rather than sent as null
    assert "realign" not in chapters[0] and "excluded" not in chapters[0]


async def test_edit_chapters_applies_a_batch_as_one_undo_step(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    one, two = _by_title(pipeline, "Chapter 1"), _by_title(pipeline, "Chapter 2")
    async with connect() as client:
        data = await call(
            client,
            "edit_chapters",
            changes=[
                {"action": "rename", "id": short_id(one), "title": "The Beginning"},
                {"action": "move", "id": short_id(two)[:5], "start": "0:25:03.5"},
                {"action": "delete", "id": short_id(_by_title(pipeline, "Chapter 3"))},
                {"action": "add", "start": 3000, "title": "Epilogue"},
            ],
        )
        assert len(data["applied"]) == 4
        assert data["chapters_now"] == 4
        assert one.title == "The Beginning"
        assert two.timestamp == 1503.5
        assert [c.title for c in pipeline.chapters if not c.deleted] == [
            "Opening Credits",
            "The Beginning",
            "Chapter 2",
            "Epilogue",
        ]

        # One Undo reverts the whole batch
        await call(client, "undo")
        assert [(c.timestamp, c.title) for c in pipeline.chapters if not c.deleted] == list(
            zip(STARTS, ["Opening Credits", "Chapter 1", "Chapter 2", "Chapter 3"])
        )
        await call(client, "redo")
        assert one.title == "The Beginning"


async def test_an_invalid_change_leaves_every_chapter_untouched(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    before = [(c.id, c.timestamp, c.title, c.deleted) for c in pipeline.chapters]
    one = _by_title(pipeline, "Chapter 1")
    async with connect() as client:
        error = await call_error(
            client,
            "edit_chapters",
            changes=[
                {"action": "rename", "id": short_id(one), "title": "Renamed"},
                # Lands on Chapter 2's start
                {"action": "move", "id": short_id(one), "start": STARTS[2]},
            ],
        )
    assert "Change 2 (move)" in error and "already starts" in error
    assert [(c.id, c.timestamp, c.title, c.deleted) for c in pipeline.chapters] == before
    assert not pipeline.can_undo()


async def test_edit_errors_name_the_problem(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    async with connect() as client:
        assert "No chapter with id" in await call_error(
            client, "edit_chapters", changes=[{"action": "delete", "id": "ffffffff"}]
        )
        assert "outside the book" in await call_error(
            client, "edit_chapters", changes=[{"action": "add", "start": 99999, "title": "x"}]
        )
        assert "can't be pinned" in await call_error(
            client, "edit_chapters", changes=[{"action": "pin", "id": short_id(pipeline.chapters[1])}]
        )
        assert "no chapters" in await call_error(
            client,
            "edit_chapters",
            changes=[{"action": "delete", "id": short_id(c)} for c in pipeline.chapters],
        )


async def test_editing_needs_the_chapter_editor(app_state):
    app_state.pipeline = make_pipeline(step=Step.SELECT_WORKFLOW)
    async with connect() as client:
        error = await call_error(client, "edit_chapters", changes=[{"action": "add", "start": 10, "title": "x"}])
    assert "needs chapter_editing" in error
    assert "start_workflow" in error  # the hint for what to do instead


async def test_moving_a_realigned_chapter_pins_it(app_state):
    pipeline = make_pipeline(realigned=True)
    app_state.pipeline = pipeline
    two = _by_title(pipeline, "Chapter 2")
    async with connect() as client:
        await call(client, "edit_chapters", changes=[{"action": "move", "id": short_id(two), "start": 1490}])
        data = await call(client, "list_chapters")
    view = next(c for c in data["chapters"] if c["title"] == "Chapter 2")
    assert view["realign"]["pinned"] is True


async def test_selection_excludes_chapters_from_the_preview(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    async with connect() as client:
        await call(
            client, "set_chapter_selection", selected=False, chapter_ids=[short_id(_by_title(pipeline, "Chapter 3"))]
        )
        listed = await call(client, "list_chapters")
        preview = await call(client, "preview_submission")
    assert listed["chapters"][-1]["excluded"] is True
    assert preview["will_write"] == 3
    assert preview["removed"] == 1
    assert any("excluded" in w for w in preview["warnings"])


async def test_preview_compares_with_the_chapters_in_audiobookshelf(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    async with connect() as client:
        await call(
            client,
            "edit_chapters",
            changes=[
                {"action": "rename", "id": short_id(_by_title(pipeline, "Chapter 1")), "title": "Chapter One"},
                {"action": "move", "id": short_id(_by_title(pipeline, "Chapter 2")), "start": 1530},
                {"action": "add", "start": 3300, "title": "Afterword"},
            ],
        )
        preview = await call(client, "preview_submission")
        full = await call(client, "preview_submission", full=True)
    assert (preview["unchanged"], preview["retitled"], preview["moved"], preview["added"], preview["removed"]) == (
        2,
        1,
        1,
        1,
        0,
    )
    # An added chapter is listed once, under new_chapters, not repeated in the changes; the whole
    # chapter list only comes with full=true, where new chapters are marked
    assert "chapters" not in preview
    assert preview["new_chapters"] == [{"n": 5, "time": "0:55:00.0", "title": "Afterword"}]
    assert not any("Afterword" in change for change in preview["changes"])
    assert full["chapters"][-1] == {"n": 5, "time": "0:55:00.0", "title": "Afterword", "new": True}
    assert "new_chapters" not in full


async def test_submit_needs_confirmation(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    async with connect() as client:
        error = await call_error(client, "submit_to_audiobookshelf")
    assert "confirm=true" in error
    assert pipeline.submitted is None


async def test_submit_writes_the_included_chapters(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    async with connect() as client:
        data = await call(client, "submit_to_audiobookshelf", confirm=True)
    assert data["written"] == 4
    assert data["step"] == "completed"
    assert pipeline.submitted is not None and len(pipeline.submitted) == 4


async def test_submit_can_be_turned_off_for_agents(app_state, app_config):
    app_config.mcp.allow_submit = False
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    async with connect() as client:
        error = await call_error(client, "submit_to_audiobookshelf", confirm=True)
    assert "turned off submitting" in error
    assert pipeline.submitted is None
    # The user is left on the Review screen to submit themselves
    assert pipeline.step == Step.REVIEWING


async def test_preview_pairs_a_chapter_that_moved_and_was_renamed(app_state):
    pipeline = make_pipeline()
    app_state.pipeline = pipeline
    one = _by_title(pipeline, "Chapter 1")
    async with connect() as client:
        await call(
            client,
            "edit_chapters",
            changes=[
                {"action": "move", "id": short_id(one), "start": 608.1},
                {"action": "rename", "id": short_id(one), "title": "Chapter One"},
            ],
        )
        preview = await call(client, "preview_submission")
    assert (preview["moved"], preview["retitled"], preview["added"], preview["removed"]) == (1, 1, 0, 0)
    assert preview["changes"] == ["0:10:00.0 -> 0:10:08.1 (+8.1 s): \u201cChapter 1\u201d -> \u201cChapter One\u201d"]
