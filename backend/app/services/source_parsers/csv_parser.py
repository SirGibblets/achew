import csv
import logging
from ...models.sources import CueSourceType, ExistingCue, ExistingCueSource
from .base_parser import BaseCueParser
from .timestamp_utils import normalize_timestamps, parse_timestamp, score_timestamp
from .title_utils import score_title

logger = logging.getLogger(__name__)

_TIMESTAMP_POSITIVE = {"start", "time", "timestamp", "offset", "begin", "position"}
_TIMESTAMP_NEGATIVE = {"end", "length", "duration", "stop", "finish"}
_TITLE_KEYWORDS = {"title", "name", "chapter", "label", "heading", "text"}


class CsvParser(BaseCueParser):
    short_name = "CSV"

    def parse(self, file_path: str, source_name: str, duration: float = 0.0) -> ExistingCueSource:
        """Parse a CSV for chapter cue data using heuristic column scoring."""
        rows = []
        try:
            with open(file_path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not any(cell.strip() for cell in row):
                        continue
                    rows.append([cell.strip() for cell in row])
        except Exception as e:
            raise ValueError(f"Could not read CSV: {e}") from e

        if not rows:
            raise ValueError("No data rows found in CSV")

        max_cols = max(len(r) for r in rows)
        if max_cols < 2:
            raise ValueError("CSV must have at least 2 columns")

        def get_cell(row, idx):
            return row[idx] if idx < len(row) else ""

        first_row = [get_cell(rows[0], i) for i in range(max_cols)]

        best_ts_idx = -1
        best_ts_score = -float("inf")

        for col_idx in range(max_cols):
            score = 0
            header_val = first_row[col_idx].lower()
            if any(pos in header_val for pos in _TIMESTAMP_POSITIVE):
                score += 10
            if any(neg in header_val for neg in _TIMESTAMP_NEGATIVE):
                score -= 10

            start_idx = 1 if len(rows) > 1 else 0
            for row_idx in range(start_idx, len(rows)):
                val = get_cell(rows[row_idx], col_idx)
                score += score_timestamp(val)

            if score > best_ts_score:
                best_ts_score = score
                best_ts_idx = col_idx

        best_title_idx = -1
        best_title_score = -float("inf")

        for col_idx in range(max_cols):
            if col_idx == best_ts_idx:
                continue

            score = 0
            header_val = first_row[col_idx].lower()
            if any(kw in header_val for kw in _TITLE_KEYWORDS):
                score += 10

            start_idx = 1 if len(rows) > 1 else 0
            for row_idx in range(start_idx, len(rows)):
                val = get_cell(rows[row_idx], col_idx)
                score += score_title(val)

            if score > best_title_score:
                best_title_score = score
                best_title_idx = col_idx

        if best_ts_idx == -1 or best_title_idx == -1:
            raise ValueError("No plausible timestamp/title columns found.")

        if rows and parse_timestamp(get_cell(rows[0], best_ts_idx)) is None:
            rows = rows[1:]

        raw_timestamps = []
        titles = []
        for row in rows:
            ts = parse_timestamp(get_cell(row, best_ts_idx))
            if ts is None:
                continue
            raw_timestamps.append(ts)
            titles.append(get_cell(row, best_title_idx))

        if not raw_timestamps:
            raise ValueError("No plausible timestamp/title columns found.")

        normalised = normalize_timestamps(raw_timestamps)
        cues = list(zip(normalised, titles))

        if duration and cues and abs(cues[-1][0] - duration) <= 3:
            cues = cues[:-1]

        name = self.ellipsize_name(source_name)
        logger.info(f"Parsed {source_name} as CSV cue source ({len(cues)} cues)")
        return ExistingCueSource(
            type=CueSourceType.CSV,
            name=f"CSV File ({name})",
            short_name=self.short_name,
            description=f"Chapter data parsed from CSV file \"{name}\"",
            metadata={"File": source_name},
            cues=[ExistingCue(timestamp=ts, title=t) for ts, t in cues],
            duration=duration,
        )
