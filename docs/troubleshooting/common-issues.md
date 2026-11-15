# Common Issues

## Transcription crashes on Docker

If Whisper transcription hangs or exits unexpectedly in Docker, your CPU may lack AVX2 support. Switch to the `legacy-cpu` image tag. See [Transcription → legacy-cpu](../reference/transcription.md#legacy-cpu-docker-image).

## Titles are inconsistent after transcription

Transcription models can vary wildly on capitalization, number formatting, and punctuation. For the most part that's just the nature of the beast, but there are a few things you can do:

1. Use an English-only[^@] model for English audio, or a multilingual[^#] model for other audio.
1. For non-English audio with Whisper, ensure you've selected a language (*not* `Auto`).
1. Step up to a larger Whisper variant (`tiny` → `small` → `turbo`), or switch to Parakeet.
1. Enable [Bias Words](../reference/transcription.md) and add book-specific names and terms.
1. Run [AI Cleanup](../editor/ai-cleanup.md) as a post-processing step and let a machine do the work for you.

[^@]: English-only models: Parakeet `0.6b v2`, Whisper `.en`
[^#]: Multilingual models: Parakeet `0.6b v3`, Whisper non-`.en`

## "Unsupported Audio Codec (xHE-AAC)" warning

Achew's bundled ffmpeg decodes xHE-AAC audiobooks, so this warning means Achew is running a different ffmpeg that lacks the `libfdk_aac` decoder. This happens when `ACHEW_FFMPEG` points to another build, or on platforms without a bundled build. Unset `ACHEW_FFMPEG` (or point it to an ffmpeg with `libfdk_aac`) and reload the book. See [Supported Formats](../reference/supported-formats.md#xhe-aac).

## First launch takes forever

Achew is downloading its [bundled tools](../installation/installation-linux-macos.md#bundled-tools) and Python dependencies, then building the project. This process may take several minutes, but subsequent launches will be much faster.

## Achew doesn't come back after updating

After an in-app update, Achew restarts through its run script, which reinstalls dependencies and rebuilds the app before starting again. If the page keeps waiting, check the terminal or window Achew runs in for an error. Once the problem is fixed, start Achew again with `./run.sh` (or `run.bat` on Windows).

## Downloading uv or Node.js fails on launch

The run script downloads uv from GitHub and Node.js from nodejs.org. If a firewall or proxy blocks either site, or the download is interrupted, the script stops with an error and keeps nothing it downloaded, so running it again retries cleanly. A *checksum mismatch* error means the file that arrived differs from the one Achew expects, which is usually caused by a proxy that rewrites downloads. If you can't allow these downloads, install uv and Node.js yourself and set `ACHEW_SYSTEM_TOOLS=1`. See [Using your own uv and Node.js](../installation/installation-linux-macos.md#bundled-tools).

## Uploading an e-book Reference fails

Reference uploads are split into 512 KB chunks, which is usually small enough to fit within the default body size limit of most reverse proxies. If an upload still fails while small `.txt`, `.json`, `.cue`, and `.csv` files work, your proxy is likely capping request bodies below that and rejecting the chunks with the error message *"The file was rejected as too large before it reached Achew".*

To confirm, connect to Achew directly over your local network (`http://IP:PORT`) and retry the same upload. If it succeeds there, raise the body-size limit on your proxy — see [Reverse Proxy → Troubleshooting](../installation/reverse-proxy.md#troubleshooting).

## Related

- [Performance Tuning](performance-tuning.md)
- [Logs and Support](logs-and-support.md)
