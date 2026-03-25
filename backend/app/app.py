import asyncio
import logging
import random
from typing import Optional, List
from datetime import datetime, timezone

from app.core.constants import MAX_JITTER_CROP, MIN_SEGMENT_GAP
from app.services.asr_service_options import get_asr_buffer

from .models.websocket import WSMessage, WSMessageType
from .models.enums import Step
from .services.progress_dispatcher import ProgressDispatcher
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

            # Warm ASR service cache
            self._warm_asr_service = None
            self._warm_asr_config_key: tuple = ()

            # Progress dispatcher
            self.progress_dispatcher = ProgressDispatcher(
                broadcast_progress=self._handle_progress_update,
                broadcast_step_change=self.broadcast_step_change,
            )

            # Transcription queue
            self._transcription_statuses: dict = {}  # chapter_id -> "pending" | "transcribing" | "finished"
            self._transcription_queue: asyncio.Queue = asyncio.Queue()
            self._transcription_worker_task: Optional[asyncio.Task] = None

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

        # Start the progress dispatcher
        self.progress_dispatcher.start()

        # Create pipeline
        self.pipeline = ProcessingPipeline(item_id=item_id, progress_callback=self.progress_dispatcher.notify)

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
        # Keep dispatcher's step tracking in sync so it correctly detects
        # future step changes, even when this is called outside the dispatcher.
        self.progress_dispatcher._current_step = new_step

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

    # ASR service warm cache management
    async def get_or_create_asr_service(self, progress_callback=None):
        """Get the cached ASR service, or create a new one if config changed"""
        from .services.asr_service_options import create_asr_service, get_asr_config_key

        current_key = get_asr_config_key()

        if self._warm_asr_service is not None and self._warm_asr_config_key == current_key:
            # Reuse cached service, update progress callback
            self._warm_asr_service.progress_callback = progress_callback
            return self._warm_asr_service

        # Config changed or no cached service — tear down old one and create new
        await self.release_asr_service()

        logger.info(f"Creating new ASR service for config: {current_key}")
        service = create_asr_service(progress_callback=progress_callback)
        self._warm_asr_service = await service.__aenter__()
        self._warm_asr_config_key = current_key
        return self._warm_asr_service

    async def release_asr_service(self):
        """Release the cached ASR service"""
        if self._warm_asr_service is not None:
            try:
                await self._warm_asr_service.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error releasing ASR service: {e}")
            finally:
                self._warm_asr_service = None
                self._warm_asr_config_key = ()

    # Transcription queue management
    @property
    def has_active_transcriptions(self) -> bool:
        return len(self._transcription_statuses) > 0

    async def enqueue_transcription(self, chapter_ids: list, is_batch: bool = False):
        """Queue chapters for transcription and start the worker if needed"""
        if not self.pipeline:
            raise RuntimeError("No active pipeline")
        if self.pipeline.step == Step.ASR_PROCESSING:
            raise RuntimeError("Cannot transcribe individual chapters during bulk ASR processing")

        for cid in chapter_ids:
            self._transcription_statuses[cid] = "pending"
        await self._broadcast_transcribing_state()

        # Put a single work item on the queue
        await self._transcription_queue.put({
            "chapter_ids": chapter_ids,
            "is_batch": is_batch,
        })

        # Start worker if not running
        if self._transcription_worker_task is None or self._transcription_worker_task.done():
            self._transcription_worker_task = asyncio.create_task(self._transcription_worker())

    async def _transcription_worker(self):
        """Process transcription requests from the queue"""
        import tempfile
        import os
        from .services.audio_service import AudioProcessingService
        from .models.chapter_operation import TranscribeOperation, BatchChapterOperation
        from .core.config import get_app_config

        logger.info("Transcription worker started")

        try:
            while not self._transcription_queue.empty():
                work_item = await self._transcription_queue.get()
                chapter_ids = work_item["chapter_ids"]
                is_batch = work_item["is_batch"]

                operations = []

                for chapter_id in chapter_ids:
                    try:
                        if not self.pipeline:
                            break

                        self._transcription_statuses[chapter_id] = "transcribing"
                        await self._broadcast_transcribing_state()

                        chapter = next(
                            (c for c in self.pipeline.chapters if c.id == chapter_id),
                            None,
                        )
                        if not chapter:
                            logger.warning(f"Chapter {chapter_id} not found, skipping")
                            continue

                        config = get_app_config()
                        segment_length = config.asr_options.segment_length

                        # Calculate segment end time
                        chapter_idx = self.pipeline.chapters.index(chapter)
                        next_chapters = [
                            c for c in self.pipeline.chapters[chapter_idx + 1:]
                            if not c.deleted
                        ]
                        max_end = self.pipeline.book.duration if self.pipeline.book else chapter.timestamp + segment_length
                        if next_chapters:
                            max_end = min(max_end, next_chapters[0].timestamp - MIN_SEGMENT_GAP)
                        duration = min(segment_length, max_end - chapter.timestamp)
                        if duration <= 0:
                            logger.warning(f"No audio available for chapter {chapter_id}")
                            continue

                        # Extract audio segment to temp file
                        temp_dir = tempfile.mkdtemp(dir=self.pipeline.temp_dir)
                        ext = "aac"
                        if self.pipeline.audio_file_path:
                            from pathlib import Path as PPath
                            src_ext = PPath(self.pipeline.audio_file_path).suffix.lstrip(".")
                            if src_ext in ["m4b", "m4a", "mp4"]:
                                ext = "aac"
                            elif src_ext:
                                ext = src_ext

                        output_path = os.path.join(temp_dir, f"segment_{chapter_id}.{ext}")
                        audio_service = AudioProcessingService(
                            lambda *args, **kwargs: None,
                            running_processes=self.pipeline._running_processes,
                            asr_buffer=get_asr_buffer(),
                        )

                        # Introduce time jitter to avoid overly deterministic results when re-transcribing
                        jitter = random.uniform(0.0, MAX_JITTER_CROP)
                        start_time = max(jitter, chapter.timestamp - jitter)

                        loop = asyncio.get_event_loop()
                        segment_path = await loop.run_in_executor(
                            None,
                            audio_service.extract_single_segment,
                            self.pipeline.audio_file_path,
                            start_time,
                            duration,
                            output_path,
                        )

                        if not segment_path:
                            logger.warning(f"Failed to extract audio for chapter {chapter_id}")
                            continue

                        # Trim the segment
                        trimmed_path = os.path.join(temp_dir, f"trimmed_{chapter_id}.{ext}")
                        if config.asr_options.trim:
                            await loop.run_in_executor(
                                None,
                                audio_service._trim_segment_to_path,
                                segment_path,
                                trimmed_path,
                            )
                            if os.path.exists(trimmed_path):
                                segment_path = trimmed_path
                        # If trim produced nothing or trim disabled, use the raw segment

                        # Transcribe
                        asr_service = await self.get_or_create_asr_service(
                            progress_callback=lambda *args, **kwargs: None
                        )
                        transcription = await asyncio.get_event_loop().run_in_executor(
                            None, asr_service.transcribe_file, segment_path
                        )

                        # Create and apply operation
                        op = TranscribeOperation(
                            chapter_id=chapter_id,
                            new_asr_title=transcription,
                            new_current_title=transcription,
                        )
                        operations.append(op)

                        if not is_batch:
                            # Apply immediately for single transcriptions
                            op.apply(self.pipeline)
                            self.pipeline.add_to_history(op)
                            await self.broadcast_chapter_update()
                            await self.broadcast_history_update()

                        # Clean up temp files
                        try:
                            import shutil
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        except Exception:
                            pass

                    except Exception as e:
                        logger.error(f"Failed to transcribe chapter {chapter_id}: {e}", exc_info=True)
                    finally:
                        if is_batch:
                            self._transcription_statuses[chapter_id] = "finished"
                        else:
                            self._transcription_statuses.pop(chapter_id, None)
                        await self._broadcast_transcribing_state()

                # For batch operations, wrap in BatchChapterOperation
                if is_batch and operations and self.pipeline:
                    batch_op = BatchChapterOperation(operations=operations)
                    batch_op.apply(self.pipeline)
                    self.pipeline.add_to_history(batch_op)
                    await self.broadcast_chapter_update()
                    await self.broadcast_history_update()

                # Clear all statuses for this batch
                if is_batch:
                    for cid in chapter_ids:
                        self._transcription_statuses.pop(cid, None)
                    await self._broadcast_transcribing_state()

        except Exception as e:
            logger.error(f"Transcription worker error: {e}", exc_info=True)
        finally:
            # Clean up any remaining transcribing state
            self._transcription_statuses.clear()
            await self._broadcast_transcribing_state()
            logger.info("Transcription worker finished")

    async def _broadcast_transcribing_state(self):
        """Broadcast transcription statuses for all chapters"""
        message = WSMessage(
            type=WSMessageType.TRANSCRIBING_UPDATE,
            data={"statuses": dict(self._transcription_statuses)},
        )
        await self.broadcast_message(message)

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
                    "total_count": stats["total"],
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
