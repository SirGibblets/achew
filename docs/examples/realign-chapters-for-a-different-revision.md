# Realign chapters for a different revision

Follow these steps when an existing source has the right chapter **titles** but the **timestamps** don't match your audio file. This is most often the case with a different *revision* of the same recording (ads stripped, an Audible-branded intro/outro removed, a later revision with minor editing fixes) where the durations differ by only a few minutes.

!!! info "Realign vs. different editions"

    Realign works well across revisions of the same recording. It may produce mixed or unusable results from a fundamentally different *edition* (re-recorded narration, abridged content, rearranged chapters, or substantively different pacing). If you spot-check the realigned chapters and most of them are clearly wrong, the source likely doesn't match the version of the book you have. Try a different source, or use [Smart Detect](../workflows/smart-detect.md) followed by [Apply Titles](../editor/apply-titles.md) or [AI Cleanup](../editor/ai-cleanup.md) instead.

## Run Realign Chapters

1. Select the book.
2. Choose **Realign Chapters** on the *Select a Workflow* screen.
3. Pick the source with the good titles (typically Audnexus). If it isn't already loaded, click **Add Chapter Source** to add it.
4. Leave **Dramatized** off unless the book has music or sound effects.
5. Click **Realign**. Achew runs targeted detection around each source chapter and shifts the timestamps to the best-fitting cue.

## Review the Offset column

You'll land in the editor with an additional **Offset** column showing how far each chapter moved during realignment. For a same-recording revision, most chapters should show a small, broadly consistent offset, potentially drifting a bit over time.

Watch for the :lucide-triangle-alert:{ .icon-token .warning } warning icon. It marks low-confidence guesses where Achew couldn't find a clear cue near the expected position. Give those a closer listen to verify their accuracy, and adjust the timestamp if needed.

## Spot-check and fix outliers

1. Use the :lucide-play:{ .icon-token .primary } play button on the first and last few chapters to confirm they begin where you expect.
2. For any chapter that sounds off, click its timestamp to edit directly. <kbd>Space</kbd> toggles playback, <kbd>↑</kbd> / <kbd>↓</kbd> nudge by ±1 second.
3. For a more thorough fix, use the :lucide-plus:{ .icon-token } **Add** button to open the [Add Chapter Dialog](../editor/add-chapter-dialog.md), switch to the **Detected Cues** tab, and run **Detect Cues** on the surrounding region to surface alternative candidate timestamps.

## Submit or export

Click **Review Selected**, then [submit to Audiobookshelf or export](../editor/review-submit-export.md).

## Related

- [Realign Chapters workflow](../workflows/realign-chapters.md)
- [Chapter Sources](../getting-started/chapter-sources.md)
- [Shift Timestamps](../editor/shift-timestamps.md)
- [Add Chapter Dialog](../editor/add-chapter-dialog.md)
