# Apply Titles from Reference

Using the **Apply Titles** dialog, you can take titles from a [Reference](../getting-started/chapter-references.md) and apply them to the chapters in the editor. To access the dialog, open the [Action Bar Menu](overview.md#action-bar-menu) and click **Apply titles from…**

## Picking a reference

The dropdown at the top of the dialog lists all loaded References and their chapter/title counts. Chapter References are listed first, followed by Title References.

![Pick Reference](../img/apply-titles-pick-reference-dark.webp#only-dark){ width="640"; .center }
![Pick Reference](../img/apply-titles-pick-reference-light.webp#only-light){ width="640"; .center }

Two buttons sit next to the dropdown:

- :lucide-eye:{ .icon-token } **Preview:** Preview the chapters/titles of the selected Reference. For the *Custom Titles* Reference it switches to an :lucide-pencil:{ .icon-token } **Edit** button that allows you to edit the title list.
- :lucide-plus:{ .icon-token } **Add Reference:** Opens the [Add Chapter Reference](../getting-started/chapter-references.md#adding-chapter-references) dialog so you can upload new References or search Audnexus. New References are automatically selected when added.

## Modes

A mode toggle below the dropdown offers three choices: **By Alignment**, **By Selection** and **By Similarity**. Title References have no timestamps and thus cannot be used with the By Alignment mode.

### By Alignment

Automatically matches chapters based on timestamp alignment.

![By Alignment](../img/apply-titles-alignment-dark.webp#only-dark){ width="640"; .center }
![By Alignment](../img/apply-titles-alignment-light.webp#only-light){ width="640"; .center }

Aligned chapters show the new title (from the Reference chapter) alongside the original title. You can deselect the chapters you don't want to affect. Chapters with no match are greyed out and cannot be selected. Use the :lucide-play:{ .icon-token .primary } play button to preview audio and confirm accuracy.

### By Selection

This mode pairs chapters to Reference titles based on **position**. The first selected chapter on the left receives the first selected title on the right, the second selected chapter receives the second selected title, and so on. 

![By Selection](../img/apply-titles-selection-dark.webp#only-dark){ width="640"; .center }
![By Selection](../img/apply-titles-selection-light.webp#only-light){ width="640"; .center }

The two columns scroll in sync, and curved connectors visually link the pairs as you scroll. Uncheck chapters on the left or titles on the right to skip them and shift the remaining pairs. Use the :lucide-play:{ .icon-token .primary } play button to preview audio and confirm accuracy.

### By Similarity

Automatically matches chapters to Reference titles based on what each chapter says. Each chapter's transcript (what is heard at its start) and its current title are compared with the Reference's titles, the same way [Enhance with transcription](../workflows/realign-chapters.md#enhancing-with-transcription) checks titles during realignment. Numbers are compared regardless of how they're written, so "Chapter XII", "Chapter Twelve" and "Chapter 12" all match, small transcription inaccuracies are tolerated, and a chapter that announces a different number never matches.

Titles are matched in order: each title goes to at most one chapter, and a chapter can't receive a title that comes before the previous chapter's. This tells repeated titles apart (such as the "Chapter 1" of each part) and keeps a chapter that only mentions a title in passing from taking it.

Each match shows a score. Strong matches start checked. Weaker ones, such as a one-word title that opens a longer sentence, start unchecked and show the title they would receive below the chapter's current title. Hover over a score to see whether the chapter's transcript or current title matched. Chapters with no match are greyed out and cannot be selected. Use the :lucide-play:{ .icon-token .primary } play button to preview audio and confirm accuracy.

This mode is useful when a Reference's timestamps don't line up with your chapters (for example, a different edition of the recording), or when extra or missing chapters would throw off the pairing in By Selection. It works best on chapters that have been transcribed, or whose current titles are short forms of the Reference's titles, such as "Chapter 4" for "Chapter 4: The Leaky Cauldron".

## Related

- [Chapter References](../getting-started/chapter-references.md)
- [Shift Titles](shift-titles.md)
- [AI Cleanup](ai-cleanup.md)
- [Undo and Redo](undo-redo.md)
