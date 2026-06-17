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

When a Chapter Reference is selected, a mode toggle appears with two choices: **By Alignment** and **By Selection**. Title References have no timestamps and thus cannot be used with the By Alignment mode.

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

## Related

- [Chapter References](../getting-started/chapter-references.md)
- [Shift Titles](shift-titles.md)
- [AI Cleanup](ai-cleanup.md)
- [Undo and Redo](undo-redo.md)
