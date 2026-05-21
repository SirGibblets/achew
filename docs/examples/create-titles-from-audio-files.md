# Create titles from audio files

Follow these steps for a multi-file audiobook with one chapter per file and generic titles like `Track 01`, `Track 02`, etc. Achew's auto-added **File Data** Reference already has correct timestamps from the file durations; this workflow transcribes real titles from the audio and optionally splits the publisher intro and end credits into their own chapters.

## Run Regenerate Titles

1. Select the book.
2. Choose **Regenerate Titles** on the *Select a Workflow* screen.
3. Pick the **File Data** Reference.
4. Click **Continue with...**
5. On the *Transcribe Titles* screen, pick your [transcription settings](../reference/transcription.md) and click **Transcribe**. Achew transcribes the first few seconds of each file into a title.

## Add a separate opening credits chapter

Many multi-file books bundle the publisher intro or opening credits with the first chapter's narration in the first file. To split them:

1. Click the :lucide-plus:{ .icon-token } **Add** button below the first chapter row (it adds a chapter *after* that row, inside the same file's range).
2. In the [Add Chapter Dialog](../editor/add-chapter-dialog.md), switch to the **Detected Cues** tab.
3. Click :lucide-scan-search:{ .icon-token .primary } **Detect Cues** to scan the time range between the first and second chapters. Use :lucide-audio-lines:{ .icon-token .primary } **Detect Cues \[Dramatized\]** instead for books with music or sound effects.
4. Sort by **Gap size** to surface the most likely candidate. The silence between credits and narrative is usually pronounced.
5. Click :lucide-play:{ .icon-token .primary } to preview, then click the :lucide-mic:{ .icon-token .primary } transcribe icon on the **Add chapter** button to add and transcribe in one step.

The new chapter is now the actual start of the narrative. The first chapter (timestamp `0`) becomes the opening credits.

## Add a separate end credits chapter

Use the same technique on the last chapter row to split out end credits, acknowledgements, or excerpts of other books:

1. Click the :lucide-plus:{ .icon-token } **Add** button below the last chapter row. Then use the **Detected Cues** tab in the dialog to scan the end of the book.
2. Sort by **Gap size** and use :lucide-play:{ .icon-token .primary } to find the cue that marks the start of the credits, then click the :lucide-mic:{ .icon-token .primary } transcribe icon on the **Add chapter** button to add and transcribe in one step.

## AI Cleanup pass

Run [AI Cleanup](../editor/ai-cleanup.md) with **Infer opening credits/intro** and **Infer end credits/outro** enabled so the new boundary chapters get sensible titles like *Opening Credits* and *End Credits* alongside the cleaned-up narrative chapter titles.

## Submit or export

Click **Review Selected**, then [submit to Audiobookshelf or export](../editor/review-submit-export.md).

## Scenario: Existing titles are usable but inconsistent

If the file names already carry usable titles (just inconsistently formatted), skip Regenerate Titles. Use the [Quick Edit](../workflows/quick-edit.md) workflow with **File Data** instead, then run [AI Cleanup](../editor/ai-cleanup.md) to tidy up. Skipping the transcription step is faster, especially on long books. See [Improve titles with AI Cleanup](improve-titles-with-ai-cleanup.md).

## Related

- [Regenerate Titles workflow](../workflows/regenerate-titles.md)
- [Chapter References](../getting-started/chapter-references.md)
- [Add Chapter Dialog](../editor/add-chapter-dialog.md)
- [AI Cleanup](../editor/ai-cleanup.md)
