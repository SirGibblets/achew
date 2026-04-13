import uuid
from enum import Enum
from typing import Dict, List, Union

from pydantic import BaseModel, Field


class CueSourceType(str, Enum):
    ABS = "abs"
    EMBEDDED = "embedded"
    AUDNEXUS = "audnexus"
    FILE_DATA = "file_data"
    JSON = "json"
    CSV = "csv"
    CUE = "cue"


class TitleSourceType(str, Enum):
    TEXT = "text"
    EPUB = "epub"
    CUSTOM = "custom"


class ExistingCue(BaseModel):
    timestamp: float
    title: str


class ExistingSourceBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    short_name: str
    description: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class ExistingCueSource(ExistingSourceBase):
    type: CueSourceType
    cues: List[ExistingCue]
    duration: float


class ExistingTitleSource(ExistingSourceBase):
    type: TitleSourceType
    titles: List[str]


ExistingSource = Union[ExistingCueSource, ExistingTitleSource]
