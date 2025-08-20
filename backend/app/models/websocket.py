from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    PROGRESS_UPDATE = "progress_update"
    STEP_CHANGE = "step_change"
    CHAPTER_UPDATE = "chapter_update"
    HISTORY_UPDATE = "history_update"
    SELECTION_STATS = "selection_stats"
    BATCH_OPERATION = "batch_operation"
    ERROR = "error"
    STATUS = "status"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class ProgressUpdateData(BaseModel):
    step: str
    percent: float
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class StepChangeData(BaseModel):
    old_step: str
    new_step: str
    data: Dict[str, Any] = Field(default_factory=dict)


class ChapterUpdateData(BaseModel):
    chapters: List[Dict[str, Any]]
    total_count: int
    selected_count: int


class HistoryUpdateData(BaseModel):
    can_undo: bool
    can_redo: bool
    current_description: Optional[str] = None


class BatchOperationData(BaseModel):
    operation: str
    affected_count: int
    description: str
    success: bool = True


class ErrorData(BaseModel):
    message: str
    details: Optional[str] = None
    code: Optional[str] = None
    recoverable: bool = True


class SelectionStatsData(BaseModel):
    total: int
    selected: int
    unselected: int


def create_selection_stats_message(total: int, selected: int) -> WSMessage:
    return WSMessage(
        type=WSMessageType.SELECTION_STATS,
        data=SelectionStatsData(
            total=total,
            selected=selected,
            unselected=total - selected,
        ).model_dump(),
    )
