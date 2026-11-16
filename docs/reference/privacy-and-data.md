# Privacy and Data

Achew talks to:

- Your Audiobookshelf server for finding books and saving chapters.
- LLM providers for AI Cleanup (optional).
- Hugging Face to download transcription models.
- Your transcription server, if you use the OpenAI-Compatible API transcription service (optional).
- GitHub to check for new versions of Achew, and to download them when you update.
- GitHub, nodejs.org, PyPI, and the npm registry to download Achew's tools and dependencies when a native install launches.

## Audiobookshelf

Achew reads book metadata, audio files, and Chapter Reference data from your ABS server, and writes chapter data back on submit. All of this happens over your LAN (or whatever network connection you use between Achew and ABS). Nothing is proxied through a third party.

## LLM providers (AI Cleanup)

AI Cleanup sends the following to your selected provider:

- The chapter **titles** you are cleaning up.
- The book's **title** and **author**.
- Titles from the **Prefer existing titles from** Reference, if that option is enabled.
- Any **Additional Instructions** and active **Custom Instructions**.
- The Achew prompt template.

No audio is sent. If you use a locally hosted provider (Ollama, LM Studio, or a self-hosted OpenAI-compatible endpoint), all cleanup data remains local as well. If an OpenAI-compatible endpoint is a gateway that forwards requests to a hosted service, the cleanup data is sent wherever that gateway routes it.


## Transcription

Achew reaches out to Hugging Face to download any requested transcription models. **With the built-in services (Whisper and Parakeet), all transcription runs locally on the Achew host;** nothing is uploaded to a third party.

The [OpenAI-Compatible API](transcription.md#openai-compatible-api) service sends a short audio segment from the start of each chapter (a few seconds, set by **Transcription Length**), along with the selected language and any Bias Words, to the server you configure. If that server is self-hosted, the audio stays on your own hardware; if it is a cloud service, the audio is handled under that provider's terms.

## AI agents (Agent Access)

[Agent Access](../getting-started/agent-access.md) is off by default. When you turn it on and connect an agent, your agent's AI provider sees what the agent reads from Achew: book titles, authors, and durations, chapter titles and timestamps, your Chapter Search results, and the text of any audio the agent asks to transcribe. Achew never sends audio to the agent; transcription happens in Achew with your transcription settings, as above.

## Upgrade checks

On launch, Achew queries the GitHub Releases API to check for a new version. This is a plain GitHub API call (no account info) and can be blocked at the network level if desired; it only affects the upgrade icon.

Updating a native install, from the app or with `--update`, downloads the new release from GitHub.

## Installing and launching

Native installs download their own copies of uv and Python from GitHub and Node.js from nodejs.org, and Achew's Python and JavaScript dependencies from PyPI and the npm registry. Docker images come with all of this already installed.

## Local storage

- API keys (ABS, LLM, transcription server) and the Agent Access token are stored in plain text in `app_config.json` in the Settings directory. See [Storage and Backup](../installation/storage-and-backup.md) for more information.
- Browser `localStorage` holds your theme preference, last-used Audnexus search region, last-selected library, and notification chime settings. Nothing sensitive.

## Notes on privacy

- Achew does not phone home. Telemetry is not collected.
- Achew does not upload audio anywhere, except to a transcription server you configure for the OpenAI-Compatible API service. Any temporary audio files are stored locally and are immediately deleted when a session is completed or canceled.

## Related

- [Reverse Proxy](../installation/reverse-proxy.md)
- [Setup LLM Providers](../getting-started/setup-llm-providers.md)
- [Storage and Backup](../installation/storage-and-backup.md)
