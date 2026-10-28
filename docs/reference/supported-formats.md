# Supported Formats

## Audio

Achew works with these audio formats:

- **MP3** (`.mp3`)
- **M4B / M4A / MP4 audio** (`.m4b`, `.m4a`, `.mp4`)
- **AAC** (`.aac`), including [xHE-AAC](#xhe-aac)
- **FLAC** (`.flac`)
- **OGG / Vorbis / Opus** (`.ogg`, `.opus`)
- **WAV / AIFF** (`.wav`, `.aiff`)
- **WMA** (`.wma`)
- **Matroska audio** (`.mka`)
- **CAF**, **AC-3**, and **E-AC-3** (`.caf`, `.ac3`, `.eac3`)

Both single-file and multi-file audiobooks are supported.

Achew installs its own build of [ffmpeg](glossary.md#ffmpeg), trimmed down to the formats above. If you have an audiobook in another format, set the `ACHEW_FFMPEG` [environment variable](../installation/index.md#environment-variables) to the path of a full ffmpeg build.

### xHE-AAC

Some audiobooks are encoded as **xHE-AAC**, a newer and more efficient version of AAC. Achew's ffmpeg build includes the Fraunhofer FDK AAC decoder, so Smart Detect, chapter realignment, and title transcription work on these books like any other. Most browsers can't play xHE-AAC, so Achew converts the audio on the fly when you preview these books.

You can view a book's codec at any time from the **Book Info** dialog (click the book title at the top-left of the page).

!!! warning "Using your own ffmpeg"

    If `ACHEW_FFMPEG` points to an ffmpeg without the `libfdk_aac` decoder, Achew shows a warning banner for xHE-AAC books during workflow selection, and Smart Detect, chapter realignment, title transcription, and audio playback may fail or produce incorrect results.

## Chapter/Title Reference formats

- **JSON**
- **CSV**
- **CUE sheet**
- **TXT**
- **E-Book** (`.epub`, `.mobi`, `.azw`, `.azw3`)

See [Chapter References](../getting-started/chapter-references.md) for more details.

## Export formats

Achew can export to:

- **CSV**
- **JSON**
- **CUE**

See [Review and Submit](../editor/review-submit-export.md) for more details.
