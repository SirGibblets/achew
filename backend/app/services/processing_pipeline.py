import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.api.routes.chapters import DetectedCue
from app.app import get_app_state
from app.models.abs import AudioFile, AudioInfo, Book

from ..core.config import get_app_config
from ..core.constants import BOOK_END_IGNORE_WINDOW
from ..core.system_info import get_worker_count
from ..models.ai_options import AIOptions
from ..models.chapter import ChapterData, RealignmentData
from ..models.chapter_operation import AICleanupOperation, BatchChapterOperation, ChapterOperation
from ..models.enums import RestartStep, Step
from ..models.progress import ProgressCallback
from ..models.references import (
    BasicChapter,
    ChapterReference,
    ChapterRefType,
    TitleReference,
    TitleRefType,
)
from .abs_service import ABSService
from .asr_service_options import get_asr_buffer
from .audio_service import AudioProcessingService, pick_segment_extension, probe_audio_info, probe_segment_extension
from .chapter_aligner import ChapterAligner
from .reference_parsers import csv_parser, cue_parser, epub_parser, json_parser, text_parser
from .vad_detection_service import VadDetectionService

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Exception raised for processing pipeline errors"""

    pass


class PipelineProgress(BaseModel):
    step: Step
    percent: float = 0.0
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class ProcessingPipeline:
    """Main processing pipeline that orchestrates the entire chapter generation workflow"""

    def __init__(self, item_id: str, progress_callback: ProgressCallback):
        self.progress_callback: ProgressCallback = progress_callback
        self.item_id = item_id
        self._running_processes = []
        self._process_lock = threading.Lock()
        self._transcription_task = None
        self._extraction_task = None
        self._trimming_task = None
        self._download_task = None
        self._vad_task = None
        self._ai_cleanup_task: Optional[asyncio.Task] = None
        self.is_realignment: bool = False
        self.is_quick_edit: bool = False

        # Create temporary directory
        sys_tmp_dir = tempfile.gettempdir()
        base_tmp_dir = os.path.join(sys_tmp_dir, "achew")
        os.makedirs(base_tmp_dir, exist_ok=True)
        self.temp_dir = tempfile.mkdtemp(dir=base_tmp_dir, prefix=str(uuid.uuid4()))
        logger.info(f"Created temp directory: {self.temp_dir}")

        # Processing state (formerly in session)
        self.step: Step = Step.IDLE
        self.progress: PipelineProgress = PipelineProgress(step=Step.IDLE)

        # Chapter management
        self.chapters: List[ChapterData] = []
        self.history_stack: List[ChapterOperation] = []
        self.history_index: int = -1

        # Configuration options (per-pipeline)
        self.ai_options: AIOptions = AIOptions()

        # Processing data
        self.book: Optional[Book] = None
        self.audio_file_path: str = ""
        self.audio_unsupported_codec: bool = False
        self.audio_info: Optional[AudioInfo] = None
        self.segment_extension: Optional[str] = None
        self.file_starts: Optional[List[float]] = None
        self.chapter_refs: List[ChapterReference] = []
        self.title_refs: List[TitleReference] = []

        self.cues: List[float] = []
        self.segment_files: List[str] = []
        self.trimmed_segment_files: List[str] = []

        self.detected_cues: List[DetectedCue] = []
        self.initial_chapter_selection_available: bool = False  # True only after smart-detect populates detected_cues

        # Scan coverage tracking
        self.normal_scanned_regions: List[Tuple[float, float]] = []
        self.vad_scanned_regions: List[Tuple[float, float]] = []

        # Partial scan task tracking
        self._partial_scan_task: Optional[asyncio.Task] = None
        self._partial_scan_temp_files: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_all_files()

    def cleanup(self):
        """Cancel running tasks and cleanup resources"""
        # Note: cleanup is synchronous, so we'll just cancel without waiting
        if self._extraction_task:
            self._extraction_task.cancel()
            self._extraction_task = None
        if self._transcription_task:
            self._transcription_task.cancel()
            self._transcription_task = None
        if self._trimming_task:
            self._trimming_task.cancel()
            self._trimming_task = None
        if self._download_task:
            self._download_task.cancel()
            self._download_task = None
        if self._vad_task:
            self._vad_task.cancel()
            self._vad_task = None
        if self._ai_cleanup_task:
            self._ai_cleanup_task.cancel()
            self._ai_cleanup_task = None
        if self._partial_scan_task:
            self._partial_scan_task.cancel()
            self._partial_scan_task = None
        self.cleanup_all_files()

    def cleanup_all_files(self):
        """Cleanup all temporary files and directories"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info(f"Removed temp directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temp directory {self.temp_dir}: {e}")
            self.temp_dir = ""

    def cleanup_segment_files(self):
        """Cleanup segment files if they exist"""
        if self.segment_files:
            for segment_file in self.segment_files:
                try:
                    if os.path.exists(segment_file):
                        os.remove(segment_file)
                except Exception:
                    pass
            self.segment_files = []
        for filename in os.listdir(self.temp_dir):
            if filename.startswith("segment_"):
                try:
                    os.remove(os.path.join(self.temp_dir, filename))
                except Exception:
                    pass

    def cleanup_trimmed_files(self):
        """Cleanup trimmed segment files if they exist"""
        if self.trimmed_segment_files:
            for trimmed_file in self.trimmed_segment_files:
                try:
                    if os.path.exists(trimmed_file):
                        os.remove(trimmed_file)
                except Exception:
                    pass
            self.trimmed_segment_files = []
        for filename in os.listdir(self.temp_dir):
            if filename.startswith("trimmed_"):
                try:
                    os.remove(os.path.join(self.temp_dir, filename))
                except Exception:
                    pass

    def cleanup_partial_scan_files(self):
        """Cleanup temporary files created during partial scanning"""
        for f in list(self._partial_scan_temp_files):
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except Exception as e:
                logger.debug(f"Failed to remove partial scan temp file {f}: {e}")
        self._partial_scan_temp_files = []

    async def cancel_processing(self):
        """Cancel any running processing tasks"""
        logger.info("Cancelling processing pipeline…")

        # Cancel any running extraction tasks
        if self._extraction_task:
            logger.info("Cancelling extraction task…")
            self._extraction_task.cancel()
            try:
                await self._extraction_task
            except asyncio.CancelledError:
                logger.info("Extraction task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for extraction task cancellation: {e}")
            self._extraction_task = None

        # Cancel any running AI cleanup tasks
        if self._ai_cleanup_task:
            logger.info("Cancelling AI cleanup task…")
            self._ai_cleanup_task.cancel()
            try:
                await self._ai_cleanup_task
            except asyncio.CancelledError:
                logger.info("AI cleanup task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for AI cleanup task cancellation: {e}")
            self._ai_cleanup_task = None

        # Cancel any running transcription tasks
        if self._transcription_task:
            logger.info("Cancelling transcription task…")
            self._transcription_task.cancel()
            self._transcription_task = None

        # Cancel any running trimming tasks
        if self._trimming_task:
            logger.info("Cancelling trimming task…")
            self._trimming_task.cancel()
            try:
                await self._trimming_task
            except asyncio.CancelledError:
                logger.info("Trimming task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for trimming task cancellation: {e}")
            self._trimming_task = None

        # Cancel any running download tasks
        if self._download_task:
            logger.info("Cancelling download task…")
            self._download_task.cancel()
            try:
                await self._download_task
            except asyncio.CancelledError:
                logger.info("Download task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for download task cancellation: {e}")
            self._download_task = None

        # Cancel any running VAD tasks
        if self._vad_task:
            logger.info("Cancelling VAD task…")
            self._vad_task.cancel()
            try:
                await self._vad_task
            except asyncio.CancelledError:
                logger.info("VAD task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for VAD task cancellation: {e}")
            self._vad_task = None

        # Cancel any running partial scan tasks
        if self._partial_scan_task:
            logger.info("Cancelling partial scan task…")
            self._partial_scan_task.cancel()
            try:
                await self._partial_scan_task
            except asyncio.CancelledError:
                logger.info("Partial scan task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for partial scan task cancellation: {e}")
            self._partial_scan_task = None
        self.cleanup_partial_scan_files()

        # Cancel any running ffmpeg processes. Snapshot under lock so workers
        # can't add a process between our iteration and the clear().
        with self._process_lock:
            processes_to_kill = list(self._running_processes)
            self._running_processes.clear()

        if processes_to_kill:
            logger.info(f"Cancelling {len(processes_to_kill)} running ffmpeg processes…")

            async def _terminate_and_wait(proc):
                try:
                    if proc.poll() is None:
                        logger.info(f"Terminating ffmpeg process {proc.pid}")
                        proc.terminate()
                        try:
                            loop = asyncio.get_event_loop()
                            await asyncio.wait_for(loop.run_in_executor(None, proc.wait), timeout=2.0)
                        except asyncio.TimeoutError:
                            logger.warning(f"Force killing ffmpeg process {proc.pid}")
                            proc.kill()
                    else:
                        logger.info(f"ffmpeg process {proc.pid} already completed")
                except Exception as e:
                    logger.warning(f"Error cancelling process: {e}")

            await asyncio.gather(*[_terminate_and_wait(p) for p in processes_to_kill])

    async def restart_at_step(self, step: RestartStep, error_message: Optional[str] = None):
        """Restart the pipeline at a specific step"""
        logger.info(f"Restarting pipeline at step: {step}")

        # Invalidate any in-flight progress callbacks before cancelling
        get_app_state().progress_dispatcher.increment_epoch()

        # Cancel any running processes first and wait for them to complete
        await self.cancel_processing()
        await get_app_state().cancel_transcriptions()

        if step == RestartStep.IDLE:
            await get_app_state().delete_pipeline()
            asyncio.create_task(get_app_state().broadcast_step_change(Step.IDLE, error_message=error_message))
            return

        step_num = step.ordinal

        if step_num <= RestartStep.CHAPTER_EDITING.ordinal:
            self.step = Step.CHAPTER_EDITING

        if step_num <= RestartStep.CONFIGURE_ASR.ordinal:
            self.cleanup_segment_files()
            self.cleanup_trimmed_files()
            self.chapters = []
            self.history_stack = []
            self.history_index = -1
            self.step = Step.CONFIGURE_ASR

        if step_num <= RestartStep.INITIAL_CHAPTER_SELECTION.ordinal:
            self.cleanup_segment_files()
            self.cues = []
            self.step = Step.INITIAL_CHAPTER_SELECTION

        if step_num <= RestartStep.SELECT_WORKFLOW.ordinal:
            self.detected_cues = []
            self.normal_scanned_regions = []
            self.vad_scanned_regions = []
            self.initial_chapter_selection_available = False
            self.is_realignment = False
            self.is_quick_edit = False
            self.step = Step.SELECT_WORKFLOW

        # Background tasks have been properly cancelled, safe to broadcast step change
        logger.info(f"Broadcasting step change to {self.step}")
        asyncio.create_task(get_app_state().broadcast_step_change(self.step, error_message=error_message))

    def get_selection_stats(self) -> Dict[str, int]:
        """Get chapter selection statistics"""
        active = [c for c in self.chapters if not c.deleted]
        total = len(active)
        selected = sum(1 for c in active if c.selected)
        return {"total": total, "selected": selected, "unselected": total - selected}

    def can_undo(self) -> bool:
        """Check if undo is possible"""
        return self.history_index >= 0

    def can_redo(self) -> bool:
        """Check if redo is possible"""
        return self.history_index < len(self.history_stack) - 1

    def add_to_history(self, operation: ChapterOperation):
        """Add an action to the history stack"""
        # Remove any future history if we're not at the end
        if self.history_index < len(self.history_stack) - 1:
            self.history_stack = self.history_stack[: self.history_index + 1]

        self.history_stack.append(operation)
        self.history_index = len(self.history_stack) - 1

    def undo(self) -> None:
        """Undo the last action"""
        if not self.can_undo():
            raise ValueError("Cannot undo")

        operation = self.history_stack[self.history_index]
        operation.undo(self)

        self.history_index -= 1

    def redo(self) -> None:
        """Redo the next action"""
        if not self.can_redo():
            raise ValueError("Cannot redo")

        operation = self.history_stack[self.history_index + 1]
        operation.apply(self)

        self.history_index += 1

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: Optional[Dict[str, Any]] = None):
        """Notify progress. Non-blocking, thread-safe via ProgressDispatcher."""
        self.step = step
        self.progress_callback(step, percent, message, details or {})

    def _scoped_progress_callback(self) -> ProgressCallback:
        """Return a progress callback bound to the current dispatcher epoch.

        After a restart (which increments the epoch), any callbacks captured
        from a previous epoch become no-ops, preventing stale progress
        updates from overwriting the pipeline step.
        """
        return get_app_state().progress_dispatcher.scoped_callback()

    def _get_chapter_ref(self, id: str) -> Optional[ChapterReference]:
        """Get a chapter reference by ID"""
        return next((ref for ref in self.chapter_refs if ref.id == id), None)

    @property
    def book_duration(self) -> float:
        """Duration of the loaded book in seconds. Raises if no book is loaded."""
        book = self.book
        if book is None:
            raise ProcessingError("No book is loaded")
        return book.duration

    @property
    def book_id(self) -> str:
        """ID of the loaded book. Raises if no book is loaded."""
        book = self.book
        if book is None:
            raise ProcessingError("No book is loaded")
        return book.id

    def _filter_cues_by_duration(self, cues: List[float]) -> List[float]:
        """Filter out chapter breaks that occur after the audiobook ends"""

        # Filter out chapter breaks that occur after the audio file ends
        filtered_cues = [cue for cue in cues if cue < self.book_duration]

        if len(filtered_cues) < len(cues):
            removed_count = len(cues) - len(filtered_cues)
            logger.info(
                f"Filtered out {removed_count} chapter break(s) that occurred after audiobook end ({self.book_duration:.1f}s)"
            )

        return filtered_cues

    def _silences_to_cues(self, silences: List[Tuple[float, float]]) -> List[DetectedCue]:
        """Convert silence intervals to DetectedCues, dropping false positives near the book's end."""
        cutoff = self.book_duration - BOOK_END_IGNORE_WINDOW
        return [DetectedCue.from_silences(s, e) for s, e in silences if e < cutoff]

    async def _get_file_durations_and_starts(self, audio_files: List[AudioFile]) -> Tuple[List[float], List[float]]:
        """Get the duration of each file and their start positions in a virtual concatenated timeline"""
        durations = []
        file_starts = [0.0]  # First file always starts at 0
        current_position = 0.0

        # Get duration of each file
        for i, audio_file in enumerate(audio_files):
            duration = audio_file.duration
            durations.append(duration)

            # Add start position for next file (except for last file)
            if i < len(audio_files) - 1:
                current_position += duration
                file_starts.append(current_position)

        return durations, file_starts

    async def _download_audio_files(self, abs_service, item_id: str, audio_files) -> Optional[List[str]]:
        """Download audio files with cancellation support"""
        try:
            audio_file_paths = []
            completed_files = 0

            total_bytes_all_files = sum(audio_file.metadata.size for audio_file in audio_files)
            total_downloaded_bytes = 0

            for i, audio_file in enumerate(audio_files):
                # Check for cancellation before starting each file download
                if self.step != Step.DOWNLOADING:
                    logger.info("Download was cancelled, stopping file downloads")
                    return None

                audio_file_path = os.path.join(self.temp_dir, audio_file.metadata.relPath)
                os.makedirs(os.path.dirname(audio_file_path), exist_ok=True)
                audio_file_paths.append(audio_file_path)

                def download_progress(
                    downloaded_current: int,
                    total_current: int,
                    file_index=i,
                    files_completed=completed_files,
                    total_downloaded_so_far=total_downloaded_bytes,
                    file_name=audio_file.metadata.relPath,
                ):
                    # Check for cancellation during download progress updates
                    if self.step != Step.DOWNLOADING:
                        return  # Don't update progress if cancelled

                    if total_current > 0:
                        # Calculate overall downloaded bytes across all files
                        overall_downloaded = total_downloaded_so_far + downloaded_current
                        overall_percent = (
                            (overall_downloaded / total_bytes_all_files) * 100 if total_bytes_all_files > 0 else 0
                        )

                        speed_bps = getattr(download_progress, "speed", 0)

                        self._notify_progress(
                            Step.DOWNLOADING,
                            overall_percent,
                            f"Downloading file {file_index + 1}/{len(audio_files)} - {overall_downloaded / 1024 / 1024:.1f} MB of {total_bytes_all_files / 1024 / 1024:.1f} MB",
                            {
                                "bytes_downloaded": overall_downloaded,
                                "total_bytes": total_bytes_all_files,
                                "current_file": file_index + 1,
                                "total_files": len(audio_files),
                                "current_file_progress": (downloaded_current / total_current) * 100,
                                "files_completed": files_completed,
                                "speed_bps": speed_bps,
                                "feed_text": f"Downloading {file_name}…",
                            },
                        )

                success = await abs_service.download_audio_file(
                    item_id,
                    audio_file.ino,
                    audio_file_path,
                    download_progress,
                    cancellation_check=lambda: self.step != Step.DOWNLOADING,
                )

                # Check for cancellation after each file download
                if self.step != Step.DOWNLOADING:
                    logger.info("Download was cancelled after downloading file, stopping")
                    return None

                if not success:
                    raise RuntimeError(f"Failed to download audio file {i + 1}")

                # Increment completed files counter and update total downloaded bytes
                completed_files += 1
                total_downloaded_bytes += audio_file.metadata.size

            self._notify_progress(Step.DOWNLOADING, 100, f"Downloaded {len(audio_files)} audio file(s)")
            return audio_file_paths

        except asyncio.CancelledError:
            logger.info("Download task was cancelled")
            return None
        except Exception as e:
            logger.error(f"Error during download: {e}")
            raise

    async def _scan_library_files(self, abs_service: "ABSService") -> None:
        """Scan book.libraryFiles and create Reference objects."""
        if not self.book or not self.book.libraryFiles:
            return

        _TITLE_STEMS = {"chapters", "titles", "chapter-titles"}

        for lib_file in self.book.libraryFiles:
            filename = lib_file.metadata.filename.lower()
            ext = lib_file.metadata.ext.lower()  # already includes leading dot, e.g. ".json"
            stem = filename[: -len(ext)] if filename.endswith(ext) else filename

            is_chapter_ref_candidate = (
                (ext == ".json" and filename == "chapters.json")
                or (ext == ".csv" and filename == "chapters.csv")
                or ext == ".cue"
            )
            is_title_ref_candidate = ext == ".epub" or (ext == ".txt" and stem in _TITLE_STEMS)

            if not is_chapter_ref_candidate and not is_title_ref_candidate:
                continue

            # Download to a temp file
            tmp_path = os.path.join(self.temp_dir, f"libfile_{lib_file.ino}{ext}")
            downloaded = await abs_service.download_file(self.book_id, lib_file.ino, tmp_path)
            if not downloaded:
                logger.warning(f"Failed to download library file: {lib_file.metadata.filename}")
                continue

            original_name = lib_file.metadata.filename
            try:
                if ext == ".json":
                    self.chapter_refs.append(
                        json_parser.parse(tmp_path, ref_name=original_name, duration=self.book_duration)
                    )
                elif ext == ".csv":
                    self.chapter_refs.append(
                        csv_parser.parse(tmp_path, ref_name=original_name, duration=self.book_duration)
                    )
                elif ext == ".cue":
                    self.chapter_refs.append(
                        cue_parser.parse(tmp_path, ref_name=original_name, duration=self.book_duration)
                    )
                elif ext == ".txt":
                    self.title_refs.append(text_parser.parse(tmp_path, ref_name=original_name))
                elif ext == ".epub":
                    self.title_refs.append(epub_parser.parse(tmp_path, ref_name=original_name))

            except ValueError as e:
                logger.warning(f"Failed to parse library file {original_name}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error parsing library file {original_name}: {e}", exc_info=True)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

        # Always add the CUSTOM title reference (singleton — only one allowed)
        self.title_refs.append(
            TitleReference(
                type=TitleRefType.CUSTOM,
                name="Custom Titles",
                short_name="Custom",
                description="Manually entered list of chapter titles",
                titles=[],
            )
        )

    async def fetch_item(self, item_id: str) -> Dict[str, Any]:
        """Fetch the audiobook info and files for processing"""

        # Store the item_id for later use
        self.item_id = item_id

        try:
            # Step 1: Validate item and download
            self._notify_progress(Step.VALIDATING, 0, "Starting validation…")

            async with ABSService() as abs_service:
                # Health check
                if not await abs_service.health_check():
                    raise RuntimeError("Unable to connect to Audiobookshelf server")

                self._notify_progress(Step.VALIDATING, 0, "Fetching book details…")

                # Get book details
                book = await abs_service.get_book_details(item_id)
                if not book:
                    raise RuntimeError("Book not found or inaccessible")

                self.book = book

                # Validate audio files - support common audio formats
                supported_mime_types = [
                    "audio/mp4",  # M4B files
                    "audio/mpeg",  # MP3 files
                    "audio/flac",  # FLAC files
                    "audio/wav",  # WAV files
                    "audio/aac",  # AAC files
                    "audio/ogg",  # OGG files
                    "audio/x-flac",  # Alternative FLAC MIME type
                    "audio/x-wav",  # Alternative WAV MIME type
                ]

                audio_files = [f for f in book.media.audioFiles if f.mimeType in supported_mime_types]

                if len(audio_files) == 0:
                    available_types = [f.mimeType for f in book.media.audioFiles]
                    raise RuntimeError(
                        f"Book must have at least one supported audio file. Found {len(audio_files)} supported files. Available MIME types: {available_types}"
                    )

                self._notify_progress(Step.VALIDATING, 0, "Checking Chapter References…")

                # Check for existing Audiobookshelf chapters
                if book.media.chapters:
                    abs_chapters: List[BasicChapter] = []
                    for chapter in book.media.chapters:
                        abs_chapters.append(
                            BasicChapter(
                                timestamp=chapter.start,
                                title=chapter.title,
                            )
                        )
                    if abs_chapters:
                        self.chapter_refs.append(
                            ChapterReference(
                                type=ChapterRefType.ABS,
                                name="Audiobookshelf Chapters",
                                short_name="ABS",
                                description="Uses the existing Audiobookshelf chapter data for this book",
                                chapters=abs_chapters,
                                duration=book.duration,
                            )
                        )

                # Check for existing embedded chapters
                if audio_files:
                    embedded_chapters: List[BasicChapter] = []
                    for audio_file in audio_files:
                        if audio_file.chapters:
                            for chapter in audio_file.chapters:
                                embedded_chapters.append(
                                    BasicChapter(
                                        timestamp=chapter.start,
                                        title=chapter.title,
                                    )
                                )
                    if embedded_chapters:
                        self.chapter_refs.append(
                            ChapterReference(
                                type=ChapterRefType.EMBEDDED,
                                name="Embedded Chapters",
                                short_name="Embedded",
                                description="Uses data from the book's embedded chapters",
                                chapters=embedded_chapters,
                                duration=book.duration,
                            )
                        )

                # Check for existing Audnexus chapters
                audnexus_chapter_data = None
                if book.media.metadata.asin:
                    audnexus_chapter_data = await abs_service.find_audnexus_chapters(book)
                if audnexus_chapter_data:
                    audnexus_chapters: List[BasicChapter] = []
                    for chapter in audnexus_chapter_data.chapters:
                        audnexus_chapters.append(
                            BasicChapter(
                                timestamp=chapter.startOffsetMs / 1000,
                                title=chapter.title,
                            )
                        )
                    if audnexus_chapters:
                        audnexus_duration_sec = float(audnexus_chapter_data.runtimeLengthMs) / 1000
                        audnexus_meta: Dict[str, str] = {
                            "ASIN": book.media.metadata.asin or "",
                            "Duration": f"{int(audnexus_duration_sec // 60)}m",
                        }
                        self.chapter_refs.append(
                            ChapterReference(
                                type=ChapterRefType.AUDNEXUS,
                                name="Audnexus Chapters",
                                short_name="Audnexus",
                                description="Uses the Audnexus chapter data associated with the ASIN assigned to this book",
                                metadata=audnexus_meta,
                                chapters=audnexus_chapters,
                                duration=audnexus_duration_sec,
                            )
                        )

                # Check for file data
                if audio_files and len(audio_files) > 1:
                    file_data_chapters: List[BasicChapter] = []
                    current_start = 0.0
                    for audio_file in audio_files:
                        file_data_chapters.append(
                            BasicChapter(
                                timestamp=current_start,
                                title=audio_file.metadata.filename,
                            )
                        )
                        current_start += audio_file.duration
                    if file_data_chapters:
                        self.chapter_refs.append(
                            ChapterReference(
                                type=ChapterRefType.FILE_DATA,
                                name="Audio File Info",
                                short_name="Files",
                                description="Uses the audiobook file names and start times as chapter data",
                                chapters=file_data_chapters,
                                duration=book.duration,
                            )
                        )

                # Scan library files for additional references
                await self._scan_library_files(abs_service)

                self._notify_progress(Step.VALIDATING, 0, "Validation complete")

                # Step 2: Download audio files
                self._notify_progress(
                    Step.DOWNLOADING,
                    0,
                    f"Starting download of {len(audio_files)} audio file(s)…",
                )

                # Create download task for proper cancellation handling
                self._download_task = asyncio.create_task(self._download_audio_files(abs_service, item_id, audio_files))
                audio_file_paths = await self._download_task
                self._download_task = None

                # Check if download was cancelled
                if audio_file_paths is None or self.step not in [Step.DOWNLOADING, Step.FILE_PREP]:
                    logger.info("Download was cancelled, stopping fetch process")
                    return {"success": False, "message": "Download was cancelled"}

                first_original_file = audio_file_paths[0]

                # Get file durations and start positions for multi-file processing
                if len(audio_files) > 1:
                    file_durations, self.file_starts = await self._get_file_durations_and_starts(audio_files)
                else:
                    self.audio_file_path = audio_file_paths[0]
                    self.file_starts = None

                self._notify_progress(Step.DOWNLOADING, 100, f"Downloaded {len(audio_files)} audio file(s)")

                # Capture audio info from first original file
                codec, ffmpeg_output, uses_xhe_aac = await asyncio.get_event_loop().run_in_executor(
                    None, probe_audio_info, first_original_file
                )
                self.audio_info = AudioInfo(
                    codec=codec,
                    container=audio_files[0].metadata.ext.lower().lstrip(".") if audio_files else None,
                    ffmpeg_output=ffmpeg_output,
                )
                if uses_xhe_aac:
                    logger.warning(
                        f"Audio file uses xHE-AAC codec which is not currently supported: {first_original_file}"
                    )
                    self.audio_unsupported_codec = True

                # Concat multi-file audio if needed
                if len(audio_file_paths) > 1:
                    self._notify_progress(Step.FILE_PREP, 0, "Preparing files…")

                    # Store original count before concatenation
                    original_file_count = len(audio_file_paths)

                    total_duration = sum(file_durations) if file_durations else None

                    audio_service = AudioProcessingService(
                        self._notify_progress, self._running_processes, process_lock=self._process_lock
                    )
                    concatenated_file = await audio_service.concat_files(audio_file_paths, total_duration)

                    if not concatenated_file or not os.path.exists(concatenated_file):
                        error_msg = "Failed to merge audio files for processing. This may be due to incompatible audio formats, corrupted files, or insufficient disk space. Please check the application logs for detailed error information."
                        raise RuntimeError(error_msg)

                    # Delete original audio files
                    for audio_file in audio_file_paths:
                        try:
                            if os.path.exists(audio_file):
                                os.remove(audio_file)
                        except Exception as e:
                            logger.warning(f"Failed to delete original audio file {audio_file}: {e}")

                    self.audio_file_path = concatenated_file

                    logger.info(f"Successfully concatenated {original_file_count} files into: {concatenated_file}")

                if self.audio_file_path:
                    # Probe once for a compatible segment extension
                    self.segment_extension = await asyncio.get_event_loop().run_in_executor(
                        None, probe_segment_extension, self.audio_file_path, self.temp_dir
                    )

                self.step = Step.SELECT_WORKFLOW

            return {
                "success": True,
                "step": Step.SELECT_WORKFLOW,
            }

        except Exception as e:
            logger.error(f"Fetching item failed: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.IDLE, f"Fetching item failed: {str(e)}")
            raise

    async def start_workflow(self, workflow: str, ref_id: Optional[str] = None, dramatized: Optional[bool] = False):
        """Run the user-selected workflow."""

        try:
            if workflow == "quick_edit":
                if not ref_id:
                    raise ValueError("Reference ID is required for quick edit workflow")
                await self._quick_edit(ref_id)

            elif workflow == "smart_detect":
                if dramatized:
                    await self._detect_cues_vad()
                else:
                    await self._detect_cues()

            elif workflow == "regenerate":
                if not ref_id:
                    raise ValueError("Reference ID is required for regenerate titles workflow")

                chapter_ref = next((src for src in self.chapter_refs if src.id == ref_id), None)
                if not chapter_ref:
                    raise ValueError(f"Invalid Chapter Reference: {ref_id}")

                self.cues = self._filter_cues_by_duration([c.timestamp for c in chapter_ref.chapters])
                self._notify_progress(Step.CONFIGURE_ASR, 0, "Ready for transcription configuration")

            elif workflow == "realign":
                if not ref_id:
                    raise ValueError("Reference ID is required for realign workflow")
                await self.realign_chapters(ref_id, dramatized=dramatized or False)

            else:
                raise ValueError(f"Invalid workflow: {workflow}")

        except Exception as e:
            logger.error(f"Failed to start workflow: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.SELECT_WORKFLOW, f"Processing failed: {str(e)}")
            raise

    async def _quick_edit(self, ref_id: str):
        """Skip all processing and load chapters directly into the editor"""
        chapter_ref = next((src for src in self.chapter_refs if src.id == ref_id), None)

        if not chapter_ref:
            raise ValueError(f"Invalid quick edit Reference: {ref_id}")

        self.is_quick_edit = True
        self.chapters = []

        for ref_chapter in chapter_ref.chapters:
            self.chapters.append(
                ChapterData(
                    timestamp=ref_chapter.timestamp,
                    title=ref_chapter.title,
                )
            )

        logger.info(f"Quick edit: loaded {len(self.chapters)} chapters from {chapter_ref.short_name}")
        self._notify_progress(Step.CHAPTER_EDITING, 0)

    async def realign_chapters(self, ref_id: str, dramatized: bool = False):
        """Realign chapter timestamps from the user-selected reference"""

        try:
            chapter_ref = next((src for src in self.chapter_refs if src.id == ref_id), None)

            if not chapter_ref:
                raise ValueError(f"Invalid realignment Reference: {ref_id}")

            self.is_realignment = True

            self._notify_progress(
                Step.AUDIO_EXTRACTION,
                0,
                "Calculating audio extraction targets…",
            )

            padding: float = max(30, abs(self.book_duration - chapter_ref.duration) * 1.5)

            raw_segments = []
            for chapter in chapter_ref.chapters:
                start = max(0, chapter.timestamp - padding)
                end = min(self.book_duration, chapter.timestamp + padding)

                if start > self.book_duration:
                    continue

                raw_segments.append((start, end))

            segment_times: List[Tuple[float, float]] = []

            if raw_segments:
                raw_segments.sort(key=lambda x: x[0])
                current_start, current_end = raw_segments[0]

                for next_start, next_end in raw_segments[1:]:
                    if next_start <= current_end:
                        current_end = max(current_end, next_end)
                    else:
                        segment_times.append((current_start, current_end))
                        current_start, current_end = next_start, next_end

                segment_times.append((current_start, current_end))

            self._extraction_task = asyncio.create_task(self._extract_realignment_segments(segment_times))
            await self._extraction_task

            if self.segment_files is None or self.step != Step.AUDIO_EXTRACTION:
                # Extraction was canceled
                return

            if len(self.segment_files) != len(segment_times):
                raise RuntimeError("Mismatch between extracted segments and expected segments for realignment")

            segment_starts, _ = zip(*segment_times)
            segments = list(zip(segment_starts, self.segment_files))

            if dramatized:
                await self._detect_realignment_cues_vad(segments)
            else:
                await self._detect_realignment_cues(segments)

            if self.detected_cues is None or self.step not in [Step.AUDIO_ANALYSIS, Step.VAD_ANALYSIS]:
                # Detection was canceled
                return

            await self._realign_chapters(chapter_ref, padding)

        except Exception as e:
            logger.error(f"Failed to align chapters: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.SELECT_WORKFLOW, f"Processing failed: {str(e)}")
            raise

    async def _realign_chapters(self, ref: ChapterReference, ransac_threshold: float):
        """Realign chapters using the detected silences and the reference chapters"""
        self._notify_progress(Step.AUDIO_ANALYSIS, 100, "Aligning chapters…")

        try:
            aligner = ChapterAligner(
                ransac_threshold=ransac_threshold,
            )

            aligned_chapters, _ = aligner.align(
                ref.chapters.copy(),
                self.detected_cues.copy() if self.detected_cues else [],
                ref.duration,
                self.book_duration,
            )

            new_chapters = []
            for i, ch in enumerate(aligned_chapters):
                timestamp = ch["timestamp"]
                confidence = ch["confidence"]
                is_guess = ch["is_guess"]

                if i == 0:
                    timestamp = 0.0
                    confidence = 1.0
                    is_guess = False

                original_chapter = ref.chapters[i]

                chapter_data = ChapterData(
                    timestamp=timestamp,
                    title=ch["title"],
                    realignment=RealignmentData(
                        original_timestamp=original_chapter.timestamp,
                        confidence=confidence,
                        is_guess=is_guess,
                    ),
                )
                new_chapters.append(chapter_data)

            self.chapters = new_chapters

            self._notify_progress(Step.CHAPTER_EDITING, 0, f"Realigned {len(self.chapters)} chapters")

        except Exception as e:
            logger.error(f"Error during chapter alignment: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.SELECT_WORKFLOW, f"Alignment failed: {str(e)}")
            raise

    @staticmethod
    def _format_duration_difference(diff_percent: float, diff_seconds: float) -> str:
        """Format duration difference for display"""
        hours = int(diff_seconds // 3600)
        minutes = int((diff_seconds % 3600) // 60)
        seconds = int(diff_seconds % 60)

        if hours > 0:
            duration_str = f"{hours}h {minutes}m {seconds}s"
        else:
            duration_str = f"{minutes}m {seconds}s"

        return f"{diff_percent:.1f}% ({duration_str})"

    async def _detect_cues(self):
        """Detect chapter breaks and generate cues for user selection"""

        self.ai_options.deselectNonChapters = True

        # Initialize services
        audio_service = AudioProcessingService(
            self._scoped_progress_callback(), self._running_processes, process_lock=self._process_lock
        )

        self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Analyzing audio…")

        # Detect silences
        silences = await audio_service.get_silence_boundaries(
            self.audio_file_path,
            duration=self.book_duration,
        )

        # Check if processing was cancelled (None return indicates cancellation)
        # If the step was changed during processing, we should not continue
        if silences is None or self.step != Step.AUDIO_ANALYSIS:
            logger.info("Processing was cancelled during audio analysis, stopping cue detection")
            return

        self._notify_progress(Step.AUDIO_ANALYSIS, -1, "Processing results…")

        self.detected_cues = self._silences_to_cues(silences)
        self.normal_scanned_regions = [(0.0, self.book_duration)]

        await self._transition_to_initial_chapter_selection()

    async def _detect_cues_vad(self):
        """Detect potential chapter boundaries using VAD (Voice Activity Detection)."""
        try:
            self.ai_options.deselectNonChapters = True

            self._notify_progress(Step.VAD_PREP, 0, "Preparing files…")

            service = VadDetectionService(
                progress_callback=self._notify_progress,
                running_processes=self._running_processes,
                tmp_dir=self.temp_dir,
            )

            # Create VAD task for proper cancellation handling
            self._vad_task = asyncio.create_task(
                service.get_vad_silence_boundaries(self.audio_file_path, self.book_duration, self.segment_extension)
            )
            silences = await self._vad_task
            self._vad_task = None

            # Check if processing was cancelled (None return indicates cancellation)
            if silences is None or self.step not in [Step.VAD_PREP, Step.VAD_ANALYSIS]:
                logger.info("Processing was cancelled during VAD analysis, stopping cue detection")
                return

            self.detected_cues = self._silences_to_cues(silences)
            self.vad_scanned_regions = [(0.0, self.book_duration)]

            await self._transition_to_initial_chapter_selection()

        except asyncio.CancelledError:
            logger.info("VAD detection was cancelled")
            self._vad_task = None
            raise
        except Exception as e:
            logger.error(f"VAD detection failed: {e}", exc_info=True)
            self._vad_task = None
            raise ProcessingError(f"VAD detection failed: {str(e)}")

    async def _detect_realignment_cues(self, segments: List[Tuple[float, str]]):
        """Detect chapter cues for realignment by running silence detection on
        each extracted segment file in parallel, bounded by the worker pool."""

        audio_service = AudioProcessingService(
            self._scoped_progress_callback(),
            self._running_processes,
            process_lock=self._process_lock,
        )

        self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Analyzing audio…")

        total = len(segments)
        if total == 0:
            self.detected_cues = []
            return

        semaphore = asyncio.Semaphore(max(1, min(get_worker_count(), total)))
        completed = 0
        progress_lock = asyncio.Lock()

        async def analyze_one(
            segment_start: float,
            segment_file: str,
        ) -> List[Tuple[float, float]]:
            nonlocal completed
            async with semaphore:
                segment_silences = await audio_service.get_silence_boundaries(
                    segment_file,
                    publish_progress=False,
                )
            async with progress_lock:
                completed += 1
                pct = completed / total * 100
                self._notify_progress(
                    Step.AUDIO_ANALYSIS,
                    pct,
                    "Performing focused audio analysis…",
                )
            if not segment_silences:
                return []
            return [(s + segment_start, e + segment_start) for s, e in segment_silences]

        per_segment = await asyncio.gather(*(analyze_one(start, path) for start, path in segments))

        if self.step != Step.AUDIO_ANALYSIS:
            logger.info("Processing was cancelled during audio analysis, stopping cue detection")
            return

        silences: List[Tuple[float, float]] = []
        for result in per_segment:
            silences.extend(result)
        silences.sort(key=lambda s: s[0])

        self.detected_cues = self._silences_to_cues(silences)

    async def _detect_realignment_cues_vad(self, segments: List[Tuple[float, str]]):
        """Detect potential chapter boundaries using VAD (Voice Activity Detection)."""
        try:
            self._notify_progress(Step.VAD_ANALYSIS, 0, "Preparing to analyze files…")

            service = VadDetectionService(
                progress_callback=self._notify_progress,
                running_processes=self._running_processes,
                tmp_dir=self.temp_dir,
            )

            self._vad_task = asyncio.create_task(
                service.get_vad_silence_boundaries_from_segments(
                    segments, duration=self.book_duration if self.book else None
                )
            )
            silences = await self._vad_task
            self._vad_task = None

            if silences is None or self.step not in [Step.VAD_PREP, Step.VAD_ANALYSIS]:
                logger.info("Processing was cancelled during VAD analysis, stopping cue detection")
                return

            self.detected_cues = self._silences_to_cues(silences)

        except asyncio.CancelledError:
            logger.info("VAD detection was cancelled")
            self._vad_task = None
            raise
        except Exception as e:
            logger.error(f"VAD detection failed: {e}", exc_info=True)
            self._vad_task = None
            await self.restart_at_step(RestartStep.SELECT_WORKFLOW, f"VAD detection failed: {str(e)}")
            raise ProcessingError(f"Error during VAD detection: {str(e)}")

    async def _transition_to_initial_chapter_selection(self):
        """Transition to the initial chapter selection step after silence detection is complete"""
        self.initial_chapter_selection_available = True
        self._notify_progress(
            Step.INITIAL_CHAPTER_SELECTION, 100, f"Ready for selection with {len(self.detected_cues)} detected cues"
        )
        logger.info(f"Detected {len(self.detected_cues)} cues, ready for initial chapter selection")

    async def _extract_audio_segments(self, preassigned_titles: Optional[Dict[int, str]] = None):
        """Extract audio segments for transcription, skipping cues with preassigned titles"""

        self._notify_progress(Step.AUDIO_EXTRACTION, 0, "Extracting chapter audio segments…")

        preassigned = preassigned_titles or {}
        timestamps_to_extract = [ts for i, ts in enumerate(self.cues) if i not in preassigned]

        audio_service = AudioProcessingService(
            self._scoped_progress_callback(),
            self._running_processes,
            asr_buffer=get_asr_buffer(),
            process_lock=self._process_lock,
        )

        extracted = await audio_service.extract_segments(
            audio_file=self.audio_file_path,
            timestamps=timestamps_to_extract,
            output_dir=self.temp_dir,
            segment_extension=self.segment_extension,
        )

        # Check if extraction was cancelled (None return indicates cancellation)
        # If the step was changed during processing, we should not continue
        if extracted is None or self.step != Step.AUDIO_EXTRACTION:
            logger.info("Processing was cancelled during audio extraction, stopping extraction")
            return

        self.segment_files = extracted

        self._notify_progress(Step.AUDIO_EXTRACTION, 100, f"Extracted {len(self.segment_files)} chapter segments")

        logger.info(f"Extracted {len(self.segment_files)} segments")

    async def _extract_realignment_segments(self, segment_times: List[Tuple[float, float]]):
        """Extract audio segments for realignment detection"""

        self._notify_progress(Step.AUDIO_EXTRACTION, 0, "Performing targeted audio extraction…")

        audio_service = AudioProcessingService(
            self._scoped_progress_callback(), self._running_processes, process_lock=self._process_lock
        )

        extracted = await audio_service.extract_segments(
            audio_file=self.audio_file_path,
            timestamps=segment_times,
            output_dir=self.temp_dir,
            segment_extension=self.segment_extension,
        )

        if extracted is None or self.step != Step.AUDIO_EXTRACTION:
            logger.info("Processing was cancelled during audio extraction, stopping extraction")
            return

        self.segment_files = extracted

        self._notify_progress(Step.AUDIO_EXTRACTION, 100, f"Extracted {len(self.segment_files)} target segments")

        logger.info(f"Extracted {len(self.segment_files)} target segments")

    async def _create_trimmed_segments(self):
        """Create trimmed segments for transcription based on ASR options"""
        try:
            app_config = get_app_config()
            copy_only = not app_config.asr_options.trim

            audio_service = AudioProcessingService(
                self._scoped_progress_callback(),
                self._running_processes,
                asr_buffer=get_asr_buffer(),
                process_lock=self._process_lock,
            )

            # Create trimmed segments from original segments
            self._trimming_task = asyncio.create_task(audio_service.trim_segments(self.segment_files, copy_only))
            trimmed_files = await self._trimming_task
            self._trimming_task = None

            # Store the trimmed segments for transcription
            self.trimmed_segment_files = trimmed_files

            logger.info(f"Created {len(trimmed_files)} trimmed segments, copy_only={copy_only}")

        except asyncio.CancelledError:
            logger.info("Trimming was cancelled")
            self._trimming_task = None
            raise
        except Exception as e:
            logger.error(f"Failed to create trimmed segments: {e}", exc_info=True)
            self._trimming_task = None
            await self.restart_at_step(RestartStep.CONFIGURE_ASR, f"Failed to create trimmed segments: {str(e)}")
            raise

    async def _transcribe_segments(self) -> List[str]:
        """Transcribe audio segments using ASR"""

        self._notify_progress(
            Step.ASR_PROCESSING,
            -1,
            "Initializing. This may take a while the first time…",
        )

        # Get or create the warm ASR service
        asr_service = await get_app_state().get_or_create_asr_service(progress_callback=self._notify_progress)

        # Run transcription
        self._transcription_task = asyncio.create_task(asr_service.transcribe(self.trimmed_segment_files))
        transcripts = await self._transcription_task
        self._transcription_task = None

        # Check if processing was cancelled during transcription
        if self.step != Step.ASR_PROCESSING:
            logger.info("Processing was cancelled during transcription, stopping transcription")
            return transcripts

        self._notify_progress(Step.ASR_PROCESSING, 100, "Transcription complete")

        logger.info(f"Transcribed {len(transcripts)} segments")

        return transcripts

    async def _create_initial_chapters(
        self,
        transcripts: List[str],
        preassigned_titles: Optional[Dict[int, str]] = None,
    ):
        """Create initial chapter objects with basic titles (without AI cleanup)"""

        # Check if processing was cancelled before creating chapters
        if self.step != Step.ASR_PROCESSING:
            logger.info("Processing was cancelled before creating chapters, stopping chapter creation")
            return

        self._notify_progress(Step.CHAPTER_EDITING, 0, "Creating initial chapters…")

        preassigned = preassigned_titles or {}
        # Map each cue index to its position in ``transcripts`` (skipping preassigned cues)
        transcript_indices = {i: k for k, i in enumerate(i for i in range(len(self.cues)) if i not in preassigned)}

        self.chapters = []
        # Create chapter objects with basic titles
        for i, timestamp in enumerate(self.cues):
            if i in preassigned:
                transcript = ""
                title = preassigned[i]
            else:
                k = transcript_indices.get(i)
                if k is not None and k < len(transcripts) and transcripts[k].strip():
                    # Use full transcription as basic title
                    transcript = transcripts[k].strip()
                    title = transcript
                else:
                    # Fallback to empty string
                    transcript = ""
                    title = ""

            chapter = ChapterData(
                timestamp=timestamp,
                transcript=transcript,
                title=title,
            )
            self.chapters.append(chapter)

        self.step = Step.CHAPTER_EDITING

        self._notify_progress(
            Step.CHAPTER_EDITING,
            100,
            f"Created {len(self.chapters)} initial chapters",
        )

        logger.info(f"Created {len(self.chapters)} initial chapters")

    async def proceed_with_transcription(self, preassigned_titles: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
        """Proceed with extraction, trimming and transcription from CONFIGURE_ASR step.

        Cues whose index appears in ``preassigned_titles`` skip extraction/transcription and
        inherit the supplied title directly. If every cue is preassigned, this short-circuits
        to ``skip_transcription`` since there is nothing to transcribe.
        """
        preassigned = preassigned_titles or {}
        try:
            # When every cue has a preassigned title there is nothing to transcribe;
            # fall through to skip_transcription which applies titles directly.
            if preassigned and len(preassigned) >= len(self.cues):
                return await self.skip_transcription(preassigned_titles=preassigned)

            # First extract audio segments with the model-appropriate buffer
            await self.extract_segments(preassigned_titles=preassigned)

            # Check if extraction was cancelled
            if self.segment_files is None or self.step != Step.AUDIO_EXTRACTION:
                logger.info("Processing was cancelled during segment extraction")
                return {"success": False, "message": "Processing was cancelled"}

            # Then create trimmed segments for transcription
            await self._create_trimmed_segments()

            # Then transcribe the trimmed segments
            transcripts = await self._transcribe_segments()

            # Check if transcription was cancelled
            if self.step != Step.ASR_PROCESSING:
                logger.info("Processing was cancelled during transcription")
                return {"success": False, "message": "Processing was cancelled"}

            # Create initial chapters
            await self._create_initial_chapters(transcripts, preassigned_titles=preassigned)

            # Check if chapter creation was cancelled
            if self.step != Step.CHAPTER_EDITING:
                logger.info("Processing was cancelled during chapter creation")
                return {"success": False, "message": "Processing was cancelled"}

            return {
                "success": True,
                "book": self.book,
                "chapters": self.chapters,
                "segment_files": self.segment_files,
                "step": Step.CHAPTER_EDITING,
                "message": "Chapter extraction and transcription complete",
            }
        except asyncio.CancelledError:
            logger.info("Processing was cancelled during transcription")
            await self.restart_at_step(RestartStep.CONFIGURE_ASR)
            return {"success": False, "message": "Processing was cancelled"}
        except Exception as e:
            logger.error(f"Failed to proceed with transcription: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CONFIGURE_ASR, f"Transcription failed: {str(e)}")
            raise

    async def skip_transcription(self, preassigned_titles: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
        """Skip transcription and create chapters with timestamps only.

        If ``preassigned_titles`` is supplied, those titles are applied directly to the matching
        cue indices instead of leaving them empty.
        """
        try:
            preassigned = preassigned_titles or {}

            self.chapters = []
            # Create chapter objects, using any preassigned titles
            for i, timestamp in enumerate(self.cues):
                title = preassigned.get(i, "")
                chapter = ChapterData(timestamp=timestamp, title=title)
                self.chapters.append(chapter)

            # self.step = Step.CHAPTER_EDITING
            self._notify_progress(Step.CHAPTER_EDITING, 0)

            logger.info(f"Skipped transcription, created {len(self.chapters)} chapters")

            return {
                "success": True,
                "book": self.book,
                "chapters": self.chapters,
                "segment_files": [],
                "step": Step.CHAPTER_EDITING,
                "message": "Chapters created without transcription",
            }

        except Exception as e:
            logger.error(f"Failed to skip transcription: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CONFIGURE_ASR, f"Failed to create chapters: {str(e)}")
            raise

    async def extract_segments(self, preassigned_titles: Optional[Dict[int, str]] = None) -> None:
        """Extract initial audio segments after CONFIGURE_ASR step"""
        try:
            # Clean up any stale segments from a previous run before re-extracting
            self.cleanup_segment_files()
            await self._extract_audio_segments(preassigned_titles=preassigned_titles)

            # Check if extraction was cancelled
            if self.segment_files is None or self.step != Step.AUDIO_EXTRACTION:
                logger.info("Processing was cancelled during segment extraction")
                return

            logger.info(f"Extracted {len(self.segment_files)} segments")

        except Exception as e:
            logger.error(f"Segment extraction failed: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CONFIGURE_ASR, f"Extraction failed: {str(e)}")
            raise

    def _deduplicate_timestamps(
        self,
        timestamps: List[float],
        tolerance: float,
        priority_timestamps: Optional[List[float]] = None,
    ) -> List[float]:
        """Remove timestamps that are within tolerance of each other, prioritizing certain timestamps"""
        if not timestamps:
            return []

        # If no priority timestamps specified, use the original simple approach
        if priority_timestamps is None:
            sorted_timestamps = sorted(timestamps)
            deduplicated = [sorted_timestamps[0]]

            for timestamp in sorted_timestamps[1:]:
                is_duplicate = any(abs(timestamp - existing) <= tolerance for existing in deduplicated)
                if not is_duplicate:
                    deduplicated.append(timestamp)

            logger.debug(
                f"Deduplicated {len(timestamps)} timestamps down to {len(deduplicated)} (tolerance: {tolerance}s)"
            )
            return deduplicated

        # Start with priority timestamps (these are kept regardless)
        deduplicated = sorted(priority_timestamps)

        # Add non-priority timestamps that don't conflict
        non_priority = [ts for ts in timestamps if ts not in priority_timestamps]
        added_count = 0

        for timestamp in sorted(non_priority):
            # Check if this timestamp is too close to any existing timestamp
            is_duplicate = any(abs(timestamp - existing) <= tolerance for existing in deduplicated)

            if not is_duplicate:
                deduplicated.append(timestamp)
                added_count += 1

        # Sort the final result
        deduplicated.sort()

        logger.debug(
            f"Deduplicated {len(timestamps)} timestamps down to {len(deduplicated)} (tolerance: {tolerance}s), added {added_count} non-priority timestamps"
        )
        return deduplicated

    def _merge_unaligned_timestamps(
        self,
        selected_timestamps: List[float],
        chapter_refs: List[ChapterReference],
        include_unaligned: List[str],
    ) -> List[float]:
        """Merge unaligned timestamps from existing chapter sets with selected timestamps"""
        if not include_unaligned or not chapter_refs:
            return selected_timestamps

        all_unaligned_timestamps = []
        tolerance = 5.0

        for ref_id in include_unaligned:
            chapter_ref = self._get_chapter_ref(ref_id)
            if not chapter_ref:
                logger.warning(f"No Chapter Reference found for include_unaligned: {ref_id}")
                continue

            existing_timestamps = [c.timestamp for c in chapter_ref.chapters]

            # Find unaligned timestamps for this chapter set
            unaligned_timestamps = []
            for existing_timestamp in existing_timestamps:
                is_aligned = any(
                    abs(existing_timestamp - selected_timestamp) <= tolerance
                    for selected_timestamp in selected_timestamps
                )

                if not is_aligned:
                    unaligned_timestamps.append(existing_timestamp)

            all_unaligned_timestamps.extend(unaligned_timestamps)
            logger.info(f"Found {len(unaligned_timestamps)} unaligned timestamps from {ref_id} chapters")

        # Merge all timestamps and remove near-duplicates within tolerance
        all_timestamps = selected_timestamps + all_unaligned_timestamps
        deduplicated_timestamps = self._deduplicate_timestamps(all_timestamps, tolerance, selected_timestamps)

        logger.info(
            f"Merged {len(all_unaligned_timestamps)} total unaligned timestamps from {include_unaligned} chapter sets. "
            f"Total timestamps: {len(deduplicated_timestamps)} (was {len(selected_timestamps)}) after deduplication"
        )

        return deduplicated_timestamps

    async def select_initial_chapters(
        self, timestamps: List[float], include_unaligned: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Select initial chapters from detected cues and proceed to CONFIGURE_ASR"""
        try:
            # Set the selected cues directly from provided timestamps
            self.cues = sorted(timestamps)

            # Add unaligned chapters if specified
            if include_unaligned:
                self.cues = self._merge_unaligned_timestamps(
                    self.cues,
                    self.chapter_refs,
                    include_unaligned,
                )

            self.cues = self._filter_cues_by_duration(self.cues)

            logger.info(f"Selected {len(self.cues)} initial chapters")

            # Transition to CONFIGURE_ASR; extraction happens when user proceeds
            self._notify_progress(Step.CONFIGURE_ASR, 0, "Ready for transcription configuration")

            return {
                "success": True,
                "step": Step.CONFIGURE_ASR,
                "message": "Ready for transcription configuration",
            }

        except Exception as e:
            logger.error(f"Failed to select initial chapters: {e}", exc_info=True)
            await self.restart_at_step(
                RestartStep.INITIAL_CHAPTER_SELECTION, f"Initial chapter selection failed: {str(e)}"
            )
            raise

    async def submit_chapters(self, chapters: List[ChapterData]) -> bool:
        """Submit final chapters to Audiobookshelf"""

        # Convert chapters to the format expected by ABS
        chapter_data = []
        for chapter in chapters:
            if chapter.selected:  # Only submit selected chapters
                chapter_data.append((chapter.timestamp, chapter.title))

        try:
            async with ABSService() as abs_service:
                success = await abs_service.upload_chapters(
                    self.book_id,
                    chapter_data,
                    self.book_duration,
                )

                if success:
                    self._notify_progress(Step.COMPLETED, 100, "Chapter submission completed successfully")
                    # Update chapter search cache if this book is cached
                    try:
                        from .chapter_search.database import upsert_chapters_for_book
                        from .chapter_search.state import get_chapter_search_state

                        cached_chapters = [
                            {"title": title, "start_time": timestamp} for timestamp, title in chapter_data
                        ]
                        await upsert_chapters_for_book(self.book_id, cached_chapters)
                        await get_chapter_search_state().update_book_chapters(self.book_id, cached_chapters)
                    except Exception as cache_err:
                        logger.warning(f"Failed to update chapter search cache: {cache_err}")

                return success

        except Exception as e:
            logger.error(f"Chapter submission failed: {e}")
            return False

    async def process_selected_with_ai(self, ai_options=None) -> bool:
        """Process selected chapters with AI enhancement"""
        # Update AI options if provided
        if ai_options:
            self.ai_options = ai_options

        # Get selected chapters
        selected_chapters = [chapter for chapter in self.chapters if chapter.selected]
        if not selected_chapters:
            return False

        try:
            # Update step to AI cleanup
            self._notify_progress(Step.AI_CLEANUP, 0, "Starting AI cleanup…")

            # Process with AI using the new provider system
            from ..core.config import get_app_config
            from ..services.llm_providers.registry import create_provider

            # Create the AI provider using the registry system
            # The provider classes handle their own configuration via saved settings
            ai_provider = create_provider(self.ai_options.provider_id, self._notify_progress)
            if not ai_provider:
                raise ValueError(f"Failed to create provider {self.ai_options.provider_id}")

            # Pass current chapter titles to the AI as input
            titles = []
            for chapter in selected_chapters:
                titles.append(chapter.title)

            # Use AI options
            infer_opening_credits = self.ai_options.inferOpeningCredits
            infer_end_credits = self.ai_options.inferEndCredits
            deselect_non_chapters = self.ai_options.deselectNonChapters
            keep_deselected_titles = self.ai_options.keepDeselectedTitles
            additional_instructions = self.ai_options.additionalInstructions
            preferred_titles: Optional[List[str]] = None

            # Get preferred titles
            if self.ai_options.usePreferredTitles and self.ai_options.preferredTitlesRef:
                chapter_ref: Optional[ChapterReference] = next(
                    (s for s in self.chapter_refs if s.id == self.ai_options.preferredTitlesRef), None
                )
                if chapter_ref:
                    preferred_titles = [ch.title for ch in chapter_ref.chapters if ch.title]
                else:
                    title_ref: Optional[TitleReference] = next(
                        (s for s in self.title_refs if s.id == self.ai_options.preferredTitlesRef), None
                    )
                    if title_ref:
                        preferred_titles = [t for t in title_ref.titles if t]

            # Prepare additional instructions list
            instructions_list = []

            # Add checked custom instructions
            config = get_app_config()
            for instruction in config.custom_instructions.instructions:
                if instruction.checked and instruction.text.strip():
                    instructions_list.append(instruction.text.strip())

            # Add non-persistent additional_instructions at the end
            if additional_instructions.strip():
                instructions_list.append(additional_instructions.strip())

            # Use the main processing method with selected model
            try:
                processed_titles = await ai_provider.process_chapter_titles(
                    titles,
                    model_id=self.ai_options.model_id,
                    additional_instructions=instructions_list,
                    deselect_non_chapters=deselect_non_chapters,
                    infer_opening_credits=infer_opening_credits,
                    infer_end_credits=infer_end_credits,
                    preferred_titles=preferred_titles,
                    book=self.book,
                )
            except Exception as e:
                logger.error(f"AI cleanup failed, no changes made to chapters: {e}")
                raise

            deselected_count = 0

            if len(processed_titles) != len(selected_chapters):
                raise ValueError("An incorrect chapter count was returned. Please try again.")

            operations: list[AICleanupOperation] = []

            # Create AI cleanup operations for each chapter
            for i, chapter in enumerate(selected_chapters):
                if i < len(processed_titles):
                    new_title = processed_titles[i]

                    # Treat None, empty/whitespace, or the literal string "null" as an invalid title
                    if (
                        new_title is not None
                        and (stripped := str(new_title).strip()) != ""
                        and stripped.lower() != "null"
                    ):
                        operations.append(
                            AICleanupOperation(
                                chapter_id=chapter.id,
                                old_title=chapter.title,
                                new_title=new_title,
                            )
                        )
                    else:
                        operations.append(
                            AICleanupOperation(
                                chapter_id=chapter.id,
                                old_title=chapter.title,
                                new_title=chapter.title if keep_deselected_titles else "",
                                selected=False,
                            )
                        )

                        deselected_count += 1

            batch_operation = BatchChapterOperation(operations=operations)
            batch_operation.apply(self)
            self.add_to_history(batch_operation)

            # Update progress message to include deselection info
            if deselected_count > 0:
                logger.info(
                    f"AI cleanup deselected and cleared titles for {deselected_count} chapters with empty/None titles"
                )

            # Send final progress update
            completion_message = "AI cleanup complete"
            if deselected_count > 0:
                completion_message += f" ({deselected_count} chapters deselected and cleared due to empty titles)"

            self._notify_progress(
                Step.CHAPTER_EDITING,
                100,
                completion_message,
                {"deselected_count": deselected_count} if deselected_count > 0 else {},
            )

            logger.info("AI cleanup completed")
            return True

        except ValueError as e:
            error_msg = f"AI cleanup error: {str(e)}"
            logger.error(f"AI cleanup error: {e}")
            self.step = Step.CHAPTER_EDITING
            asyncio.create_task(get_app_state().broadcast_step_change(Step.CHAPTER_EDITING, error_message=error_msg))
            return False
        except Exception as e:
            provider_info = (
                f" (Provider: {self.ai_options.provider_id}, Model: {self.ai_options.model_id})"
                if self.ai_options.provider_id
                else ""
            )
            error_msg = f"AI cleanup failed{provider_info}: {str(e)}"
            logger.error(f"AI cleanup unexpected error: {e}", exc_info=True)
            self.step = Step.CHAPTER_EDITING
            asyncio.create_task(get_app_state().broadcast_step_change(Step.CHAPTER_EDITING, error_message=error_msg))
            return False

    def get_restart_options(self) -> List[str]:
        """Get available restart options for the current step"""
        from ..models.enums import RestartStep

        restart_options: List[RestartStep] = []

        match self.step:
            case Step.SELECT_WORKFLOW:
                restart_options.append(RestartStep.IDLE)
            case Step.INITIAL_CHAPTER_SELECTION:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_WORKFLOW)
            case Step.CONFIGURE_ASR:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_WORKFLOW)
                if self.initial_chapter_selection_available:
                    restart_options.append(RestartStep.INITIAL_CHAPTER_SELECTION)
            case Step.CHAPTER_EDITING:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_WORKFLOW)
                if self.initial_chapter_selection_available:
                    restart_options.append(RestartStep.INITIAL_CHAPTER_SELECTION)
                if not self.is_realignment and not self.is_quick_edit:
                    restart_options.append(RestartStep.CONFIGURE_ASR)
            case Step.REVIEWING | Step.COMPLETED:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_WORKFLOW)
                if self.initial_chapter_selection_available:
                    restart_options.append(RestartStep.INITIAL_CHAPTER_SELECTION)
                if not self.is_realignment and not self.is_quick_edit:
                    restart_options.append(RestartStep.CONFIGURE_ASR)
                restart_options.append(RestartStep.CHAPTER_EDITING)
            case _:
                pass

        restart_options.reverse()
        return [option.value for option in restart_options]

    # ─── Coverage tracking helpers ────────────────────────────────────────────

    @staticmethod
    def _merge_regions(regions: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Sort and merge overlapping/adjacent regions into a minimal covering list."""
        if not regions:
            return []
        sorted_regions = sorted(regions, key=lambda r: r[0])
        merged = [sorted_regions[0]]
        for start, end in sorted_regions[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def _is_region_covered(
        self,
        scanned: List[Tuple[float, float]],
        start: float,
        end: float,
        margin: float = 1.0,
    ) -> bool:
        """Return True if [start+margin, end-margin] is fully covered by scanned regions."""
        check_start = start + margin
        check_end = end - margin
        if check_start >= check_end:
            return True  # Region too small to meaningfully check

        merged = self._merge_regions(scanned)
        remaining_start = check_start
        for r_start, r_end in merged:
            if r_start <= remaining_start and r_end >= check_end:
                return True
            if r_start <= remaining_start:
                remaining_start = max(remaining_start, r_end)
            if remaining_start >= check_end:
                return True
        return False

    def _get_uncovered_subregions(
        self,
        scanned: List[Tuple[float, float]],
        start: float,
        end: float,
    ) -> List[Tuple[float, float]]:
        """Return portions of [start, end] not covered by scanned regions."""
        if not scanned:
            return [(start, end)]

        merged = self._merge_regions(scanned)
        uncovered = []
        current = start

        for r_start, r_end in merged:
            if r_start >= end:
                break
            if r_start > current:
                uncovered.append((current, min(r_start, end)))
            current = max(current, r_end)

        if current < end:
            uncovered.append((current, end))

        return uncovered

    # ─── Partial scanning ─────────────────────────────────────────────────────

    def _run_single_extraction(
        self,
        seg_start: float,
        seg_end: float,
        output_path: str,
    ) -> bool:
        """Extract a single contiguous audio range using stream copy. Returns True on success."""
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(seg_start),
            "-to",
            str(seg_end),
            "-i",
            self.audio_file_path,
            "-map",
            "0:a:0",
            "-c",
            "copy",
            output_path,
        ]
        # Use subprocess.PIPE and process.communicate() to capture error output in memory
        # without risking pipe buffer deadlock.
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
        with self._process_lock:
            self._running_processes.append(process)
        try:
            _, stderr_data = process.communicate()
            if process.returncode != 0:
                error_output = stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
                logger.error(f"ffmpeg extraction failed: {' '.join(cmd)}\nOutput:\n{error_output}")
            return process.returncode == 0
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

    def _run_split_extraction(
        self,
        seg_start: float,
        seg_end: float,
        split_boundaries_global: List[float],
        output_pattern: str,
    ) -> bool:
        """
        Extract and split audio in a single ffmpeg pass using the segment muxer.
        split_boundaries_global are global timestamps within (seg_start, seg_end).
        Returns True on success.
        """
        # Convert global timestamps to stream-relative timestamps
        relative_boundaries = [b - seg_start for b in split_boundaries_global if seg_start < b < seg_end]
        if not relative_boundaries:
            return False

        segment_times_str = ",".join(str(b) for b in relative_boundaries)

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(seg_start),
            "-to",
            str(seg_end),
            "-i",
            self.audio_file_path,
            "-map",
            "0:a:0",
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_times",
            segment_times_str,
            output_pattern,
        ]
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
        with self._process_lock:
            self._running_processes.append(process)
        try:
            _, stderr_data = process.communicate()
            if process.returncode != 0:
                error_output = stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
                logger.error(f"ffmpeg split extraction failed: {' '.join(cmd)}\nOutput:\n{error_output}")
            return process.returncode == 0
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

    def _extract_segment_audio(
        self,
        seg_start: float,
        seg_end: float,
        large_scanned_in_seg: List[Tuple[float, float]],
        ext: str,
    ) -> List[Tuple[str, float, float]]:
        """
        Extract audio for a single extraction segment in a single ffmpeg pass.
        Splits around large already-scanned sub-regions if needed.

        Returns list of (file_path, global_start, duration) for unscanned sub-segments.
        All created temp files are added to self._partial_scan_temp_files.
        """
        import glob as glob_module

        seg_uid = uuid.uuid4().hex

        if not large_scanned_in_seg:
            # Simple single-file extraction
            out_path = os.path.join(self.temp_dir, f"partial_{seg_uid}.{ext}")
            success = self._run_single_extraction(seg_start, seg_end, out_path)
            if not success or not os.path.exists(out_path):
                raise ProcessingError(f"ffmpeg extraction failed for segment ({seg_start:.1f}, {seg_end:.1f})")
            self._partial_scan_temp_files.append(out_path)
            return [(out_path, seg_start, seg_end - seg_start)]

        # Build split boundaries from large scanned region edges
        split_boundaries = []
        for sr_start, sr_end in large_scanned_in_seg:
            split_boundaries.append(sr_start)
            split_boundaries.append(sr_end)
        split_boundaries = sorted(set(split_boundaries))

        output_pattern = os.path.join(self.temp_dir, f"partial_{seg_uid}_%03d.{ext}")
        success = self._run_split_extraction(seg_start, seg_end, split_boundaries, output_pattern)

        # Find all created files matching the pattern
        base_name = os.path.basename(output_pattern).replace("%03d", "*")
        created_files = sorted(glob_module.glob(os.path.join(self.temp_dir, base_name)))

        # Track all created files for cleanup
        self._partial_scan_temp_files.extend(created_files)

        if not success or not created_files:
            raise ProcessingError(f"ffmpeg split extraction failed for segment ({seg_start:.1f}, {seg_end:.1f})")

        # Determine which files to keep (unscanned) vs discard (scanned)
        # Compute all sub-segment ranges and their keep/discard status
        sub_segments: List[Tuple[float, float, bool]] = []
        current = seg_start
        for sr_start, sr_end in large_scanned_in_seg:
            if current < sr_start:
                sub_segments.append((current, sr_start, True))  # unscanned → KEEP
            sub_segments.append((sr_start, sr_end, False))  # scanned → DISCARD
            current = sr_end
        if current < seg_end:
            sub_segments.append((current, seg_end, True))  # unscanned → KEEP

        result = []
        for i, (s_start, s_end, keep) in enumerate(sub_segments):
            if i < len(created_files) and keep:
                duration = s_end - s_start
                result.append((created_files[i], s_start, duration))

        return result

    async def run_partial_scan(self, chapter_id: str, scan_type: str):
        """Run a partial scan for the region surrounding the given chapter."""

        async def _do_partial_scan():
            try:
                # ── Step 1: Determine target region ────────────────────────────
                active_chapters = sorted(
                    [ch for ch in self.chapters if not ch.deleted],
                    key=lambda ch: ch.timestamp,
                )
                current_chapter = next((ch for ch in active_chapters if ch.id == chapter_id), None)
                if not current_chapter:
                    raise ProcessingError(f"Chapter {chapter_id} not found")

                current_idx = active_chapters.index(current_chapter)
                next_chapter = active_chapters[current_idx + 1] if current_idx + 1 < len(active_chapters) else None

                region_start = current_chapter.timestamp
                region_end = next_chapter.timestamp if next_chapter else self.book_duration

                logger.info(f"Starting {scan_type} partial scan for region ({region_start:.1f}, {region_end:.1f})")

                # ── Step 2: Find unscanned sub-regions ─────────────────────────
                if scan_type == "vad":
                    already_scanned = self._merge_regions(self.vad_scanned_regions)
                else:
                    already_scanned = self._merge_regions(self.normal_scanned_regions + self.vad_scanned_regions)

                uncovered = self._get_uncovered_subregions(already_scanned, region_start, region_end)
                if not uncovered:
                    logger.info("No unscanned sub-regions found; nothing to scan")
                    return

                # ── Step 3: Expand and merge extraction segments ────────────────
                book_dur = self.book_duration
                expand = 5.0
                raw_segments = []
                for u_start, u_end in uncovered:
                    raw_segments.append(
                        (
                            max(0.0, u_start - expand),
                            min(book_dur, u_end + expand),
                        )
                    )
                extraction_segments = self._merge_regions(raw_segments)

                # ── Step 4: 80% threshold check ────────────────────────────────
                total_extraction = sum(e - s for s, e in extraction_segments)
                use_original_file = (total_extraction / book_dur) >= 0.8

                # ── Step 5: Extract audio (PARTIAL_SCAN_PREP) ──────────────────
                self._notify_progress(Step.PARTIAL_SCAN_PREP, 0, "Extracting audio…")

                ext = self.segment_extension or pick_segment_extension(self.audio_file_path)

                if use_original_file:
                    logger.info("Using original audio file for partial scan (coverage >= 80%)")
                    scan_files = [(self.audio_file_path, 0.0, book_dur)]
                else:
                    scan_files: List[Tuple[str, float, float]] = []

                    # Determine which scan type is used for checking large sub-regions
                    if scan_type == "vad":
                        sub_check_scanned = self._merge_regions(self.vad_scanned_regions)
                    else:
                        sub_check_scanned = self._merge_regions(self.normal_scanned_regions + self.vad_scanned_regions)

                    ten_min = 600.0  # 10 minutes

                    for seg_start, seg_end in extraction_segments:
                        # Find large already-scanned sub-regions within this extraction segment
                        large_scanned = []
                        for r_start, r_end in sub_check_scanned:
                            clipped_start = max(r_start, seg_start)
                            clipped_end = min(r_end, seg_end)
                            if clipped_end - clipped_start > ten_min:
                                large_scanned.append((clipped_start, clipped_end))

                        self._notify_progress(
                            Step.PARTIAL_SCAN_PREP,
                            extraction_segments.index((seg_start, seg_end)) / len(extraction_segments) * 100,
                            "Extracting audio…",
                        )

                        files = await asyncio.get_event_loop().run_in_executor(
                            None, self._extract_segment_audio, seg_start, seg_end, large_scanned, ext
                        )
                        scan_files.extend(files)

                if not scan_files:
                    raise ProcessingError("No audio files to scan")

                self._notify_progress(Step.PARTIAL_SCAN_PREP, 100, "Audio extracted")

                # ── Step 6: Run analysis ────────────────────────────────────────
                new_cues: List[DetectedCue] = []

                if scan_type == "vad":
                    target_step = Step.PARTIAL_VAD_ANALYSIS
                else:
                    target_step = Step.PARTIAL_AUDIO_ANALYSIS

                self._notify_progress(target_step, 0, "Scanning audio…")

                for file_idx, (file_path, global_offset, file_duration) in enumerate(scan_files):
                    base_progress = file_idx / len(scan_files) * 100

                    if scan_type == "vad":
                        # Create a progress-translating callback for VAD
                        def make_vad_callback(base_pct, total_files) -> ProgressCallback:
                            def vad_progress_cb(
                                step: Step, percent: float, message: str = "", details: Optional[Dict[str, Any]] = None
                            ) -> None:
                                adjusted_pct = base_pct + percent / total_files
                                self._notify_progress(Step.PARTIAL_VAD_ANALYSIS, adjusted_pct, message, details)

                            return vad_progress_cb

                        vad_service = VadDetectionService(
                            progress_callback=make_vad_callback(base_progress, len(scan_files)),
                            running_processes=self._running_processes,
                            tmp_dir=self.temp_dir,
                        )
                        file_silences = await vad_service.get_vad_silence_boundaries(
                            file_path, file_duration, self.segment_extension
                        )

                        if file_silences is None or self.step not in [
                            Step.PARTIAL_VAD_ANALYSIS,
                            Step.PARTIAL_SCAN_PREP,
                        ]:
                            logger.info("Partial VAD scan was cancelled")
                            return
                    else:
                        # Create a progress-translating callback for audio analysis
                        def make_audio_callback(base_pct, total_files) -> ProgressCallback:
                            def audio_progress_cb(
                                step: Step, percent: float, message: str = "", details: Optional[Dict[str, Any]] = None
                            ) -> None:
                                adjusted_pct = base_pct + percent / total_files
                                self._notify_progress(Step.PARTIAL_AUDIO_ANALYSIS, adjusted_pct, message, details)

                            return audio_progress_cb

                        audio_service = AudioProcessingService(
                            make_audio_callback(base_progress, len(scan_files)),
                            self._running_processes,
                            process_lock=self._process_lock,
                        )
                        file_silences = await audio_service.get_silence_boundaries(
                            file_path,
                            duration=file_duration,
                        )

                        if file_silences is None or self.step != Step.PARTIAL_AUDIO_ANALYSIS:
                            logger.info("Partial audio scan was cancelled")
                            return

                    if file_silences:
                        # Offset timestamps to global time
                        adjusted = [(s + global_offset, e + global_offset) for s, e in file_silences]
                        new_cues.extend(self._silences_to_cues(adjusted))

                # ── Step 7: Merge results (drop near-duplicates) ─────────
                near_dup_threshold = 0.75
                for new_cue in new_cues:
                    is_duplicate = any(
                        abs(existing_cue.timestamp - new_cue.timestamp) < near_dup_threshold
                        for existing_cue in self.detected_cues
                    )
                    if not is_duplicate:
                        self.detected_cues.append(new_cue)

                self.detected_cues.sort(key=lambda x: x.timestamp)
                logger.info(
                    f"Partial scan added {len(new_cues)} new cues; total detected cues: {len(self.detected_cues)}"
                )

                # ── Step 8: Update coverage tracking ──────────────────────────
                if use_original_file:
                    scanned_ranges = [(0.0, book_dur)]
                else:
                    scanned_ranges = extraction_segments

                if scan_type == "vad":
                    self.vad_scanned_regions = self._merge_regions(self.vad_scanned_regions + scanned_ranges)
                else:
                    self.normal_scanned_regions = self._merge_regions(self.normal_scanned_regions + scanned_ranges)

                # ── Step 9: Cleanup temp files ─────────────────────────────────
                self.cleanup_partial_scan_files()

                # ── Step 10: Return to chapter editing ─────────────────────────
                self.step = Step.CHAPTER_EDITING
                asyncio.create_task(
                    get_app_state().broadcast_step_change(
                        Step.CHAPTER_EDITING,
                        extras={"chapter_id": chapter_id, "open_tab": "detected_cue"},
                    )
                )
                logger.info(f"Partial {scan_type} scan complete; returned to chapter editing")

            except asyncio.CancelledError:
                logger.info("Partial scan was cancelled")
                self.cleanup_partial_scan_files()
                raise
            except Exception as e:
                logger.error(f"Partial scan failed: {e}", exc_info=True)
                self.cleanup_partial_scan_files()
                self.step = Step.CHAPTER_EDITING
                asyncio.create_task(
                    get_app_state().broadcast_step_change(
                        Step.CHAPTER_EDITING,
                        error_message=f"Partial scan failed: {str(e)}",
                    )
                )
            finally:
                self._partial_scan_task = None

        self._partial_scan_task = asyncio.create_task(_do_partial_scan())
