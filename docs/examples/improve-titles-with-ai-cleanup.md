# Improve titles with AI Cleanup

Follow these steps when you have chapter titles in the editor with many spelling errors, poor formatting, incorrect punctuation, or other issues, and you don't want to clean them up manually. **AI Cleanup** can help normalize your chapter titles by handing them off to an LLM and letting the machine work its magic. It's also a good place to establish your formatting and styling preferences using  **Custom Instructions** so that future cleanups across your library follow the same rules.

## Load the chapters

If you're already in the editor after another workflow, you're set. Otherwise:

1. Select the book.
2. Choose **Quick Edit** on the *Select a Workflow* screen.
3. Pick the source with the titles you want to clean up and click **Open in Editor.**

## Open AI Cleanup

1. Select the chapters you want to clean up. The top checkbox selects all of them.
2. Click the :material-creation:{ .icon-token .inverted-primary } **Clean Up Selected** button in the Action Bar.

## Pick a provider and model

Use the dropdowns in the top left of the dialog to choose a provider and model. If you haven't set up any providers yet, follow [Set up LLM Providers](../getting-started/setup-llm-providers.md) first. Most cloud providers cost very little per cleanup, but there are also a few free options to pick from.

## Pick the cleanup options

- **Infer opening credits/intro** / **Infer end credits/outro**: Useful if your selection contains an intro or outro chapter that isn't already labeled as such (e.g. *Opening Credits*, *End Credits*).
- **Deselect Non-Chapters**: Drops rows that don't look like chapter titles.
- **Prefer existing titles from:** Points AI Cleanup at the titles in another [chapter source](../getting-started/chapter-sources.md) (e.g. an Audnexus or EPUB title list) as a reference. This can be useful for establishing correct spelling or adding missing title text.

## Add Custom Instructions to define your style

Custom Instructions sit in the right column of the dialog. They are reusable, persist across sessions, and supersede the default rules, making them great for building a consistent chapter style you want applied across your library.

Some examples:

- *Use words, not numerals, for chapter numbers (Chapter Twelve, not Chapter 12).*
- *Use Title-case for all chapter titles.*
- *Strip any leading "Chapter #: " prefix and keep only the descriptive title.*
- *Preserve series-specific terms like Interlude, Coda, and Reprise verbatim.*
- *Always use a hyphen between the chapter number and the descriptive title.*

Manage them with:

- :lucide-plus:{ .icon-token } **Add**, **edit**, and :lucide-trash-2:{ .icon-token } **delete** to maintain the list.
- :material-checkbox-marked:{ .icon-token .primary } **Toggle** the checkbox next to each instruction to enable or disable it without deleting it.
- :lucide-grip-vertical:{ .icon-token } **Reorder** with the grip handle to organize the rules as you see fit.

## Use Additional Instructions for one-offs

Below the Custom Instructions list is the **Additional Instructions** field. Use this for book-specific rules that you don't want saved permanently. For example: *"This book uses Roman numerals for chapter numbers, preserve them as-is."* These are cleared after you submit.

## Run, review, and submit

1. Click **Clean Up** to run the pass.
2. Review the applied changes in the editor. If the results aren't right, use the :lucide-undo:{ .icon-token } undo button to revert the changes. Then tweak the cleanup options and instructions, and run again.
3. When ready, click **Review Selected**, then [submit to Audiobookshelf or export](../editor/review-submit-export.md).

## Scenario: Titles are too generic

If every title is something like `Track 01` or `001`, AI Cleanup has nothing to work with. Use the [Regenerate Titles](../workflows/regenerate-titles.md) workflow first to transcribe real titles from the audio, then run AI Cleanup as a second pass. See [Create titles from audio files](create-titles-from-audio-files.md).

## Related

- [AI Cleanup](../editor/ai-cleanup.md)
- [Apply Titles](../editor/apply-titles.md)
- [Regenerate Titles workflow](../workflows/regenerate-titles.md)
- [Set up LLM Providers](../getting-started/setup-llm-providers.md)
