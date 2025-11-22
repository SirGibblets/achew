from datetime import datetime
from typing import Optional
import uuid


from pydantic import BaseModel, Field, computed_field

class RealignmentData(BaseModel):
    original_timestamp: float
    confidence: float
    is_guess: bool

class ChapterData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float
    asr_title: str
    current_title: str
    deleted: bool = False
    audio_segment_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    modified_at: datetime = Field(default_factory=datetime.now)
    realignment: Optional[RealignmentData] = None
    _selected: bool = True

    @computed_field
    @property
    def selected(self) -> bool:
        return self._selected and not self.deleted

    @selected.setter
    def selected(self, value: bool) -> None:
        self._selected = value
