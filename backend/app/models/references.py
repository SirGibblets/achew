import uuid
from enum import Enum
from typing import Dict, List, Union

from pydantic import BaseModel, Field

from app.models.chapter import BasicChapter


class ChapterRefType(str, Enum):
    ABS = "abs"
    EMBEDDED = "embedded"
    AUDNEXUS = "audnexus"
    FILE_DATA = "file_data"
    JSON = "json"
    CSV = "csv"
    CUE = "cue"
    SNAPSHOT = "snapshot"


class TitleRefType(str, Enum):
    TEXT = "text"
    EPUB = "epub"
    MOBI = "mobi"
    CUSTOM = "custom"


class ReferenceBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    short_name: str
    description: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class ChapterReference(ReferenceBase):
    type: ChapterRefType
    chapters: List[BasicChapter]
    duration: float
    # Names of References with identical chapter data that were collapsed into this one
    merged_names: List[str] = Field(default_factory=list)


class TitleReference(ReferenceBase):
    type: TitleRefType
    titles: List[str]


Reference = Union[ChapterReference, TitleReference]
