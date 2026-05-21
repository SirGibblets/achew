# Start from scratch with Smart Detect

Follow these steps when your book has no usable chapter data: No chapters in Audiobookshelf, no embedded chapters, and Audnexus has nothing for it. You'll build chapters from the audio itself.

## Run Smart Detect

1. Select the book.
2. Choose **Smart Detect** on the *Select a Workflow* screen.
3. Leave the **Dramatized** checkbox off unless the book has music or sound effects (dramatized detection is significantly slower).
4. Click **Start Smart Detect**. Achew analyzes the audio; this can take anywhere from a few seconds to several minutes depending on the book's length and your hardware.

## Tune the cue selection

When detection finishes, you'll land on the *Initial Chapter Selection* screen. With no comparison Reference available, rely on the timeline and histogram:

1. Drag the **Cue Selection Slider** to set how many cues become chapters. If you're not sure where to start, look for a clear *valley* in the histogram and place the slider just into the right slope of it. For example:

    ![Cue Valley Example](../img/cue-valley-large-dark.webp#only-dark)
    ![Cue Valley Example](../img/cue-valley-large-light.webp#only-light)

2. Glance at the **Timeline Visualization** above. Aim for a roughly even distribution of tick marks across the book's length.
3. If the prologue, foreword, or epilogue looks like it's being missed near the edges of the timeline, raise the **Intro/Outro Sensitivity** slider. Lower it if you'd rather exclude that material.

When in doubt, err on the side of **more cues**. Extras are easy to delete in the editor; missing chapters are harder to find.

Click **Create Chapters** when the timeline looks right.

## Transcribe titles

On the *Transcribe Titles* screen, pick your [transcription settings](../reference/transcription.md) and click **Transcribe**. Achew transcribes the first few seconds of audio at each chapter timestamp into a working title.

## Polish in the editor

1. Scan the chapter list. Use the :lucide-play:{ .icon-token .primary } play button to spot-check timestamps or titles that look odd.
2. Delete obvious false positives with the :lucide-trash-2:{ .icon-token .danger } delete button.
3. If a chapter is missing, follow [Fill in a few missing chapters](fill-missing-chapters.md) to insert it.
4. Run [AI Cleanup](../editor/ai-cleanup.md) to normalize the transcribed titles (capitalization, chapter numbering, intro/outro labels).

## Submit or export

Click **Review Selected**, then [submit to Audiobookshelf or export](../editor/review-submit-export.md).

## Scenario: A Reference exists, but is partly wrong

If you have a Chapter Reference whose timestamps are mostly accurate but you suspect Smart Detect can do better, make sure to add it from the Smart Detect screen *before* clicking **Start Smart Detect**. Then on the *Initial Chapter Selection* screen:

1. Toggle the Reference under **Compare to** in the timeline. Tick marks become color-coded by alignment quality, with the alignment percentage shown next to it.
2. Adjust the **Cue Selection Slider** to maximize alignment.
3. Optionally, enable the Reference under **Include unaligned chapters** to fold in any of its chapters that Smart Detect missed.

## Related

- [Smart Detect workflow](../workflows/smart-detect.md)
- [Add Chapter Dialog](../editor/add-chapter-dialog.md)
- [AI Cleanup](../editor/ai-cleanup.md)
- [Review and Submit](../editor/review-submit-export.md)
