import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ...models.sources import ExistingCueSource, ExistingTitleSource


class BaseParser(ABC):
    short_name: ClassVar[str]

    @staticmethod
    def ellipsize_name(filename: str, max_len: int = 20) -> str:
        stem, ext = os.path.splitext(filename)
        if len(stem) <= max_len:
            return filename
        return stem[:max_len].rstrip() + "\u2026" + ext


class BaseCueParser(BaseParser):
    @abstractmethod
    def parse(self, file_path: str, source_name: str, duration: float = 0.0) -> "ExistingCueSource":
        ...


class BaseTitleParser(BaseParser):
    @abstractmethod
    def parse(self, file_path: str, source_name: str) -> "ExistingTitleSource":
        ...
