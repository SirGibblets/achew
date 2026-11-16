# Achew agent guide

Achew finds and fixes audiobook chapters (where each chapter starts, and its title) and saves
them to Audiobookshelf (ABS). This guide is for an agent driving Achew through its MCP tools.

## Ground rules

- **One session, shared with the web UI.** Only one book can be open at a time. The user may
  have Achew open in a browser: they see every change you make as it happens, and they may be
  editing too. Never discard their work: `open_book` refuses while another book is open, and
  `close_session` discards unsubmitted edits, so ask before closing a book you didn't open.
- **Follow `next`.** Every tool that reports the session returns its `step` and a `next` hint.
  A `ui_overlay` field means the user opened a settings page in the web UI; the session (and
  your work) carries on underneath it.
- **Stale descriptions.** Every tool description ends with `[achew rev …]`, the revision it
  was written for. If that differs from `get_status`'s `tools_revision`, the description you
  have is out of date (clients can cache tool schemas even across a reconnect): ask the user
  to reconnect, and meanwhile trust results over descriptions.
- **Long work runs in the background.** Downloading, detection, transcription and realignment
  take seconds to many minutes. Tools that start them wait up to `timeout_seconds`; when a
  result says `busy: true`, call `wait` (repeatedly) until it doesn't. An `error` field means
  the work failed and Achew went back to a safe step.
- **Verify, don't guess.** Check doubtful boundaries by listening (`transcribe_audio`) and by
  looking at nearby silences (`get_nearby_cues`) before moving chapters.
- **Batch edits.** Put related changes in one `edit_chapters` call; the user can undo the whole
  batch with one Undo.
- **Ask before writing.** `submit_to_audiobookshelf` replaces the book's chapters in ABS. Call
  `preview_submission`, show the user the changes, and submit with `confirm=true` only once
  they agree. The user can turn off agent submits entirely; then Achew shows its Review screen
  and the user clicks Submit there.

## Concepts

- **Chapter reference:** a list of chapter starts with titles, e.g. the chapters ABS has now,
  chapters embedded in the audio files, or Audnexus (Audible's chapter data). References are
  the raw material for workflows; they aren't changed by editing.
- **Title reference:** titles without timestamps, e.g. an ebook's table of contents, or a
  plain list added with `add_reference_from_text` (format `txt`).
- **Cue:** a silence detected in the audio, with its length (`gap`). Chapter breaks are
  usually the longer silences, but long pauses happen mid-chapter too. A cue's time is where
  speech *resumes*: 1/3 s before the silence ends. The silence itself began at
  `silence_from`, before the cue's time.
- **Realignment:** moving a reference's chapters onto the cues that match them in this
  recording. Each realigned chapter has a `confidence`; `guess: true` means no strong cue
  confirmed it, so check those first (workflow results list their ids in `guess_ids`).
  **Pinned** chapters are confirmed (by the user, you, or transcription) and show no
  confidence: `realign_unpinned` keeps them and re-places the rest around them. Moving a
  realigned chapter pins it. `realign_search` says how wide a window around each reference
  chapter was scanned; if most chapters are guesses and the window was narrow, realigning with
  `thorough=true` scans more.
- **Scanned audio:** Achew only finds silences in audio it has scanned. Smart detect scans the
  whole book; realignment only the window around each reference chapter. The cue tools report
  `scanned`: no cues in unscanned audio means "not looked at", so `scan_for_cues` there.
- **Excluded** chapters stay in the editor but aren't written to ABS (`set_chapter_selection`).
- **Transcripts:** `list_chapters` marks every chapter whose start was transcribed with
  `transcript_matches` (true when the title was heard, allowing "Two" for "2"), and shows the
  transcript where it doesn't match. `title_is_transcript` means the title was made from the
  transcript (smart detect, regenerate) and not edited since. Neither means never transcribed.
  To check several starts at once, `transcribe_audio` with `chapter_ids` reports for each
  whether its title was heard (anywhere in the snippet, ignoring track numbers like "01 - ")
  and the silence before it (`lead_seconds` hears the end of the previous chapter too). Every
  snippet reports the chapter heading it `announces`, so "Chapter 5 of Oliver Twist. This
  LibriVox recording..." gives you "Chapter 5" without the boilerplate. Short clips transcribe
  badly (a few seconds can come back as "[Music]" or a stray syllable): keep the default
  window of 15 s or more unless the chapter is shorter.
- **Files:** in books made of several audio files, `list_chapters` marks whether each chapter
  starts on a file (`on_file_start`); in LibriVox and similar recordings each file is usually
  one chapter, so one that doesn't sit on a file start deserves a listen.
- **Beyond the audio:** a reference from a longer copy of the book (for example one with credits
  this copy lacks) can leave its last chapters starting after this recording ends. They're marked
  `beyond_audio`, results carry a warning, and submitting refuses them: delete them, and check the
  last chapter that does have audio.

## Choosing a workflow

Open the book, then look at the references `open_book` returns (`get_references` lists one in
full). Compare each chapter reference's `duration_difference` (seconds longer or shorter than
this recording) and its titles.

| Situation | Workflow |
|-----------|----------|
| A reference has good titles but the times are off (common when ABS chapters came from a different edition, or there are none but Audnexus has some) | `realign` with that reference |
| The times are right but titles are generic ("Chapter 1", "Track 03", the book title) | `regenerate` (retitles by transcription), or `quick_edit` and rename them yourself from a title reference |
| A reference is already right apart from small fixes | `quick_edit` |
| No usable reference at all | `smart_detect` |

