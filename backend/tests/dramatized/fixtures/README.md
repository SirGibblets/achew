# Dramatized detection fixtures

Real captures used by `test_real_fixture_matches_ground_truth` in
[`../test_dramatized_detection.py`](../test_dramatized_detection.py). Each file pins one
book's standard vs VAD probe cues against a known ground-truth label, so the heuristic in
`backend/app/services/dramatized_detection.py` can be tuned without regressing real books.

## How to generate one

1. Run the dev server with DEBUG on: `./dev.sh`.
2. Load a book and reach the **Select a Workflow** step (Smart Detect / Realign tab).
3. Open the **Audiobook info** dialog. In the **Debug · Dramatized fixture** section, set the
   toggle to the book's true type (**Standard** or **Dramatized**) and click
   **Run detection & export fixture**.
4. The dialog reports whether the heuristic agreed, and downloads a
   `dramatized_fixture_<timestamp>.json`. Drop it in this directory and commit it.

## File shape

```json
{
  "book_duration": 0,
  "windows": [[0, 300], [..., ...]],
  "standard_cues": [[timestamp, gap], ...],
  "vad_cues": [[timestamp, gap], ...],
  "ground_truth_dramatized": true
}
```

The file holds only durable inputs: the recorded probe cues, the ground-truth label, and
capture provenance (`book_duration`, `windows`). The test reads `standard_cues`, `vad_cues`,
and `ground_truth_dramatized`. The heuristic's own verdict is deliberately **not** stored —
the test recomputes it, so persisting it would only go stale when the detection code is
tuned. The debug dialog shows that verdict at capture time instead.
