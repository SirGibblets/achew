# Privacy and Data

Achew talks to:

- Your Audiobookshelf server for finding books and saving chapters.
- LLM providers for AI Cleanup (optional).
- Hugging Face to download transcription models.
- The GitHub Releases API to check for new versions of Achew.

## Audiobookshelf

Achew reads book metadata, audio files, and chapter source data from your ABS server, and writes chapter data back on submit. All of this happens over your LAN (or whatever network connection you use between Achew and ABS). Nothing is proxied through a third party.

## LLM providers (AI Cleanup)

AI Cleanup sends the following to your selected provider:

- The chapter **titles** you are cleaning up.
- The book's **title** and **author**.
- Titles from the **Prefer existing titles from** source, if that option is enabled.
- Any **Additional Instructions** and active **Custom Instructions**.
- The Achew prompt template.

No audio is sent. If you locally host and use Ollama or LM Studio as your provider, all cleanup data remains local as well.


## Transcription

Achew reaches out to Hugging Face to download any requested transcription models. **All transcription runs locally on the Achew host;** nothing is uploaded to a third party.

## Upgrade checks

On launch, Achew queries the GitHub Releases API to check for a new version. This is a plain GitHub API call (no account info) and can be blocked at the network level if desired; it only affects the upgrade icon.

## Local storage

- API keys (ABS, LLM) are stored in plain text in `app_config.json` in the Settings directory. See [Storage and Backup](../installation/storage-and-backup.md) for more information.
- Browser `localStorage` holds your theme preference, last-used Audnexus search region, last-selected library, and notification chime settings. Nothing sensitive.

## Notes on privacy

- Achew does not phone home. Telemetry is not collected.
- Achew does not upload audio anywhere. Any temporary audio files are stored locally and are immediately deleted when a session is completed or canceled.

## Related

- [Reverse Proxy](../installation/reverse-proxy.md)
- [Setup LLM Providers](../getting-started/setup-llm-providers.md)
- [Storage and Backup](../installation/storage-and-backup.md)
