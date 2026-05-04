# Adding Chapters

In the editor, use the :lucide-plus:{ .icon-token } button between rows to insert a new chapter. 

![Add Chapter Button](../img/add-chapter-button-light.webp#only-light)
![Add Chapter Button](../img/add-chapter-button-dark.webp#only-dark)

This opens the **Add Chapter Dialog** which has several options for adding new chapters, depending on what data and which [sources](../getting-started/chapter-sources.md) are available. Only candidates that fall between the surrounding chapters are shown; this time range is displayed in the bottom left corner of the dialog.

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


### Chapter Sources

![From Source](../img/add-chapter-from-source-light.webp#only-light){ width="480" }
![From Source](../img/add-chapter-from-source-dark.webp#only-dark){ width="480" }

One tab per [full chapter source](../getting-started/chapter-sources.md#full-chapter-sources). Click :lucide-play:{ .icon-token .primary } to preview.

### Deleted

![From Deleted](../img/add-chapter-deleted-light.webp#only-light){ width="480" }
![From Deleted](../img/add-chapter-deleted-dark.webp#only-dark){ width="480" }

Shows all previously-deleted chapters in the time range. Click :lucide-play:{ .icon-token .primary } to preview.

## Add and Transcribe

When a chapter is selected (or a valid timestamp is entered), clicking the **Add chapter at** button will add the new chapter to the editor.

If you instead click the :lucide-mic:{ .icon-token .primary } **transcribe** icon in that button, the new chapter will be added and then immediately transcribed using the current [transcription settings](../reference/transcription.md#configuring-transcription).