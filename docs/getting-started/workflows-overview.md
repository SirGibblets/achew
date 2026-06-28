# Choosing a Workflow

![Select Workflow screen](../img/select-workflow-light.webp#only-light)
![Select Workflow screen](../img/select-workflow-dark.webp#only-dark)

Achew asks you to pick a workflow after you select a book. The four options differ in how much of the chapter data is regenerated versus reused.

## Which workflow should I use?

1. **Do you have any partially accurate chapter data for this book?** (from ABS, Audnexus, embedded chapters, or another [Reference](chapter-references.md))

    - **No** → [Smart Detect](../workflows/smart-detect.md).
    - **Yes** → continue.

2. **Which part of the data is accurate?**

    - **Everything, I just want to tidy up or add a few missing chapters** → [Quick Edit](../workflows/quick-edit.md).
    - **Titles are fine, timestamps are slightly off** → [Realign Chapters](../workflows/realign-chapters.md).
    - **Timestamps are fine, titles are missing or wrong** → [Regenerate Titles](../workflows/regenerate-titles.md).
    - **Both are partially wrong** → Start with [Smart Detect](../workflows/smart-detect.md) and reconcile with other References later in the chapter editor.

## The four workflows at a glance

| Workflow | Detects cues? | Transcribes titles? | Requires existing [Reference](chapter-references.md)? | Example use case |
|---|---|---|---|---|
| [**Smart Detect**](../workflows/smart-detect.md) | Yes | Optional | No | Books with no chapters or completely wrong chapters |
| [**Realign Chapters**](../workflows/realign-chapters.md) | Partial | No | Yes | Timings are off by up to a few minutes |
| [**Regenerate Titles**](../workflows/regenerate-titles.md) | No | Yes | Yes | Chapters are only numbers or are missing titles |
| [**Quick Edit**](../workflows/quick-edit.md) | No | No | Yes | Quick manual tweaks or adding a couple missing chapters |

## "Dramatized" toggle

Smart Detect and Realign both offer a **Dramatized** toggle for audiobooks that contain music and/or sound effects, i.e. *dramatized* audiobooks. When enabled, Achew uses a slower voice-activity-based detection strategy that is significantly more accurate for non-speech audio.

## Existing Chapter Reference selection

Three of the four workflows (Realign, Regenerate, Quick Edit) require you to pick an existing Chapter Reference. Clicking on the chapter count for a Reference will display the full chapter information including timestamps and titles.

![View Reference chapters](../img/reference-view-chapters-light.webp#only-light){ width="480"; .center }
![View Reference chapters](../img/reference-view-chapters-dark.webp#only-dark){ width="480"; .center }

If the Reference you want is not shown, click the **Add Chapter Reference** button. This will open a dialog where you can upload JSON, CSV, CUE, TXT, or e-book files containing chapter data, or you can search for an Audnexus Reference by title and/or author. See [Chapter References](chapter-references.md).

## Changing your mind

You can back out of any workflow using the [Back Menu](../reference/glossary.md#back-menu) (the **Back** button at the top-left of the screen). It lists the earlier steps you can return to, plus a **New Audiobook** option that ends the current session and takes you back to book selection. Just be aware that any progress made after the chosen step will be lost.
