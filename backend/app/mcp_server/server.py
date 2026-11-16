"""Achew's MCP server: lets an agent (Claude Code, Claude Desktop, Cursor, ...) drive the same
session as the web UI, through the tools in this package."""

import importlib.metadata
import inspect
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult
from pydantic import Field

from . import tools_editing, tools_library, tools_session
from .runtime import READ_ONLY, quote, result, tool_errors, tools_revision

GUIDE_PATH = Path(__file__).with_name("guide.md")
GUIDE_URI = "achew://guide"

INSTRUCTIONS = """\
Achew finds and fixes audiobook chapters (where each starts, and its title) and saves them to Audiobookshelf.

- One book is open at a time, in a session shared with Achew's web UI: the user may be watching, sees your \
changes live, and may be editing too. Start with get_status.
- Tool results report the session's `step` and a `next` hint. Long work (download, detection, transcription) \
runs in the background: when a result says `busy: true`, call wait until it doesn't.
- Pick the workflow that keeps the most good data: realign when a chapter reference (often Audnexus, see \
find_audnexus_chapters) has the right titles; regenerate when timestamps are right but titles aren't; \
smart_detect only when nothing usable exists.
- Verify doubtful boundaries with transcribe_audio and get_nearby_cues before moving chapters. Put related \
edits in one edit_chapters call (one Undo for the user).
- submit_to_audiobookshelf replaces the book's chapters: call preview_submission, show the user, and submit \
with confirm=true only after they agree. Never close a book the user may be working on without asking.

Call get_guide (or read achew://guide) for workflow walkthroughs and title conventions."""

# Appended to INSTRUCTIONS with the revision the client connected at (see runtime.tools_revision)
REVISION_NOTE = """

Every tool description ends with the revision it was written for, like [achew rev {revision}]. get_status reports \
the server's current `tools_revision`. Clients can cache tool descriptions separately from these instructions, so \
check the tag on the tools you use: if it differs (or a description has no tag), that description is out of date \
(Achew was updated since it was loaded) and may lack parameters or fields that results show. Tell the user to reconnect Achew's MCP server (in \
Claude Code: /mcp, select achew, Reconnect); until then, trust what results say over the descriptions."""

# Appended to every tool description
REVISION_TAG = "\n\n[achew rev {revision}]"


def _finish_descriptions(server: MCPServer, revision: str) -> None:
    """Dedent each tool's description (the SDK takes docstrings as written, indentation and all)
    and tag it with the revision, so a client's cached copy shows its own age."""
    # No public API edits a registered tool, so this goes through the SDK's tool manager
    for tool in server._tool_manager.list_tools():
        tool.description = inspect.cleandoc(tool.description) + REVISION_TAG.format(revision=revision)


def _version() -> str:
    try:
        return importlib.metadata.version("achew")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _guide() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


def create_mcp_server() -> MCPServer:
    server = MCPServer(
        "achew",
        title="Achew",
        description="Audiobook Chapter Extraction Wizard: fix audiobook chapters and save them to Audiobookshelf",
        instructions=INSTRUCTIONS + REVISION_NOTE.format(revision=tools_revision()),
        website_url="https://github.com/SirGibblets/achew",
        version=_version(),
    )

    tools_library.register(server)
    tools_session.register(server)
    tools_editing.register(server)

    @server.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_guide() -> CallToolResult:
        """Achew's guide for agents: concepts, choosing a workflow, step-by-step walkthroughs, checking
        boundaries, and title conventions. Read it before your first workflow."""
        return result({"guide": _guide()})

    @server.resource(GUIDE_URI, name="guide", title="Achew agent guide", mime_type="text/markdown")
    def guide() -> str:
        """How to use Achew's tools: workflows, verification, and title conventions."""
        return _guide()

    @server.prompt(title="Clean up a book's chapters")
    def clean_up_book(
        book: Annotated[str, Field(description="The book's title, or its Audiobookshelf item id")],
    ) -> str:
        """Fix one audiobook's chapters end to end and save them to Audiobookshelf."""
        return (
            f"Use Achew to fix the chapters of the audiobook {quote(book)}.\n\n"
            "1. Call get_status and get_guide. If another book is open, ask me before closing it.\n"
            "2. Find the book with search_books and open it with open_book.\n"
            "3. Look at its chapter references and pick a workflow as the guide describes. Look for an Audnexus "
            "edition that matches this recording if no reference has good titles.\n"
            "4. Run it, then review every chapter: check low-confidence or guessed starts by listening with "
            "transcribe_audio, fix them with edit_chapters, and tidy the titles.\n"
            "5. Call preview_submission and show me a summary of the changes. Only submit to Audiobookshelf once "
            "I say so."
        )

    @server.prompt(title="Audit a library")
    def audit_library(
        library: Annotated[str, Field(description="Library name or id; empty for the first book library")] = "",
    ) -> str:
        """Find books whose chapters need work, and fix them one at a time."""
        target = f"the library {quote(library)}" if library else "my Audiobookshelf book library"
        return (
            f"Use Achew to audit {target} for bad chapters.\n\n"
            "1. Call get_status and get_guide, then list_libraries to find the library.\n"
            "2. Call find_books_needing_cleanup and show me what it found, grouped by problem, with your "
            "suggested fix for each (the workflow and reference you'd use).\n"
            "3. When I pick books, fix them one at a time: open, run the workflow, review and verify, then show "
            "me preview_submission. Submit only books I approve, then close_session before the next one."
        )

    @server.prompt(title="Review the open book")
    def review_open_book() -> str:
        """Check and tidy the chapters of the book that's open in Achew right now."""
        return (
            "A book is open in Achew's chapter editor. Review its chapters for me.\n\n"
            "1. Call get_status, get_guide and list_chapters.\n"
            "2. Check chapters whose start looks doubtful (low confidence, guessed, very short or very long) by "
            "listening with transcribe_audio and looking at get_nearby_cues.\n"
            "3. Propose fixes to starts and titles, then apply the ones I agree with in a single edit_chapters "
            "call. Don't submit; I'll review it in the web UI."
        )

    _finish_descriptions(server, tools_revision())
    return server
