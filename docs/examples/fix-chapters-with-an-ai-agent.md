# Fix chapters with an AI agent

Use this when you'd rather describe what you want than click through it yourself. An AI agent connected through [Agent Access](../getting-started/agent-access.md) does the work in Achew, while you watch in the web UI and approve the result.

This example uses Claude Code, but any agent that supports MCP works the same way.

## Before you start

1. [Turn on Agent Access](../getting-started/agent-access.md#turn-on-agent-access) and connect your agent.
2. Set up a [transcription service](../reference/transcription.md), so the agent can listen to the audio to check chapter boundaries.
3. Open Achew in a browser if you want to follow along. Every step the agent takes shows up there.

## Ask for the fix

Tell the agent what you want, in plain language:

> Fix the chapters of *Exoplanet* in Achew. Show me what will change before saving anything.

Or, in Claude Code, run the built-in prompt `/mcp__achew__clean_up_book` and give it the book's title.

## What the agent does

A typical session looks like this. The agent decides each step from what it finds, so yours may differ.

1. **Checks in.** It reads Achew's status (is a book already open? which transcription service is set up?) and Achew's guide for agents.
2. **Opens the book.** It searches your library, opens the book, and waits while Achew downloads it. In the web UI, Achew moves to the *Select a Workflow* screen.
3. **Compares the references.** It finds that the current Audiobookshelf chapters have good titles, and looks up Audnexus for a matching edition to compare the timing with.
4. **Picks a workflow.** Since the titles are right, it runs [Realign Chapters](../workflows/realign-chapters.md). Because the book is a full-cast production, it may choose the **Dramatized** detection mode.
5. **Checks the result.** In the editor, it lists the chapters and looks closer at any with low confidence: it transcribes a few seconds before and at each chapter's start, and checks the detected cues nearby. A chapter that starts on the wrong pause gets moved, and then realignment is re-run around it.
6. **Tidies the titles.** It applies one consistent style, following any [Custom Instructions](../editor/ai-cleanup.md#custom-instructions) you've enabled for AI Cleanup.
7. **Shows you the changes.** It previews the submission and summarizes it for you, for example:

    > 9 chapters will be written. 5 moved by 5 to 7 seconds to the actual episode breaks (e.g. *Episode 4: Harm's Way* 1:52:11 → 1:52:18), 3 unchanged, 1 retitled. No warnings. Shall I save them to Audiobookshelf?

8. **Saves when you say so.** After you agree, it submits the chapters to Audiobookshelf and closes the session.

If you'd rather submit yourself, tell the agent not to save, or turn off **Let agents save chapters to Audiobookshelf** in **Settings → Agent Access**. The agent then leaves the book on the Review screen for you.

## Stepping in

You can take over at any point. Edit a chapter in the web UI and the agent sees the change the next time it looks. Use **Undo** to revert the agent's last batch of edits, or tell the agent to undo them.

## More things to ask

- **Audit a library:** "Find books in my Audiobooks library with bad chapters, group them by problem, and suggest a fix for each." The agent uses your [Chapter Search](audit-library-with-chapter-search.md) rules, then works through the books you pick, one at a time.
- **Start from scratch:** "This book has no chapters. Detect them, use the ebook's table of contents for the titles, and show me the result." Paste the table of contents into the chat, and the agent adds it as a title reference.
- **Review a book you're working on:** "I have a book open in Achew. Check the chapters it guessed, fix any that are wrong, but don't submit." (Or run `/mcp__achew__review_open_book` in Claude Code.)

## Related

- [Agent Access (MCP)](../getting-started/agent-access.md)
- [Choosing a Workflow](../getting-started/workflows-overview.md)
- [Realign Chapters](../workflows/realign-chapters.md)
- [Audit your library with Chapter Search](audit-library-with-chapter-search.md)
