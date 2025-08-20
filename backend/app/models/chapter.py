from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from .enums import ActionType


class ChapterData(BaseModel):
    id: int
    timestamp: float
    asr_title: str
    current_title: str
    deleted: bool = False
    audio_segment_path: str
    created_at: datetime = Field(default_factory=datetime.now)
    modified_at: datetime = Field(default_factory=datetime.now)
    _selected: bool = True

    @computed_field
    @property
    def selected(self) -> bool:
        return self._selected and not self.deleted

    @selected.setter
    def selected(self, value: bool) -> None:
        self._selected = value


class ChapterHistory(BaseModel):
    action_type: ActionType
    chapter_id: int | None = None
    old_value: Any = None
    new_value: Any = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ChapterBatchHistory(BaseModel):
    batch_id: str
    operations: list[ChapterHistory]
    description: str
    timestamp: datetime = Field(default_factory=datetime.now)
