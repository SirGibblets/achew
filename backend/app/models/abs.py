from typing import List, Optional

from pydantic import BaseModel, ConfigDict, computed_field


class SeriesDetails(BaseModel):
    id: str
    name: str
    sequence: Optional[str] = None


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


class BookMetadata(BaseModel):
    title: str
    authorName: Optional[str] = ""
    narratorName: Optional[str] = ""
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


class Book(BaseModel):
    id: str
    addedAt: int
    updatedAt: int
    media: BookMedia
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


class ABSResponse(BaseModel):
    results: List[Book]
    total: int
    limit: int
    page: int
    sortBy: str
    sortDesc: bool
    offset: int

    model_config = ConfigDict(extra="ignore")


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
