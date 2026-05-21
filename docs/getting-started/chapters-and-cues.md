# Chapters vs Cues

## Chapter

A **chapter** is exactly what you might think: the combination of a title and a timestamp. Every row in the [Chapter Editor](../editor/overview.md) is a chapter. You save finished chapters back to Audiobookshelf. You can use chapters from [Chapter References](./chapter-references.md) to start workflows.

## Cue

A **cue** is a *candidate* chapter boundary produced by Achew's audio analysis. It's a detected gap in voice activity that *might* mark the start of a chapter. Cues are what Smart Detect finds in the audio. Sometimes referred to as **chapter cues**.

Cues have no title; they have a timestamp and an associated gap duration. Generally speaking, longer gaps are more likely to represent real chapters compared to shorter gaps. During the [Initial Chapter Selection](../workflows/smart-detect.md#initial-chapter-selection) step, you pick a gap threshold using the **Cue Selection Slider** to decide which cues become chapters. In the Chapter Editor, you can also turn cues into chapters by picking one from the **Detected Cues** tab when adding a new chapter.