If no reference has good titles, try `find_audnexus_chapters`: a candidate whose
`duration_difference` is within a few seconds is almost certainly the same edition, and is the
best reference to `add_audnexus_reference` and realign. A difference of a minute or more
usually means a different edition (different intro/outro credits, or a different narrator),
which realignment can still handle.

For full-cast or heavily scored productions use `detection_mode: "dramatized"`, or leave
`auto` to let Achew decide.

## Walkthroughs

### Realign to Audnexus

1. `open_book(item_id)`; read the references.
2. If there's no good Audnexus reference: `find_audnexus_chapters`, then
   `add_audnexus_reference(asin)`.
3. `start_workflow("realign", reference_id=...)`. Add `transcribe: true` to have Achew verify
   chapter starts by listening (slower, more accurate; needs a transcription service); it
   stops at `configure_asr`, where `configure_transcription("transcribe")` starts it.
4. In `chapter_editing`: `list_chapters`. Check chapters with low confidence or `guess: true`:
   `transcribe_audio` at the chapter's start (and a few seconds before it) should hear the
   title, or the end of the previous chapter just before it. `get_nearby_cues` shows where else
   the start could go. Each snippet lists the `pauses` inside it: speech after a long pause can
   be missing from the transcript, so listen again from after the pause before deciding a
   passage is silent or a hallucination.
5. Fix wrong starts with `edit_chapters` (`move`), then `realign_unpinned` to let the fix carry
   to the chapters after it. Check again. A move clears the transcript heard at the old start,
   so listen at the new one before trusting its title.
6. `preview_submission`, show the user, `submit_to_audiobookshelf(confirm=true)`.

### Detect from scratch (smart_detect)

1. `start_workflow("smart_detect")`. It ends at `initial_chapter_selection`.
2. `get_detected_cues`. Use `cues_at_least` (how many cues have each gap length),
   `thresholds` (the `min_gap_seconds` that gives N chapters) and `natural_breaks` (where gap
   lengths drop sharply) together with any reference chapter counts or a table of contents
   to pick a threshold. `transcribe_audio` at a few candidate cues tells you whether they're
   real chapter starts. Real breaks can be short (a section break of 1.5 s under a heading):
   list a stretch with `from_time`/`to_time` and a low `min_gap_seconds` to find them.
3. `select_cues(min_gap_seconds=...)`, adding specific `timestamps` and leaving out
   mid-chapter pauses with `exclude_timestamps`.
4. `configure_transcription("transcribe")` titles each chapter from its first few seconds
   (or pass `titles` you already know, e.g. from a table of contents).
5. In `chapter_editing`, clean up titles (below), delete false chapters, add missing ones,
   then preview and submit. Chapters marked `suspect` in `list_chapters` (for example a
   heading that runs for minutes) say where to look. Transcription titles only hear the first
   few seconds of each chapter: `transcribe_audio` at a short chapter's start hears all of it
   (epigraphs included).

### Fix titles only

Timestamps are right but titles are bad: `start_workflow("regenerate", reference_id=...)`,
then `configure_transcription("transcribe")`. Or `quick_edit` and write titles yourself from a
title reference (`add_reference_from_text` with the table of contents), using `edit_chapters`
renames.

### Split off opening and end credits

Many recordings (LibriVox especially) put credits or a preamble inside the first and last
chapters. To give them their own chapters:

1. `transcribe_audio` at the book's start and over its last minute (`seconds: 30`): the
   credits usually say so ("This is a LibriVox recording", "End of", "This has been").
2. Find where they end or begin: `get_detected_cues` with `from_time`/`to_time` around that
   stretch (in a realigned book, `scan_for_cues` first if `scanned` is under 100%), then listen
   just after a candidate cue.
3. One `edit_chapters` call: rename or `add` the `Opening Credits` / `End Credits` chapters and
   move the first real chapter to where the text begins.

Short pauses between credits and text can fall below what detection reports; place those by
listening.

### Audit a library

`find_books_needing_cleanup(library_id)` lists books matching the user's Chapter Search rules,
with sample titles and why each matched. Work through them one at a time (only one book can be
open): open, fix, preview, get approval, submit, `close_session`, next. Ask the user how much
to batch approvals; never submit without one.

## Titles

- Prefer the publisher's titles (Audnexus, an ebook table of contents) over transcription,
  which mishears names and numbers. Use transcripts to place chapters and to fix titles a
  reference lacks.
- Use number order to fix misheard numbers: between sections 1 and 3, "Too" or "To" is 2;
  between 8 and the next heading, "Knine" is 9. Names misheard in one chapter are usually
  misheard the same way in others; fix them consistently (check the book's description or
  a table of contents for spellings).
- For big rename batches, send them in one `edit_chapters` call; it answers with counts, and
  `list_chapters` shows the result.
- Be consistent within a book: one style for numbered chapters (e.g. `Chapter 1` or
  `Chapter 1: The Beginning`), not a mix.
- Keep front and back matter as their own chapters with plain names: `Opening Credits`,
  `Dedication`, `Prologue`, `Epilogue`, `Acknowledgments`, `End Credits`.
- Don't repeat the book title in every chapter, and drop track or disc numbering.
- `get_status` returns the user's own title preferences (the AI Cleanup custom instructions
  they enabled) as `title_preferences`; follow them. "none set" means choose a style yourself:
  match the book's existing chapters where they're consistent, and ask the user if unsure.
