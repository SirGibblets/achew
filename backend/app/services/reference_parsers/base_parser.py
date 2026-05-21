import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ...models.references import ChapterReference, TitleReference


class BaseParser(ABC):
    short_name: ClassVar[str]

    @staticmethod
    def ellipsize_name(filename: str, max_len: int = 20) -> str:
        stem, ext = os.path.splitext(filename)
        if len(stem) <= max_len:
            return filename
        return stem[:max_len].rstrip() + "…" + ext


class BaseChapterRefParser(BaseParser):
    @abstractmethod
    def parse(self, file_path: str, ref_name: str, duration: float = 0.0) -> "ChapterReference": ...


class BaseTitleRefParser(BaseParser):
    @abstractmethod
    def parse(self, file_path: str, ref_name: str) -> "TitleReference": ...
