# Apply Titles from Source

Using the **Apply Titles** dialog, you can take titles from a [source](../getting-started/chapter-sources.md) and apply them to the chapters in the editor. To access the dialog, open the [Action Bar Menu](overview.md#action-bar-menu) and click **Apply titles from…**

## Picking a source

The dropdown at the top of the dialog lists all loaded sources and their chapter/title counts. Full chapter sources are listed first, followed by title-only sources.

![Pick Source](../img/apply-titles-pick-source-dark.webp#only-dark){ width="640"; .center }
![Pick Source](../img/apply-titles-pick-source-light.webp#only-light){ width="640"; .center }

Two buttons sit next to the dropdown:

- :lucide-eye:{ .icon-token } **Preview:** Preview the chapters/titles of the selected source. For the *Custom Titles* source it switches to an :lucide-pencil:{ .icon-token } **Edit** button that allows you to edit the title list.
- :lucide-plus:{ .icon-token } **Add Source:** Opens the [Add Chapter Source](../getting-started/chapter-sources.md#adding-chapter-sources) dialog so you can upload new sources or search Audnexus. New sources are automatically selected when added.

## Modes

When the selected source has timestamps (a full chapter source), a mode toggle appears with two choices: **By Alignment** and **By Selection**. Title-only sources have no timestamps and thus cannot be used with the By Alignment mode.

### By Alignment

Automatically matches chapters based on timestamp alignment.

![By Alignment](../img/apply-titles-alignment-dark.webp#only-dark){ width="640"; .center }
![By Alignment](../img/apply-titles-alignment-light.webp#only-light){ width="640"; .center }

Aligned chapters show the new title (from the source chapter), with the old title struck through. You can deselect the chapters you don't want to affect. Chapters with no match are greyed out and cannot be selected. Use the :lucide-play:{ .icon-token .primary } play button to preview audio and confirm accuracy.

### By Selection

Pairs chapters to source titles **positionally**: the 1st selected chapter on the left receives the 1st selected title on the right, the 2nd selected chapter receives the 2nd selected title, and so on. 

![By Selection](../img/apply-titles-selection-dark.webp#only-dark){ width="640"; .center }
![By Selection](../img/apply-titles-selection-light.webp#only-light){ width="640"; .center }

The two columns scroll in sync, and curved connectors visually link the pairs as you scroll. Uncheck chapters on the left or titles on the right to skip them and shift the remaining pairs. Use the :lucide-play:{ .icon-token .primary } play button to preview audio and confirm accuracy.

## Related

- [Chapter Sources](../getting-started/chapter-sources.md)
- [AI Cleanup](ai-cleanup.md)
- [Undo and Redo](undo-redo.md)
