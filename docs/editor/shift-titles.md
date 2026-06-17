# Shift Titles

The **Shift Titles** dialog moves chapter titles forward or backward across your chapters in bulk, without changing any timestamps. It is useful when titles are misaligned by a consistent number of chapters, for example, when a missing or extra chapter has pushed every title one position out of place. To access the dialog, open the [Action Bar Menu](overview.md#action-bar-menu) and click **Shift Titles**.

![Shift Titles Dialog](../img/shift-titles-dialog-dark.webp#only-dark){ width="512"; .center }
![Shift Titles Dialog](../img/shift-titles-dialog-light.webp#only-light){ width="512"; .center }

## Shift by

The number of chapters to move each title. Positive values move titles to later chapters, negative values move them to earlier chapters.

Adjust the value with the :lucide-minus:{ .icon-token } / :lucide-plus:{ .icon-token } buttons, the <kbd>↓</kbd> / <kbd>↑</kbd> arrow keys, or by typing directly.

## Choosing chapters

The list shows every chapter, each with a checkbox. Only the checked chapters will be affected by the shift. <kbd>Shift</kbd>-click a checkbox to toggle every chapter in the range between it and your last click. Use the :lucide-play:{ .icon-token .primary } play button to preview a chapter's audio.

For each affected chapter, the list shows the original title alongside the new title it will receive.

## How shifting works

Titles move only among the checked chapters. Titles pushed past the beginning or end of the checked set will be discarded, and any chapters without an incoming title will become blank.

For example, shifting four checked chapters by `+1`:

| Chapter | Before | After |
|---|---|---|
| 1 | Intro | *(blank)* |
| 2 | Chapter 1 | Intro |
| 3 | Chapter 2 | Chapter 1 |
| 4 | Chapter 3 | Chapter 2 |

Here, the title "Chapter 3" is pushed off the end and discarded, and chapter 1 is left with no title. A negative shift behaves the same way in the opposite direction.

When ready, click **Apply** to perform the shift. Like any editor action, it is recoverable via [Undo](undo-redo.md).

## Related

- [Apply Titles](apply-titles.md)
- [Shift Timestamps](shift-timestamps.md)
- [Undo and Redo](undo-redo.md)
