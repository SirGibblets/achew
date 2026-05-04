# Audit your library with Chapter Search

Use this when you want to find all books in a library that have bad, missing, or generic chapter data, so you can process them with Achew one by one.

## Open Chapter Search

1. From Achew's main book search screen, switch to the [Chapter Search](../getting-started/finding-a-book.md#chapter-search) tab.
2. Select the library you want to audit from the library dropdown.

## Define your rules

The first time you use Chapter Search, Achew populates the rule list with a default set of rules:

- **Book has a low chapter count:** Matches any book with 3 chapters or fewer.
- **Most chapters contain only numbers:** Matches any book where the title of most of its chapters is just a number.
- **Most chapters contain the book title:** Matches any book where the title of most of its chapters contains text that is similar to the book's title.
- **First chapter is not an intro:** Disabled by default. A ruleset containing the following rules:
     - **First chapter doesn't include 'intro' or 'credit':** Matches any book where the first chapter does not contain the text "intro" or "credit"
     - **First chapter includes 'chapter':** Matches any book where the first chapter contains the text "chapter"


These default rules are a good starting place for auditing your library, but you may wish to further customize by creating your own rules.

### Creating a rule

Let's say you want to find books that have chapter numbers, but are missing descriptive titles. In other words, you want to find titles like "Chapter 1" but *not* "Chapter 1: The Beginning"

Click **Add Rule** in the rule editor. 

- **Target:** `Most every chapter`
- **First condition:**
     - `starts with`
     - `the text`
     - `chapter` (leave "ignore case" checked)
- **Second condition:**
     - `ends with`
     - `a number`

This matches books where the title of most chapters resembles "Chapter 1", "chapter 004", etc.

You can add more rules or rulesets to cover other patterns. Enable or disable individual rules with the checkbox next to each one. Only enabled rules affect the search.

## Run the search

Click **Search**. Achew scans the library and returns all books where at least one rule matched.

## Work through the results

The left panel of the results page lists every matched book. Click one to see its chapter list and which rules caused it to be matched.

For each book you want to fix:

1. Click **Start** to open it in Achew.
2. Choose the appropriate workflow:
     - [Smart Detect](../workflows/smart-detect.md): if the book has no real chapter data at all.
     - [Regenerate Titles](../workflows/regenerate-titles.md): if timestamps are correct but titles are generic.
     - [Realign Chapters](../workflows/realign-chapters.md): if Audnexus has the right titles but timing is off.
     - [Quick Edit](../workflows/quick-edit.md): for small manual fixes.
3. Process and submit. Achew returns you to the book search screen.
4. Switch back to Chapter Search and continue with the next book.

## Ignoring books

Click **Ignore** in the right panel for any books you don't intend to change. The book will be hidden from future search results. Reveal ignored books again with the **Show ignored books** toggle.


## Related

- [Finding a Book](../getting-started/finding-a-book.md)
- [Choosing a Workflow](../getting-started/workflows-overview.md)
