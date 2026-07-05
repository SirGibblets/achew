# Edit Titles

The **Edit Titles** dialog is a set of manual tools for cleaning up chapter titles in bulk: Find & Replace, Change Case, Add/Remove Text, Sequence Numbering, Convert Numbers, and Tidy. Every tool shows a live preview of how titles will change before anything is applied, making it a fully manual alternative to [AI Cleanup](ai-cleanup.md). To access the dialog, open the [Action Bar Menu](overview.md#action-bar-menu) and click **Edit Titles**.

![Edit Titles Dialog](../img/edit-titles-light.webp#only-light){ width="480" .center}
![Edit Titles Dialog](../img/edit-titles-dark.webp#only-dark){ width="480" .center}

Pick a tool from the **Tool** dropdown at the top of the dialog. Your inputs for each tool are kept while the dialog is open, so you can freely switch tools without losing the current preferences.

## Choosing chapters

The bottom half of the dialog is a preview list showing every chapter, each with a checkbox. Only the checked chapters will be affected by the current tool. <kbd>Shift</kbd>-click a checkbox to toggle every chapter in the range between it and your last click. Use the :lucide-play:{ .icon-token .primary } play button to preview a chapter's audio.

For each affected chapter, the list shows the original title alongside the new title it will receive, and the header shows how many titles will change.

Clicking **Apply** commits the previewed changes but keeps the dialog open, so tools can be chained: for example Tidy, then Find & Replace, then Sequence Numbering. Each Apply is a single action in the [Undo](undo-redo.md) history.

## Tools

### Find & Replace

Replaces every occurrence of the search text within each title. Matching is case-insensitive unless **Match case** is enabled.

- **Regex** interprets the search text as a regular expression. Use `$1`, `$2`, … in the replacement to insert capture groups, `$&` for the whole match, and `$$` for a literal dollar sign. Invalid patterns show an error and disable the Apply button.
- **Preserve case** attempts to match the case of the text being replaced: replacing `chapter` with `part` turns `CHAPTER` into `PART`, `Chapter` into `Part`, and `chapter` into `part`.

### Change Case

Converts titles to **Title Case**, **Sentence case**, **UPPERCASE**, or **lowercase**.

Title Case keeps short words like *a*, *of*, *the* lowercase (except at the start or end of a title, or after a colon), and handles apostrophes correctly (*Don't Look Back*, *O'Brien's Return*). With **Keep Roman numerals uppercase** enabled, numerals stay intact: `CHAPTER XIV` becomes `Chapter XIV` rather than `Chapter Xiv`.

### Add or Remove Text

Adds text to the start or end of each title, or removes text from either end: either a matching prefix/suffix or a fixed number of characters.

### Sequence Numbering

Adds a sequence of numbers using a template. In the template, `{n}` becomes the sequence number and `{title}` the chapter's current title:

- `Chapter {n}` → *Chapter 1*, *Chapter 2*, …
- `{n}. {title}` → *1. Introduction*, *2. The Journey*, …

The filled template replaces each title by default, or can instead be added to the start or end of the existing title using the placement dropdown.

Numbering follows the **checked** chapters in list order, so you can uncheck a prologue or epilogue and still get a contiguous sequence. The starting number is configurable, and numbers can be formatted as digits (`1`), zero-padded digits (`01`, `001`), Roman numerals (`XIV` / `xiv`), or words (`Fourteen` / `fourteen`).

### Convert Numbers

Converts numbers found in titles (digits, Roman numerals, or spelled-out words like *Twenty-One*) to the chosen format: digits, Roman numerals, or words.

By default, only numbers acting as chapter markers are converted: numbers that follow a structural word (*Chapter*, *Part*, *Book*, *Volume*, *Section*, *Episode*, …), start the title (`1. Introduction`, `Five: What now?`, `One the Beginning`), or make up the entire title. Mid-title numbers (*Catch Twenty-Two*) are protected, along with leading numbers that are likely title words, such as *One of Us Is Lying*, *Twenty Thousand Leagues Under the Sea*, and *I Am Legend*. Uncheck the **Only chapter numbers** option to convert every number.

### Tidy

The configurable version of the [Quick Tidy](#quick-tidy) button. Each option can be toggled individually:

- **Fix whitespace:** Trims leading/trailing whitespace and removes duplicate whitespace.
- **Remove trailing punctuation:** Strips trailing periods, commas, colons, and dashes. `?`, `!`, and ellipses are kept, since they usually end a title intentionally.
- **Convert chapter numbers:** `Chapter Fourteen` / `Chapter XIV` → `Chapter 14`, in your choice of digits, Roman numerals, or words. Only numbers acting as chapter markers are touched, as described in [Convert Numbers](#convert-numbers).
- **Separator after chapter number:** `Chapter 14 The Sea Voyage` → `Chapter 14: The Sea Voyage`, using a colon, dash, period, or custom separator. An existing separator after the number is converted to your choice, so with the dash selected, `Chapter 2: The Next Step` becomes `Chapter 2 - The Next Step`. A number that starts the title is treated as a chapter number too (`3. Undaunted` → `3: Undaunted`), while continuation phrases like `Chapter 2 of Frankenstein` are left alone.
- **Change case:** Title Case, Sentence case, UPPERCASE, or lowercase, as described in [Change Case](#change-case), keeping Roman numerals uppercase.

Click **Save as Quick Tidy defaults** to persist the current configuration; the [Quick Tidy](#quick-tidy) button will use it from then on. The Tidy tool loads your saved configuration whenever the dialog opens.

## Quick Tidy

The **Quick Tidy** button in the [Action Bar Menu](overview.md#action-bar-menu) applies your saved [Tidy](#tidy) preferences to the currently selected chapters in a single click. With the default settings, it is the quickest way to clean up common transcription artifacts like ALL-CAPS titles and trailing periods:

> `  CHAPTER   FOURTEEN THE SEA VOYAGE.  ` → `Chapter 14: The Sea Voyage`

The settings button :lucide-settings:{ .icon-token } opens the [Tidy tool](#tidy) directly, where you can preview exactly what your configuration will do to the current titles, and change it.

The whole cleanup is a single action in the [Undo](undo-redo.md) history. If you want to review the changes first or apply only some of the fixes, use the Tidy tool in the Edit Titles dialog instead.

## Related

- [AI Cleanup](ai-cleanup.md)
- [Shift Titles](shift-titles.md)
- [Apply Titles](apply-titles.md)
