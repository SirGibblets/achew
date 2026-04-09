import logging

from ...models.sources import ExistingTitleSource, TitleSourceType
from .base_parser import BaseTitleParser

logger = logging.getLogger(__name__)

_MAX_LINES = 499


class TextParser(BaseTitleParser):
    short_name = "Txt File"

    def parse(self, file_path: str, source_name: str) -> ExistingTitleSource:
        """Parse a plain-text file as a title-only source (one title per line).

        Rejects files with 500 or more non-blank lines as implausibly large.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                raw_lines = f.readlines()
        except UnicodeDecodeError:
            with open(file_path, encoding="latin-1") as f:
                raw_lines = f.readlines()
        except Exception as e:
            raise ValueError(f"Could not read text file: {e}") from e

        titles = [line.strip() for line in raw_lines if line.strip()]

        if len(titles) >= 500:
            raise ValueError(
                f"Text file has {len(titles)} lines which is implausibly large for chapter titles (limit: {_MAX_LINES})"
            )

        if not titles:
            raise ValueError("Text file contains no non-blank lines")

        name = self.ellipsize_name(source_name)
        logger.info(f"Parsed {source_name} as text title source ({len(titles)} titles)")
        return ExistingTitleSource(
            type=TitleSourceType.TEXT,
            name=f"[TXT] {name}",
            short_name=self.short_name,
            description=f"Chapter titles parsed from text file \"{name}\"",
            metadata={"File": source_name},
            titles=titles,
        )
