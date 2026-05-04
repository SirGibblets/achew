# Supported Formats

## Audio

Achew works with most audiobook files, including these common formats:

- **MP3** (`.mp3`)
- **M4B / M4A / MP4 audio** (`.m4b`, `.m4a`, `.mp4`)
- **FLAC** (`.flac`)
- **OGG / Vorbis / Opus** (`.ogg`, `.opus`)
- **WAV** (`.wav`)

Both single-file and multi-file audiobooks are supported.

!!! warning "Unsupported codec: xHE-AAC"

    Due to ffmpeg's limited support, Achew cannot reliably process audiobooks encoded as **xHE-AAC**. Smart Detect, chapter realignment, title transcription, and audio playback may all fail or produce incorrect results for these audiobooks.

    Achew automatically detects these files and shows a warning banner during workflow selection.

## Chapter source formats

- **JSON**
- **CSV**
- **CUE sheet**
- **TXT**
- **EPUB**

See [Chapter Sources](../getting-started/chapter-sources.md) for more details.

## Export formats

Achew can export to:

- **CSV**
- **JSON**
- **CUE**

See [Review and Submit](../editor/review-submit-export.md) for more details.
