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
