# Agent Access (MCP)

Achew has a built-in [MCP](https://modelcontextprotocol.io){:target="_blank"} server, so an AI agent such as Claude Code, Claude Desktop, or Cursor can use Achew for you. An agent can find books with bad chapters, pick and run a workflow, listen to the audio to check where chapters start, fix titles, and save the result to Audiobookshelf once you approve it.

The agent works in the same session as Achew's web UI. If you have Achew open in a browser, you see every change the agent makes as it happens, and you can undo its edits like your own.

## Turn on Agent Access

Agent Access is off until you turn it on.

1. Open the :lucide-settings:{ .icon-token } **Settings** menu and choose **Agent Access**.
2. Check **Allow agents to connect**. Achew creates a token that agents must send with every request.
3. Under **Connect your agent**, pick your agent and copy the command or config it shows (the token is already filled in).

!!! warning "Treat the token like a password"
    Anyone with the token can control Achew, including saving chapters to your Audiobookshelf library. If it leaks, click **Regenerate token**: agents using the old one are disconnected until you give them the new one.

### Saving to Audiobookshelf

**Let agents save chapters to Audiobookshelf** is on by default. Agents are told to show you what will change and ask before saving, and most agents also ask you to approve each save.

Turn it off to keep agents edit-only. When an agent finishes, Achew shows its Review screen, and you click **Submit** yourself.

## Connect your agent

The server address is the address you open Achew at, followed by `/mcp`, for example `http://localhost:8000/mcp`. Replace `YOUR_TOKEN` below with the token from the Agent Access dialog, or copy the ready-made version from the dialog instead.

=== "Claude Code"

    Run this in a terminal, then start Claude Code and check that `achew` is listed under `/mcp`:

    ```bash
    claude mcp add --transport http achew http://localhost:8000/mcp --header "Authorization: Bearer YOUR_TOKEN"
    ```

=== "Claude Desktop"

    Claude Desktop connects to local servers through the [mcp-remote](https://www.npmjs.com/package/mcp-remote){:target="_blank"} bridge, which needs [Node.js](https://nodejs.org){:target="_blank"}. Open **Settings → Developer → Edit Config**, add this to `claude_desktop_config.json`, and restart Claude Desktop:

    ```json
    {
      "mcpServers": {
        "achew": {
          "command": "npx",
          "args": ["-y", "mcp-remote", "http://localhost:8000/mcp", "--header", "Authorization:${ACHEW_AUTH}"],
          "env": { "ACHEW_AUTH": "Bearer YOUR_TOKEN" }
        }
      }
    }
    ```

    If Achew runs on another machine and you connect over plain `http://`, add `"--allow-http"` to the end of `args`.

=== "Cursor"

    Add this to `~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project):

    ```json
    {
      "mcpServers": {
        "achew": {
          "url": "http://localhost:8000/mcp",
          "headers": { "Authorization": "Bearer YOUR_TOKEN" }
        }
      }
    }
    ```

=== "VS Code"

    Add this to `.vscode/mcp.json`, or run **MCP: Open User Configuration**:

    ```json
    {
      "servers": {
        "achew": {
          "type": "http",
          "url": "http://localhost:8000/mcp",
          "headers": { "Authorization": "Bearer YOUR_TOKEN" }
        }
      }
    }
    ```

Other agents that support remote (Streamable HTTP) MCP servers work the same way: give them the server address and the `Authorization: Bearer YOUR_TOKEN` header.

## What agents can do

| Area | What the agent can do |
|------|-----------------------|
| Find books | List libraries, search for books, and audit a library with your [Chapter Search](finding-a-book.md#chapter-search) rules. |
| Run workflows | Open a book, compare its [Chapter References](chapter-references.md), find a matching Audnexus edition, and run any [workflow](workflows-overview.md), including picking cues after Smart Detect. |
| Check chapters | Listen to the audio at any point (using your [transcription](../reference/transcription.md) settings) and look at the detected cues near a chapter. |
| Edit chapters | Rename, move, add, delete, pin, and include or exclude chapters, re-run realignment, and undo or redo. |
| Save | Preview the changes against Audiobookshelf's current chapters, then save them (if you allow it). |

An agent's edits go into the same undo history as yours, and each batch of changes is a single undo step. Agents don't change Achew's settings.

Agents get instructions on how to use Achew when they connect, plus a longer guide covering workflows, how to check boundaries, and title conventions. Achew also hands them the **Custom Instructions** you've enabled for [AI Cleanup](../editor/ai-cleanup.md), so they can follow your title preferences.

## Example requests

Once your agent is connected, ask it in plain language:

- "Fix the chapters of *Project Hail Mary* in Achew."
- "Audit my Audiobooks library for bad chapters, and suggest a fix for each book."
- "I have a book open in Achew. Check the chapters it guessed and fix any that are wrong, but don't submit."
- "Realign *Dune* to the Audnexus chapters, then show me what would change."

Some agents also show Achew's built-in prompts as commands. In Claude Code, type `/` to find `/mcp__achew__clean_up_book`, `/mcp__achew__audit_library`, and `/mcp__achew__review_open_book`.

See [Fix chapters with an AI agent](../examples/fix-chapters-with-an-ai-agent.md) for a full example.

## Good to know

- **One book at a time.** Achew has a single session, shared by you and the agent. An agent won't open another book while one is open; it asks you to finish or close it first.
- **Transcription needs a service.** To listen to the audio, the agent uses the transcription service in your [Transcription Settings](../reference/transcription.md).
- **No LLM provider needed.** The agent cleans up titles itself, so you don't need to [set up an LLM provider](setup-llm-providers.md) for AI Cleanup.
- **Long steps run in the background.** Downloading and detecting can take minutes. The agent checks back until they finish, and you can follow the progress in the web UI.
- **Reconnect after updating Achew.** Agents load Achew's tool descriptions when they connect, so after an update they can be out of date until the agent reconnects (in Claude Code, run `/mcp`, select `achew`, and choose **Reconnect**). Agents can tell when this happens and will ask you to.

## Privacy

Your agent's AI provider sees what the agent reads from Achew: book titles, authors, and durations, chapter titles and timestamps, your Chapter Search results, and the text of any audio the agent asks to transcribe. Achew never sends audio to the agent. Transcription happens in Achew, with your [transcription](../reference/transcription.md) settings. See [Privacy and Data](../reference/privacy-and-data.md).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| The agent gets **404** with "Achew's MCP server is turned off" | Turn on **Allow agents to connect** in **Settings → Agent Access**. |
| The agent gets **403** | The token is missing or wrong (or was regenerated). Copy the connection settings again from the Agent Access dialog. |
| The agent can't reach Achew | Check the address: it's the one you open Achew at, plus `/mcp`. If Achew runs on another machine, it must be [reachable from it](../installation/reverse-proxy.md#make-achew-reachable-from-the-proxy). |
| It works locally but not through a reverse proxy | See [Reverse Proxy](../installation/reverse-proxy.md#agent-access). |

## Related

- [Fix chapters with an AI agent](../examples/fix-chapters-with-an-ai-agent.md)
- [Choosing a Workflow](workflows-overview.md)
- [Reverse Proxy](../installation/reverse-proxy.md)
- [Privacy and Data](../reference/privacy-and-data.md)
