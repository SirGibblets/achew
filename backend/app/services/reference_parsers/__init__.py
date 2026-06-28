from .csv_parser import CsvParser
from .cue_parser import CueParser
from .epub_parser import EpubParser
from .json_parser import JsonParser
from .mobi_parser import MobiParser
from .text_parser import TextParser

csv_parser = CsvParser()
cue_parser = CueParser()
epub_parser = EpubParser()
json_parser = JsonParser()
mobi_parser = MobiParser()
text_parser = TextParser()

__all__ = [
    "csv_parser",
    "cue_parser",
    "epub_parser",
    "json_parser",
    "mobi_parser",
    "text_parser",
]
