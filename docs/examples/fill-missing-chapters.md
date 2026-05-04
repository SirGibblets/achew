# Fill in a few missing chapters

Follow these steps if your book is missing a chapter or two, but is otherwise correct.

## Load the existing chapters

1. Select the book.
2. Choose **Quick Edit** on the Select Workflow screen.
3. Pick the relevant chapter source.
4. Click **Continue**. You'll land in the editor with those chapters loaded.

## Insert the missing chapter

1. Locate the chapters between which you expect to find a missing chapter.
2. Click the :lucide-plus:{ .icon-token } **Add** button between those chapters.
3. In the [Add Chapter Dialog](../editor/add-chapter-dialog.md), switch to the **Detected Cues** tab.
4. Click :lucide-scan-search:{ .icon-token .primary } **Detect Cues** (or :lucide-audio-lines:{ .icon-token .primary } **Detect Cues \[Dramatized\]** if the book has music or sound effects). Achew runs detection targeting that specific region.
5. When detection has finished, sort by **Gap size** to surface the most likely candidates first.
6. Click the play button on each candidate to preview the audio. Pick the right one and click **Add chapter**. You can also click the :lucide-mic:{ .icon-token .primary } transcription icon to add and transcribe at the same time.

Repeat for each missing chapter.

## Cleanup

- Edit titles manually, use the :lucide-mic:{ .icon-token } transcribe button, or run [AI Cleanup](../editor/ai-cleanup.md) to tidy up.
- Submit to Audiobookshelf or export.

## Scenario: The title is in another source

If one of your *other* chapter sources has the missing chapter, use the tab for that source in the Add Chapter Dialog instead of the Detect Cues tab. Pick the missing chapter there to insert both its timestamp and title in one click.

## Related

- [Add Chapter Dialog](../editor/add-chapter-dialog.md)
- [Quick Edit workflow](../workflows/quick-edit.md)
