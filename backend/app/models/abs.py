import re
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class SeriesDetails(BaseModel):
    id: str
    name: str
    sequence: Optional[str] = None


# Minified ABS items carry no structured series object, only a flat display string
# of the form "Sample Series #2" (the sequence suffix is absent when unnumbered).
_SERIES_NAME_RE = re.compile(r"^(?P<name>.+?)(?:\s+#(?P<sequence>\S+))?$")


def _parse_series_name(series_name: str) -> Optional[SeriesDetails]:
    """Split a flat ABS series display string into its name and sequence.

    Returns None when the string holds several comma-joined series, since there is
    no reliable way to tell those apart from a series name that contains a comma.
    """
    if "," in series_name:
        return None
    match = _SERIES_NAME_RE.match(series_name.strip())
    if not match:
        return None
    # Minified items give no series id, and nothing downstream needs one here.
    return SeriesDetails(id="", name=match.group("name"), sequence=match.group("sequence"))


class AudioFileMetadata(BaseModel):
    filename: str
    ext: str
    relPath: str
    size: int


class BookChapter(BaseModel):
    title: str
    start: float
    end: float


class AudioFile(BaseModel):
    ino: str
    mimeType: str
    duration: float
    metadata: AudioFileMetadata
    chapters: List[BookChapter] = []


class AudioInfo(BaseModel):
    codec: Optional[str] = None
    container: Optional[str] = None
    ffmpeg_output: Optional[str] = None  # full `ffmpeg -i` stderr, for diagnostics


class AuthorEntry(BaseModel):
    id: Optional[str] = None
    name: str

    model_config = ConfigDict(extra="ignore")


class BookMetadata(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _coerce_series_shape(cls, data: Any) -> Any:
        """Wrap the single-series dict form into the list the model declares.

        A `filter=series.<id>` query returns `series` as one dict describing the
        matched series, where every other ABS response returns a list.
        """
        if isinstance(data, dict) and isinstance(data.get("series"), dict):
            data = {**data, "series": [data["series"]]}
        return data

    title: str
    subtitle: Optional[str] = None
    authorName: Optional[str] = ""
    authors: Optional[List[AuthorEntry]] = None
    narratorName: Optional[str] = ""
    narrators: Optional[List[str]] = None

    @model_validator(mode="after")
    def _coerce_names(self) -> "BookMetadata":
        """Normalise between the list formats (`authors`, `narrators`) and the flat
        `authorName` / `narratorName` strings, so callers see both regardless of which
        ABS response shape produced this item. The expanded item response populates
        both; the minified one (library items, `filter=` queries) has only the flat
        strings, while some non-expanded responses have only the list forms."""
        if self.authors and not self.authorName:
            self.authorName = self.authors[0].name
        if self.narrators and not self.narratorName:
            self.narratorName = ", ".join(n for n in self.narrators if n)
        # ABS joins these with ", ", keeping any inverted "Last, First" form in the
        # separate authorNameLF field, so splitting on the same separator is safe.
        if self.authorName and not self.authors:
            self.authors = [AuthorEntry(name=n.strip()) for n in self.authorName.split(",") if n.strip()]
        if self.narratorName and not self.narrators:
            self.narrators = [n.strip() for n in self.narratorName.split(",") if n.strip()]
        if not self.series and self.seriesName:
            parsed = _parse_series_name(self.seriesName)
            if parsed:
                self.series = [parsed]
        return self

    seriesName: Optional[str] = None
    seriesTitle: Optional[str] = None
    series: Optional[List[SeriesDetails]] = None
    seriesOrder: Optional[str] = None
    genres: List[str]
    publishedYear: Optional[str]
    description: Optional[str]
    asin: Optional[str] = None
    language: Optional[str] = None

    # Allow extra fields in case ABS API returns additional metadata
    model_config = ConfigDict(extra="ignore")


class BookMedia(BaseModel):
    metadata: BookMetadata
    coverPath: str
    duration: Optional[float] = None
    audioFiles: List[AudioFile] = []
    chapters: List[BookChapter] = []
    numChapters: Optional[int] = None
    numAudioFiles: Optional[int] = None

    model_config = ConfigDict(extra="ignore")

    @property
    def file_count(self) -> int:
        """Get the number of audio files"""
        return len(self.audioFiles)

    @property
    def total_duration(self) -> float:
        """Get the total duration across all audio files"""
        return sum(f.duration for f in self.audioFiles)


class LibraryFileMetadata(BaseModel):
    filename: str
    ext: str
    path: str
    size: int

    model_config = ConfigDict(extra="ignore")


class LibraryFile(BaseModel):
    ino: str
    metadata: LibraryFileMetadata
    fileType: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class Book(BaseModel):
    id: str
    libraryId: Optional[str] = None
    addedAt: int
    updatedAt: int
    media: BookMedia
    libraryFiles: List[LibraryFile] = []
    _calculated_duration: Optional[float] = None

    model_config = ConfigDict(extra="ignore")

    @computed_field
    @property
    def duration(self) -> float:
        """Get the total duration across all audio files"""
        if self.media.duration:
            return self.media.duration
        if self._calculated_duration is None:
            self._calculated_duration = self.media.total_duration
        return self._calculated_duration


class MatchType(str, Enum):
    """Which field of a book matched a library search query.

    The declaration order is the result ranking order: a book reachable through
    several routes is attributed to the first one that found it.
    """

    TITLE = "title"
    SUBTITLE = "subtitle"
    SERIES = "series"
    AUTHOR = "author"
    NARRATOR = "narrator"


class LibrarySearchHit(BaseModel):
    book: Book
    match_type: MatchType
    # The specific field value that matched, e.g. the matched author name. A book can
    # list several authors or narrators, so the frontend needs to be told which of
    # them the query actually hit rather than re-deriving it.
    match_text: str


class LibrarySearchResponse(BaseModel):
    hits: List[LibrarySearchHit]
    # Match count before truncation to the request's limit, so the UI can report
    # how many results it is not showing.
    total: int


class ABSResponse(BaseModel):
    results: List[Book]
    total: int
    limit: int
    page: int
    sortBy: str
    sortDesc: bool
    offset: int

    model_config = ConfigDict(extra="ignore")


class BookSearchSeriesEntry(BaseModel):
    series: str
    sequence: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class BookSearchResult(BaseModel):
    title: str
    author: Optional[str] = None
    narrator: Optional[str] = None
    narrators: List[str] = []
    cover: Optional[str] = None
    asin: Optional[str] = None
    duration: Optional[float] = None
    descriptionPlain: Optional[str] = None
    series: Optional[List[BookSearchSeriesEntry]] = None
    matchConfidence: Optional[float] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _coerce_narrators(self) -> "BookSearchResult":
        """Normalise the new `narrators` list and legacy `narrator` string into a single list."""
        if not self.narrators and self.narrator:
            self.narrators = [n.strip() for n in self.narrator.split(",") if n.strip()]
        return self


class AudnexusChapter(BaseModel):
    lengthMs: int
    startOffsetMs: int
    startOffsetSec: int
    title: str


class AudnexusChapterList(BaseModel):
    asin: str
    brandIntroDurationMs: int
    brandOutroDurationMs: int
    chapters: List[AudnexusChapter]
    isAccurate: bool
    runtimeLengthMs: int
    runtimeLengthSec: int
