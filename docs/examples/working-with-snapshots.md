# Working with snapshots

[Snapshots](../getting-started/chapter-references.md#snapshot) save the chapter list as a new [Chapter Reference](../getting-started/chapter-references.md) in your current session. They unlock a few patterns that aren't possible with the editor alone, mostly when you need to revert to a [previous step](../reference/glossary.md#back-menu) but don't want to lose your progress.

This page gives a few examples of real problems that can be addressed using snapshots.

## Realign + Regenerate Titles on a long book

**Problem.** You ran [Realign](../workflows/realign-chapters.md) against a Chapter Reference that has generic titles. Timestamps are now correct but the generic titles (`Chapter 1`, `Chapter 2`, …) need to be re-transcribed.

You *could* just click **Transcribe** in the editor, and that's fine for a short book. But for books with many chapters, the [Regenerate](../workflows/regenerate-titles.md) workflow can be meaningfully faster for transcription.

**Steps:**

1. Start with your realigned chapters in the editor.
2. Click **Review Selected** → **Export** → **Create Snapshot**.
3. Use the [Back Menu](../reference/glossary.md#back-menu) to return to **Select a Workflow**.
4. Choose **Regenerate Titles** and pick the **Snapshot** Reference.
5. Configure transcription and run.

The chapter list resets when you go back, but the **Snapshot** Reference survives the reset. After transcription you'll be back in the editor with transcribed titles at the realigned timestamps.

## Realign after Quick Edit without losing title edits

**Problem.** You used [Quick Edit](../workflows/quick-edit.md) to import chapters, then spent time fixing up titles in the editor. Now you realize the *timestamps* don't quite match your audio and you want to run [Realign](../workflows/realign-chapters.md) against them.

If you go back to **Select a Workflow** to start Realign from scratch, you lose all your title edits.

**Steps:**

1. Start with your edited chapter list in the editor.
2. Click **Review Selected** → **Export** → **Create Snapshot**.
3. Use the [Back Menu](../reference/glossary.md#back-menu) to return to **Select a Workflow**.
4. Choose **Realign Chapters** and pick the **Snapshot** Reference.

Realign now runs against your edited titles instead of the original Reference. You land back in the editor with the corrected timestamps and your title work intact.

## Redo Smart Detect without losing title edits

**Problem.** You ran [Smart Detect](../workflows/smart-detect.md) and made a bunch of title edits in the editor, but you've decided your initial selections were off. Maybe you chose too few cues, or should have used **Dramatized**. You want to redo detection or cue selection without throwing away your title work.

Going back to previous steps, like the [Initial Chapter Selection](../workflows/smart-detect.md#initial-chapter-selection) screen, wipes the chapter list.

**Steps:**

1. Click **Review Selected** → **Export** → **Create Snapshot**.
2. Use the [Back Menu](../reference/glossary.md#back-menu) to return to **Initial Chapter Selection** (or **Select a Workflow** if you want to switch detection modes).
3. Adjust the cue slider, **Dramatized** toggle, or whatever else needs changing, and proceed.
4. Once you're back in the editor with the new chapter list, open the [Apply Titles](../editor/apply-titles.md) dialog and pick the **Snapshot** Reference.
5. Apply the snapshot's titles to the chapters as necessary.

**Apply Titles** aligns the snapshot's titles to the new chapter timestamps, so your edits carry over wherever the new chapter list still lines up with the old.

## Related

- [Chapter References](../getting-started/chapter-references.md)
- [Review and Submit](../editor/review-submit-export.md)
- [Apply Titles](../editor/apply-titles.md)
- [Back Menu](../reference/glossary.md#back-menu)
