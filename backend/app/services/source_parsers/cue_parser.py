import logging
import re
from typing import Optional

from ...models.sources import CueSourceType, ExistingCue, ExistingCueSource
from .base_parser import BaseCueParser

logger = logging.getLogger(__name__)

_TRACK_RE = re.compile(r"^\s*TRACK\s+\d+\s+AUDIO", re.IGNORECASE)
_TITLE_RE = re.compile(r'^\s*TITLE\s+"(.*)"', re.IGNORECASE)
_INDEX_RE = re.compile(r"^\s*INDEX\s+01\s+(\d+):(\d+):(\d+)", re.IGNORECASE)


class CueParser(BaseCueParser):
    short_name = "CUE"

    def parse(self, file_path: str, source_name: str, duration: float = 0.0) -> ExistingCueSource:
        """Parse a CUE sheet file for chapter cue data.

        CUE INDEX timestamps use MM:SS:FF format (75 frames per second).
        """
        try:
            try:
                with open(file_path, encoding="utf-8") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(file_path, encoding="latin-1") as f:
                    lines = f.readlines()
        except Exception as e:
            raise ValueError(f"Could not read CUE file: {e}") from e

        cues = []
        current_title: Optional[str] = None
        in_track = False

        for line in lines:
            if _TRACK_RE.match(line):
                in_track = True
                current_title = None
                continue

            if in_track:
                m = _TITLE_RE.match(line)
                if m:
                    current_title = m.group(1).strip()
                    continue

                m = _INDEX_RE.match(line)
                if m:
                    mm, ss, ff = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    timestamp = mm * 60 + ss + ff / 75.0
                    title = current_title or f"Track {len(cues) + 1}"
                    cues.append((timestamp, title))
                    in_track = False
                    continue

        if not cues:
            raise ValueError("No TRACK/INDEX entries found in CUE file")

        name = self.ellipsize_name(source_name)
        logger.info(f"Parsed {source_name} as CUE cue source ({len(cues)} cues)")
        return ExistingCueSource(
            type=CueSourceType.CUE,
            name=f"Cue Sheet ({name})",
            short_name=self.short_name,
            description=f"Chapter data parsed from CUE Sheet file \"{name}\"",
            metadata={"File": source_name},
            cues=[ExistingCue(timestamp=ts, title=t) for ts, t in cues],
            duration=duration,
        )
