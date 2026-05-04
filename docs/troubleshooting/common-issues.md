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

## xHE-AAC books fail

These books are not currently supported in Achew. See [Supported Formats](../reference/supported-formats.md).

## First launch takes forever

Achew is downloading and installing Python dependencies and building the project. This process may take several minutes, but subsequent launches will be much faster.

## Related

- [Performance Tuning](performance-tuning.md)
- [Logs and Support](logs-and-support.md)
