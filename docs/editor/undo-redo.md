# Undo and Redo

Nothing in the editor is permanent until you click **Submit to Audiobookshelf**. Until then, nearly every change can be undone by using the :lucide-undo:{ .icon-token } **Undo** button in the editor's Action Bar. The :lucide-redo:{ .icon-token } **Redo** button can be used to revert undone changes as long as no new changes are made.

Note that **Undo** only applies to actions made within the editor. If you use the [Back Menu](../reference/glossary.md#back-menu) to return to a previous step and then re-enter the editor, the history will have reset.

## Keyboard Shortcuts

| Action | Windows / Linux | macOS |
|---|---|---|
 | :lucide-undo:{ .icon-token } Undo | <kbd>Ctrl</kbd>+<kbd>Z</kbd> | <kbd>⌘</kbd>+<kbd>Z</kbd> |
 | :lucide-redo:{ .icon-token } Redo | <kbd>Ctrl</kbd>+<kbd>Y</kbd> or <br> <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> | <kbd>⌘</kbd>+<kbd>Y</kbd> or <br> <kbd>⌘</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> |

## What's tracked

All of these actions in the editor can be undone:

- Title edits
- Timestamp edits
- Adding a chapter
- Deleting a chapter
- Transcribing titles
- Shift Timestamps
- Apply Titles from Source
- AI Cleanup

!!! tip "Restoring Deleted Chapters"
    In addition to using the :lucide-undo:{ .icon-token } **Undo** button, previously-deleted chapters can be restored by selecting them from the **Deleted** tab of the [Add Chapter Dialog](./add-chapter-dialog.md#deleted).
