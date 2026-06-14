# Real realignment fixtures

Drop `*.json` files captured from the **Realignment Fixture** debug button
(ChapterReview page, dev/DEBUG mode only) into this directory. They are picked up
automatically by the regression test in `tests/realignment/test_chapter_aligner.py`, which
scores the aligner on every fixture and fails if any case regresses against the committed
baseline (`tests/realignment/realignment_baseline.json`).

Capture a fixture *after* correcting every timestamp you can in the editor, so
`ground_truth` is actually ground truth. Use the jump-to-cue feature to ensure corrected 
timestamps fall exactly on a detected cue where possible.

After adding fixtures, regenerate the baseline so they're included:

```bash
uv run pytest tests/realignment/test_chapter_aligner.py --update-aligner-baseline
```

Review the resulting `tests/realignment/realignment_baseline.json` diff before committing.
The schema is documented in the module docstring of
`tests/realignment/realignment_helpers.py`.

## The `padding` field

Each fixture's `detected_cues` are only the silences found inside the audio that was scanned
at capture time — a ±padding window around each reference timestamp. The tests reproduce a
production first pass by filtering those cues to the regions the *current* code would scan
(`production_padding()` → `extraction_regions()`), so a fixture must declare the width it was
captured at.

- **Fixtures exported since the detection-expansion work** carry a `padding` field recording
  that width. The current capture width equals the pipeline's first-pass padding, so the
  filter keeps every cue as captured.
- **Older fixtures lack the field.** They were captured under the previous `max(180, 2·…)`
  default, so their cues span a much wider window. A missing `padding` therefore means
  "legacy ≥180s capture — recompute the current width from the formula," which is exactly
  what `production_padding()` does (falling back to the current capture witdh). This is sound
  because the old 180s window always subsumes the current one, so filtering the wide capture
  yields the same cue set a fresh narrow capture would.

Do **not** backfill `padding` onto a legacy fixture: writing its true capture width (180s)
would make the test score it at the old, wide coverage instead of today's, and writing the
formula value would just duplicate the fallback while falsely claiming the cues were detected
at 15s. Leave the field absent — its absence is the signal.
