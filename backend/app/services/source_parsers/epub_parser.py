import logging

from ...models.sources import ExistingTitleSource, TitleSourceType
from .base_parser import BaseTitleParser

logger = logging.getLogger(__name__)


def _extract_toc_titles(toc_items, depth=0) -> list[str]:
    """Recursively extract title strings from an ebooklib TOC structure."""
    titles = []
    for item in toc_items:
        # ebooklib TOC items can be a Link (has .title) or a tuple (section, children)
        if isinstance(item, tuple):
            section, children = item
            if hasattr(section, "title") and section.title:
                titles.append(section.title.strip())
            titles.extend(_extract_toc_titles(children, depth + 1))
        elif hasattr(item, "title") and item.title:
            titles.append(item.title.strip())
    return titles


class EpubParser(BaseTitleParser):
    short_name = "EPUB"

    def parse(self, file_path: str, source_name: str) -> ExistingTitleSource:
        """Parse an EPUB file and extract chapter titles from its TOC.

        Falls back to spine item titles if the TOC is empty.
        """
        import ebooklib
        from ebooklib import epub

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                book = epub.read_epub(file_path)
        except Exception as e:
            raise ValueError(f"Could not read EPUB: {e}") from e

        titles = _extract_toc_titles(book.toc)

        if not titles:
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                title = item.get_name() or ""
                title = title.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
                if title:
                    titles.append(title)

        titles = [t for t in titles if t]

        if not titles:
            raise ValueError("Could not extract any chapter titles from EPUB")

        name = self.ellipsize_name(source_name)
        logger.info(f"Parsed {source_name} as EPUB title source ({len(titles)} titles)")
        return ExistingTitleSource(
            type=TitleSourceType.EPUB,
            name=f"[EPUB] {name}",
            short_name=self.short_name,
            description=f"Chapter titles extracted from EPUB file \"{name}\"",
            metadata={"File": source_name},
            titles=titles,
        )
