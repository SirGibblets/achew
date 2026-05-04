# Supported Languages

## Smart Detect

Smart Detect is language-agnostic; it works with any language. 

## Transcription

Language support depends on which **model variant** you pick within each service.

### Parakeet

| Variant | Languages |
|---|---|
| **0.6B v2** | English only (recommended for English audio) |
| **0.6B v3** | Multilingual; auto-detects language |

The `v3` model supports: Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Russian, Slovak, Slovenian, Spanish, Swedish, Ukrainian.

### Whisper

Whisper supports 99+ languages to varying degrees. See the full list [here](https://whisper-api.com/docs/languages/){:target="_blank"}.

Each Whisper size (`tiny` / `base` / `small` / `medium`) also has an **English-only** variant (e.g. `tiny.en`, `base.en`, etc.). These are trained exclusively on English audio and are usually *more accurate on English* than the equivalent multilingual size. The `large` and `turbo` variants are multilingual only.

### Picking a Whisper language

On the **Transcribe Titles** screen, Achew tries to preselect the language based on the book's language set in Audiobookshelf. If that metadata is missing or wrong, you'll want to specify manually.

Whisper's accuracy can drop significantly if you use the `Auto` language option; always pick explicitly when you know. For English books, prefer the English-only variant of a given model over the multilingual one.

## AI Cleanup (LLMs)

Most LLM providers can handle several languages, with larger cloud services capable of dozens of languages. Each provider has its own strengths and weaknesses; you'll want to research which options will work best for your own library.

If cleanup results look wrong for a non-English book:

- Make sure that **Custom/Additional Instructions** are not accidentally coercing English output.
- Add a Custom Instruction like "Keep titles in the book's original language."
- Try a different model or provider.

## Related

- [Transcription](transcription.md)
- [AI Cleanup](../editor/ai-cleanup.md)
