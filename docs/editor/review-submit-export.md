# Review and Submit

Once you are happy with your chapters in the editor, click the **Review Selected** button to proceed to the Review screen. Here you can review the final chapter list, submit the chapters back to Audiobookshelf, or export chapters to a file.

![Review and submit](../img/review-and-submit-light.webp#only-light)
![Review and submit](../img/review-and-submit-dark.webp#only-dark)

## Submit to Audiobookshelf

Writes the chapters for this book back to your Audiobookshelf server, replacing whatever was there before. All chapters must have non-empty titles. If any are blank, submission will be disabled.

After submission, you'll return to the main screen where you can find another book to process.

## Export

Below the submit button, you can expand the **Export** section to view your export options.

!!! info "Exporting without submitting"
    Exporting does not end your current session. If you don't plan on submitting to Audiobookshelf, open the [Back Menu](../reference/glossary.md#back-menu) and pick **New Audiobook** to end the session and return to book selection.

### CSV

Columns: chapter number, timestamp (formatted `HH:MM:SS`), timestamp (raw seconds), title.

```csv
Chapter,Timestamp,Timestamp_Seconds,Title
1,00:00:00,0.000,Opening Credits
2,00:00:42,42.500,Chapter 1
```

### JSON

Structure:

```json
{
  "export_timestamp": "2026-04-16T12:34:56",
  "total_chapters": 23,
  "chapters": [
    { "chapter": 1, "timestamp": 0.0, "title": "Opening Credits" },
    { "chapter": 2, "timestamp": 42.5, "title": "Chapter 1" }
  ]
}
```

### CUE

Standard CUE sheet format, using `MM:SS:FF` (75 frames/sec).
