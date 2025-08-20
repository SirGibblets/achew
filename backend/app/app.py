import asyncio
import logging
from typing import Optional, List
from datetime import datetime, timezone

from .models.websocket import WSMessage, WSMessageType
from .models.enums import Step
from .models.progress import ProgressCallback
from .core.config import get_configuration_status

logger = logging.getLogger(__name__)


class AppState:
    """Singleton app state manager that replaces the session concept"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppState, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._app_step: Optional[Step] = None
            self.pipeline = None

            # WebSocket connections
            self.websocket_connections: List = []

            AppState._initialized = True

    @property
    def step(self) -> Step:
        config_status = get_configuration_status()
        if config_status["needs_abs_setup"]:
            return Step.ABS_SETUP

        if self._app_step:
            return self._app_step

        if self.pipeline:
            return self.pipeline.step

        return Step.IDLE

    @step.setter
    def step(self, value: Optional[Step]):
        """Set the current application step and broadcast change"""
        self._app_step = value

    def create_pipeline(self, item_id: str):
        """Create a new processing pipeline for the given item"""
        # Only allow one pipeline at a time
        if self.pipeline:
            raise RuntimeError("You are already processing an audiobook. Please refresh the page.")

        # Dynamic import to avoid circular dependencies
        from .services.processing_pipeline import ProcessingPipeline

        # Create progress callback for WebSocket updates
        progress_callback: ProgressCallback = lambda step, percent, message="", details=None: asyncio.create_task(
            self._handle_progress_update(step, percent, message, details)
        )

        # Create pipeline
        self.pipeline = ProcessingPipeline(item_id=item_id, progress_callback=progress_callback)

        logger.info(f"Created pipeline for item {item_id}")
        return self.pipeline

    def delete_pipeline(self) -> bool:
        """Delete the current pipeline and cleanup resources"""
        try:
            if not self.pipeline:
                return False

            # Clean up pipeline
            try:
                self.pipeline.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up pipeline: {e}")
            finally:
                self.pipeline = None

            # Reset state
            self.step = None

            logger.info(f"Deleted pipeline")
            return True

        except Exception as e:
            logger.error(f"Error deleting pipeline: {e}")
            return False

    # WebSocket management
    def add_websocket_connection(self, websocket):
        """Add WebSocket connection"""
        self.websocket_connections.append(websocket)
        logger.info(f"Added WebSocket connection")

    def remove_websocket_connection(self, websocket):
        """Remove WebSocket connection"""
        try:
            self.websocket_connections.remove(websocket)
            logger.info(f"Removed WebSocket connection")
        except ValueError:
            pass

    async def broadcast_message(self, message: WSMessage):
        """Broadcast message to all WebSocket connections"""
        connections = self.websocket_connections.copy()
        for websocket in connections:
            try:
                await websocket.send_text(message.model_dump_json())
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                # Remove failed connection
                try:
                    self.websocket_connections.remove(websocket)
                except ValueError:
                    pass

    async def _handle_progress_update(self, step: Step, percent: float, message: str, details: dict):
        """Handle progress updates from processing pipeline"""
        try:
            # Broadcast progress update
            message_obj = WSMessage(
                type=WSMessageType.PROGRESS_UPDATE,
                data={
                    "step": step.value,
                    "percent": percent,
                    "message": message,
                    "details": details or {},
                },
            )
            await self.broadcast_message(message_obj)
        except Exception as e:
            logger.error(f"Error handling progress update: {e}")

    async def broadcast_step_change(
        self,
        new_step: Step,
        extras: dict = None,
        error_message: str = None,
    ):
        """Broadcast step change to WebSocket connections"""
        logger.info(f"Broadcasting step change to {new_step.value}")

        data = {
            "new_step": new_step.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "restart_options": self.pipeline.get_restart_options() if self.pipeline else [],
        }

        # Add any extra data provided by the caller
        if extras:
            data.update(extras)

        message = WSMessage(
            type=WSMessageType.STEP_CHANGE,
            data=data,
        )
        await self.broadcast_message(message)

        # If error message is provided, broadcast it separately
        if error_message:
            error_msg = WSMessage(
                type=WSMessageType.ERROR,
                data={
                    "message": error_message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self.broadcast_message(error_msg)

    async def _broadcast_book_update(self):
        """Broadcast book data update to WebSocket connections"""
        if not self.pipeline or not self.pipeline.book:
            return

        message = WSMessage(
            type=WSMessageType.STATUS,
            data={
                "type": "book_update",
                "book": self.pipeline.book.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await self.broadcast_message(message)

    # Pipeline-related broadcast helpers
    async def broadcast_chapter_update(self):
        """Broadcast chapter update - delegates to pipeline"""
        if self.pipeline:
            chapter_data = [chapter.model_dump() for chapter in self.pipeline.chapters if not chapter.deleted]
            stats = self.pipeline.get_selection_stats()

            message = WSMessage(
                type=WSMessageType.CHAPTER_UPDATE,
                data={
                    "chapters": chapter_data,
                    "total_count": len(self.pipeline.chapters),
                    "selected_count": stats["selected"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self.broadcast_message(message)

    async def broadcast_history_update(self):
        """Broadcast history state update - delegates to pipeline"""
        if self.pipeline:
            can_undo = self.pipeline.can_undo()
            can_redo = self.pipeline.can_redo()

            message = WSMessage(
                type=WSMessageType.HISTORY_UPDATE,
                data={
                    "can_undo": can_undo,
                    "can_redo": can_redo,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self.broadcast_message(message)


# Singleton instance
def get_app_state() -> AppState:
    """Get the singleton app state instance"""
    return AppState()
