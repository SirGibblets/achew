# Adding Chapters

In the editor, use the :lucide-plus:{ .icon-token } button between rows to insert a new chapter. 

![Add Chapter Button](../img/add-chapter-button-light.webp#only-light)
![Add Chapter Button](../img/add-chapter-button-dark.webp#only-dark)

This opens the **Add Chapter Dialog** which has several options for adding new chapters, depending on what data and which [References](../getting-started/chapter-references.md) are available. Only candidates that fall between the surrounding chapters are shown; this time range is displayed in the bottom left corner of the dialog.

## Chapter Options

### Timestamp

![At timestamp](../img/add-chapter-timestamp-light.webp#only-light){ width="480" }
![At timestamp](../img/add-chapter-timestamp-dark.webp#only-dark){ width="480" }

Manually specify a timestamp. Use <kbd>↑</kbd>/<kbd>↓</kbd> to nudge by ±1 second, and <kbd>Space</kbd> to preview.

### Detected Cues

![From Cue](../img/add-chapter-cue-light.webp#only-light){ width="480" }
![From Cue](../img/add-chapter-cue-dark.webp#only-dark){ width="480" }

Choose from cues that have been detected in the available time range. Click :lucide-play:{ .icon-token .primary } to preview.

![Empty cue list](../img/add-chapter-cue-empty-dark.webp#only-dark){ width="480" }
![Empty cue list](../img/add-chapter-cue-empty-light.webp#only-light){ width="480" }

If the region has not been fully scanned for cues yet, you can click on the :lucide-scan-search:{ .icon-token .primary } **Detect Cues** button or the :lucide-audio-lines:{ .icon-token .primary } **Detect Cues \[Dramatized\]** button to initiate a partial scan.


### Chapter References

![From Reference](../img/add-chapter-from-reference-light.webp#only-light){ width="480" }
![From Reference](../img/add-chapter-from-reference-dark.webp#only-dark){ width="480" }

One tab per [Chapter Reference](../getting-started/chapter-references.md#chapter-references). Click :lucide-play:{ .icon-token .primary } to preview.

### Deleted

![From Deleted](../img/add-chapter-deleted-light.webp#only-light){ width="480" }
![From Deleted](../img/add-chapter-deleted-dark.webp#only-dark){ width="480" }

Shows all previously-deleted chapters in the time range. Click :lucide-play:{ .icon-token .primary } to preview.

## Transcript Previews

The Detected Cues, Chapter Reference, and Deleted tabs have a **Transcript** column that shows what is spoken at each candidate, so you can tell which one is the real chapter start without previewing each one.

Click :lucide-mic:{ .icon-token } next to an item to transcribe it. Items are transcribed one at a time; clicking a queued item (:lucide-clock:{ .icon-token }) moves it to the front of the queue. Snippets that contain no speech show `<no speech>`, and long transcripts are shortened to fit (hover to see the full text).

Check **Auto** in the column header to automatically transcribe the items currently in view, top to bottom in the current sort order. As you scroll, newly visible items are transcribed and items scrolled out of view are dropped from the queue. Unchecking it stops queueing new items, and achew remembers your choice. If you have never set it, Auto turns itself on once a transcription model is already loaded (for example, after you have transcribed something earlier in the session), so opening the dialog never starts a model download on its own.

Each snippet is as long as your **Transcription Length** [setting](../reference/transcription.md#configuring-transcription) (or shorter, if the next chapter starts sooner). Transcripts are kept for the rest of the session, until you start a new session or change your transcription settings, and items less than half a second apart share a transcript. If you close the dialog while an item is being transcribed, that item still finishes and its transcript is kept; anything still queued is dropped.

## Add and Transcribe

When a chapter is selected (or a valid timestamp is entered), clicking the **Add chapter at** button will add the new chapter to the editor.

If you instead click the :lucide-mic:{ .icon-token .primary } **transcribe** icon in that button, the new chapter will be added and then immediately transcribed using the current [transcription settings](../reference/transcription.md#configuring-transcription). If the selected item already shows a [transcript preview](#transcript-previews), that transcript is used instead of transcribing again.