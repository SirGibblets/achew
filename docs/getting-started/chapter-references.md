<style>
    .muted-section {
        color: var(--md-default-fg-color--light);
        font-size: 0.9em;
        margin-top: -0.5rem;
    }
    .muted-section.top-margin {
        margin-top: 0rem;
    }
</style>

# References

Achew designates sets of external chapter data as **References**. There are two kinds:

- **Chapter References**: These have timestamps *and* titles. They drive the Realign, Regenerate Titles, and Quick Edit workflows, and serve as points of comparison during initial chapter selection in the Smart Detect workflow. Chapter References can also be used anywhere a Title Reference is accepted.
- **Title References**: These only have titles, no timestamps. They can be used with [AI Cleanup](../editor/ai-cleanup.md) and the [Apply Titles](../editor/apply-titles.md) feature. They cannot be used for chapter alignment.

References stay loaded for the duration of your session. They appear as options during workflow selection and as tabs in the editor's [Add Chapter Dialog](../editor/add-chapter-dialog.md).

## Chapter References

### :simple-audiobookshelf: Audiobookshelf
The chapters currently set on the book in Audiobookshelf.

<div class="muted-section" markdown>
Auto-added if available.
</div>

### :material-tag-multiple: Embedded Chapters
Chapter markers stored inside the audio file's metadata.

<div class="muted-section" markdown>
Auto-added if available.
</div>

### :material-folder-music: File Data
Chapter data using the audio file names and durations.

<div class="muted-section" markdown>
Auto-added for multi-file books.
</div>

### :simple-audible: Audnexus

Chapter data from [Audnexus](https://audnex.us){:target="_blank"}, the same service Audiobookshelf uses for its own chapter lookups. 

<div class="muted-section" markdown>
Auto-added if the book is assigned an [ASIN](https://en.wikipedia.org/wiki/Amazon_Standard_Identification_Number){:target="_blank"} in Audiobookshelf.
<br>
Can also be searched/added via the **Add Chapter Reference** dialog.
</div>

### :material-code-json: JSON File
A `.json` file containing an array of objects with timestamp[^1] and title fields. Achew tries to auto-detect the fields, but predictable names like `start` / `timestamp` and `name` / `title` help:

```json
[
    {
        "timestamp": 0,
        "title": "Opening Credits"
    },
    {
        "timestamp": 18.453,
        "title": "Chapter 1: The Beginning"
    }
]
```

<div class="muted-section top-margin" markdown>
Auto-added from **Library Files**[^2] named `chapters.json`.
<br>
Can also be uploaded via the **Add Chapter Reference** dialog.
</div>

### :material-file-delimited: CSV File
A `.csv` file with columns for timestamps[^1] and titles. Achew tries to detect the columns (even without headers), but predictable column names like `start` / `timestamp` and `name` / `title` help.

<div class="muted-section" markdown>
Auto-added from **Library Files**[^2] named `chapters.csv`.
<br>
Can also be uploaded via the **Add Chapter Reference** dialog.
</div>

### :material-album: Cue Sheet
A standard cue sheet file (`.cue`).

<div class="muted-section" markdown>
Auto-added from **Library Files**[^2] named `*.cue`.
<br>
Can also be uploaded via the **Add Chapter Reference** dialog.
</div>

### :lucide-bookmark-plus: Snapshot
A snapshot of the chapters you've produced inside Achew, usable only during the current session.

<div class="muted-section" markdown>
Added using the **Create Snapshot** button on the [Review and Submit](../editor/review-submit-export.md#snapshot) screen.
</div>

## Title References

### :material-file-document-outline: Text File
A plain `.txt` file, one title per line. Blank lines are ignored. 

<div class="muted-section" markdown>
Auto-added from **Library Files**[^2] named `titles.txt`.
<br>
Can also be uploaded via the **Add Chapter Reference** dialog.
</div>

### :material-book-open-variant: EPUB File
An `.epub` e-book file. Chapter titles are extracted from its Table of Contents.

<div class="muted-section" markdown>
Auto-added from **Library Files**[^2] named `*.epub`.
<br>
Can also be uploaded via the **Add Chapter Reference** dialog.
</div>

### :material-playlist-edit: Custom Titles
You can edit a list of custom titles directly in Achew:

1. In the [Apply Titles](../editor/apply-titles.md) dialog or the [AI Cleanup](../editor/ai-cleanup.md) dialog, use the appropriate dropdown to select the **Custom Titles** Reference.
2. Click the **Pencil** icon next to the Reference to open the editor.
3. Type or paste your desired list of titles, one title per line. Blank lines are ignored.

<hr>
<br>

## Adding Chapter References

New References can be manually added using the **Add Chapter Reference** dialog. This dialog can be accessed from [Workflow Selection](./workflows-overview.md), the [Apply Titles](../editor/apply-titles.md) dialog, or the [AI Cleanup](../editor/ai-cleanup.md) dialog: 

![Add Chapter Reference button](../img/add-reference-button-light.webp#only-light)
![Add Chapter Reference button](../img/add-reference-button-dark.webp#only-dark)

Two tabs are available: **Upload File** and **Audnexus Search**.

### Upload File 

![Upload File tab](../img/add-reference-upload-light.webp#only-light){ width="480" }
![Upload File tab](../img/add-reference-upload-dark.webp#only-dark){ width="480" }

In the **Upload File** tab, drop a file into the upload zone or click **browse** to pick one. 

Supported Formats:

<div class="grid" markdown>

| Format | Extension | Reference type |
|--------|-----------|----------------|
| [JSON file](#json-file) | `.json` | Chapter Reference |
| [CSV file](#csv-file) | `.csv` | Chapter Reference |
| [Cue sheet](#cue-sheet) | `.cue` | Chapter Reference |
| [Text file](#text-file) | `.txt` | Title Reference |
| [EPUB file](#epub-file) | `.epub` | Title Reference |

<div markdown>
!!! tip
    Although Title References (`.txt` or `.epub`) cannot be used to start a workflow, you are allowed to upload them from the workflow selection screen; you'll be able to use them later when [Applying Titles](../editor/apply-titles.md) or running [AI Cleanup](../editor/ai-cleanup.md).
</div>

</div>

### Audnexus Search

??? info "What is Audnexus?"
    Audnexus is a service that provides aggregate metadata for audiobooks. This data is sourced primarily from the various Audible regions, and as such its chapter data is usually specific to books sourced directly from Audible. **If your book was sourced from elsewhere, the titles from Audnexus might be helpful, but the timestamps will likely be incorrect.**

In the **Audnexus Search** tab, you can search the [Audnexus](https://audnex.us){:target="_blank"} database by book title and/or author. Changing the **provider** allows you to change which Audible storefront region is searched.

![Audnexus Search tab](../img/add-reference-search-light.webp#only-light){ width="480"; .center}
![Audnexus Search tab](../img/add-reference-search-dark.webp#only-dark){ width="480"; .center}

Each result displays relevant information that can help you decide on a good match. Use the **Eye** button in the top right of each result to preview its chapter list, and click the **Add** button to add it as a Chapter Reference.

!!! tip
    If the book has an ASIN set in Audiobookshelf, Achew attempts to auto-add the Audnexus Reference at load time. Use this dialog to add new References using a different region, or to search by title when no ASIN is set.

[^1]:
    Timestamps in JSON and CSV files can be in any of these formats:

    * `H:MM:SS` or `H:MM:SS.ms`, e.g. `1:02:34` or `1:02:34.500`
    * `M:SS` or `M:SS.ms`, e.g. `62:34` or `62:34.500`
    * A plain number in seconds, e.g. `3754` or `3754.5`
    * A plain number in milliseconds, e.g. `3754000`

[^2]:
    "Library Files" refers to files stored alongside the audiobook, in the same directory. You can see them in the **Library Files** section of the book's detail page in Audiobookshelf.
