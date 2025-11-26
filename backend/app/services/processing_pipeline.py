import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Optional, List, Dict, Any, Tuple

from app.app import get_app_state
from app.models.abs import AudioFile, Book
from pydantic import BaseModel, Field
from .abs_service import ABSService
from .asr_service import create_asr_service
from .audio_service import AudioProcessingService
from .smart_detection_service import SmartDetectionService
from .vad_detection_service import VadDetectionService
from ..core.config import get_app_config
from ..models.chapter import ChapterData, RealignmentData
from ..models.enums import RestartStep, Step
from ..models.progress import ProgressCallback
from ..models.chapter_operation import AICleanupOperation, BatchChapterOperation, ChapterOperation
from .chapter_aligner import ChapterAligner

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Exception raised for processing pipeline errors"""

    pass


class PipelineProgress(BaseModel):
    step: Step
    percent: float = 0.0
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class SimpleChapter(BaseModel):
    timestamp: float
    title: str


class ExistingCueSource(BaseModel):
    id: str
    name: str
    short_name: str
    description: str
    cues: List[SimpleChapter]
    duration: float


class SmartDetectConfig:
    def __init__(
        self,
        segment_length: float = 8.0,
        min_clip_length: float = 1.0,
        asr_buffer: float = 0.25,
        min_silence_duration: float = 2.0,
    ):
        self.segment_length = segment_length
        self.min_clip_length = min_clip_length
        self.asr_buffer = asr_buffer
        self.min_silence_duration = min_silence_duration

    def validate_constraints(self) -> List[str]:
        """Validate configuration constraints and return list of errors"""
        errors = []

        # Range validations
        if not (3.0 <= self.segment_length <= 30.0):
            errors.append("Segment length must be between 3 and 30 seconds")
        if not (0.5 <= self.min_clip_length <= 5.0):
            errors.append("Min clip length must be between 0.5 and 5 seconds")
        if not (0.0 <= self.asr_buffer <= 1.0):
            errors.append("ASR buffer must be between 0 and 1 seconds")
        if not (1.0 <= self.min_silence_duration <= 5.0):
            errors.append("Min silence duration must be between 1 and 5 seconds")

        # Cross-parameter validations
        if self.segment_length < self.min_clip_length:
            errors.append("Segment length cannot be shorter than min clip length")

        return errors


class AIOptions:
    def __init__(
        self,
        inferOpeningCredits: bool = True,
        inferEndCredits: bool = True,
        deselectNonChapters: bool = True,
        keepDeselectedTitles: bool = False,
        usePreferredTitles: bool = False,
        preferredTitlesSource: str = "",
        additionalInstructions: str = "",
        provider_id: str = "",
        model_id: str = "",
    ):
        self.inferOpeningCredits = inferOpeningCredits
        self.inferEndCredits = inferEndCredits
        self.deselectNonChapters = deselectNonChapters
        self.keepDeselectedTitles = keepDeselectedTitles
        self.usePreferredTitles = usePreferredTitles
        self.preferredTitlesSource = preferredTitlesSource
        self.additionalInstructions = additionalInstructions
        self.provider_id = provider_id
        self.model_id = model_id


class ProcessingPipeline:
    """Main processing pipeline that orchestrates the entire chapter generation workflow"""

    def __init__(self, item_id: str, progress_callback: ProgressCallback, smart_detect_config=None):
        self.progress_callback: ProgressCallback = progress_callback
        self.item_id = item_id
        self._running_processes = []
        self._transcription_task = None
        self._extraction_task = None
        self._trimming_task = None
        self._download_task = None
        self._vad_task = None
        self.is_realignment: bool = False

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
        self.smart_detect_config: SmartDetectConfig = (
            smart_detect_config if smart_detect_config else SmartDetectConfig()
        )

        # Processing data
        self.book: Optional[Book] = None
        self.audio_file_path: str = ""
        self.file_starts: Optional[List[float]] = None
        self.existing_cue_sources: List[ExistingCueSource] = []

        self.cues: List[float] = []
        self.segment_files: List[str] = []
        self.trimmed_segment_files: List[str] = []
        self.transcriptions: List[str] = []
        self.transcribed_chapters: List[ChapterData] = []
        self.cue_sets: Dict[int, List[float]] = {}
        self.include_unaligned: List[str] = []

        self.detected_silences: List[Tuple[float, float]] = []  # List of (silence_start, silence_end)

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
        self.cleanup_all_files()

    def cleanup_all_files(self):
        """Cleanup all temporary files and directories"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info(f"Removed temp directory: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temp directory {self.temp_dir}: {e}")
            self.temp_dir = None

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

    async def cancel_processing(self):
        """Cancel any running processing tasks"""
        logger.info("Cancelling processing pipeline...")

        # Cancel any running extraction tasks
        if self._extraction_task:
            logger.info("Cancelling extraction task...")
            self._extraction_task.cancel()
            try:
                await self._extraction_task
            except asyncio.CancelledError:
                logger.info("Extraction task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for extraction task cancellation: {e}")
            self._extraction_task = None

        # Cancel any running transcription tasks
        if self._transcription_task:
            logger.info("Cancelling transcription task...")
            self._transcription_task.cancel()
            self._transcription_task = None

        # Cancel any running trimming tasks
        if self._trimming_task:
            logger.info("Cancelling trimming task...")
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
            logger.info("Cancelling download task...")
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
            logger.info("Cancelling VAD task...")
            self._vad_task.cancel()
            try:
                await self._vad_task
            except asyncio.CancelledError:
                logger.info("VAD task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error waiting for VAD task cancellation: {e}")
            self._vad_task = None

        # Cancel any running ffmpeg processes
        if self._running_processes:
            logger.info(f"Cancelling {len(self._running_processes)} running ffmpeg processes...")
        for process in self._running_processes:
            try:
                if process.poll() is None:  # Process is still running
                    logger.info(f"Terminating ffmpeg process {process.pid}")
                    process.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Force killing ffmpeg process {process.pid}")
                        process.kill()
                else:
                    logger.info(f"ffmpeg process {process.pid} already completed")
            except Exception as e:
                logger.warning(f"Error cancelling process {process.pid}: {e}")

        self._running_processes.clear()

    async def restart_at_step(self, step: RestartStep, error_message: str = None):
        """Restart the pipeline at a specific step"""
        logger.info(f"Restarting pipeline at step: {step}")

        # Cancel any running processes first and wait for them to complete
        await self.cancel_processing()

        if step == RestartStep.IDLE:
            get_app_state().delete_pipeline()
            asyncio.create_task(get_app_state().broadcast_step_change(Step.IDLE, error_message=error_message))
            return

        step_num = step.ordinal

        if step_num <= RestartStep.CHAPTER_EDITING.ordinal:
            self.step = Step.CHAPTER_EDITING

        if step_num <= RestartStep.CONFIGURE_ASR.ordinal:
            self.cleanup_trimmed_files()
            self.transcriptions = []
            self.transcribed_chapters = []
            self.chapters = []
            self.history_stack = []
            self.history_index = -1
            self.step = Step.CONFIGURE_ASR

        if step_num <= RestartStep.CUE_SET_SELECTION.ordinal:
            self.cleanup_segment_files()
            self.cues = []
            self.include_unaligned = []
            self.step = Step.CUE_SET_SELECTION

        if step_num <= RestartStep.SELECT_CUE_SOURCE.ordinal:
            self.cue_sets = {}
            self.detected_silences = []
            self.is_realignment = False
            self.step = Step.SELECT_CUE_SOURCE

        # Background tasks have been properly cancelled, safe to broadcast step change
        logger.info(f"Broadcasting step change to {self.step}")
        asyncio.create_task(get_app_state().broadcast_step_change(self.step, error_message=error_message))

    def get_selection_stats(self) -> Dict[str, int]:
        """Get chapter selection statistics"""
        total = len(self.chapters)
        selected = sum(1 for c in self.chapters if c.selected)
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

    def undo(self) -> Dict[str, Any]:
        """Undo the last action"""
        if not self.can_undo():
            raise ValueError("Cannot undo")

        operation = self.history_stack[self.history_index]
        operation.undo(self)

        self.history_index -= 1

    def redo(self) -> Dict[str, Any]:
        """Redo the next action"""
        if not self.can_redo():
            raise ValueError("Cannot redo")

        operation = self.history_stack[self.history_index + 1]
        operation.apply(self)

        self.history_index += 1

    def update_smart_detect_config(self, config_data: Dict[str, float]) -> Dict[str, Any]:
        """Update smart detect configuration with validation"""
        try:
            # Create new config with provided data
            new_config = SmartDetectConfig(**config_data)

            # Validate constraints
            errors = new_config.validate_constraints()
            if errors:
                return {"success": False, "errors": errors}

            # Update the configuration
            self.smart_detect_config = new_config

            return {"success": True, "config": new_config.__dict__}
        except Exception as e:
            return {"success": False, "errors": [f"Invalid configuration: {str(e)}"]}

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: dict = None):
        """Notify progress via callback"""
        old_step = self.step
        self.step = step
        if old_step != step:
            asyncio.create_task(get_app_state().broadcast_step_change(step))
        self.progress_callback(step, percent, message, details or {})

    def _get_existing_cue_source(self, id: str) -> Optional[ExistingCueSource]:
        """Get an existing cue source by ID"""
        return next((source for source in self.existing_cue_sources if source.id == id), None)

    def _filter_cues_by_duration(self, cues: List[float]) -> List[float]:
        """Filter out chapter breaks that occur after the audiobook ends"""

        # Filter out chapter breaks that occur after the audio file ends
        filtered_cues = [cue for cue in cues if cue < self.book.duration]

        if len(filtered_cues) < len(cues):
            removed_count = len(cues) - len(filtered_cues)
            logger.info(
                f"Filtered out {removed_count} chapter break(s) that occurred after audiobook end ({self.book.duration:.1f}s)"
            )

        return filtered_cues

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
                            f"Downloading file {file_index+1}/{len(audio_files)} - {overall_downloaded / 1024 / 1024:.1f} MB of {total_bytes_all_files / 1024 / 1024:.1f} MB",
                            {
                                "bytes_downloaded": overall_downloaded,
                                "total_bytes": total_bytes_all_files,
                                "current_file": file_index + 1,
                                "total_files": len(audio_files),
                                "current_file_progress": (downloaded_current / total_current) * 100,
                                "files_completed": files_completed,
                                "speed_bps": speed_bps,
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
                    raise RuntimeError(f"Failed to download audio file {i+1}")

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

    async def fetch_item(self, item_id: str) -> Dict[str, Any]:
        """Fetch the audiobook info and files for processing"""

        # Store the item_id for later use
        self.item_id = item_id

        try:
            # Step 1: Validate item and download
            self._notify_progress(Step.VALIDATING, 0, "Starting validation...")

            async with ABSService() as abs_service:
                # Health check
                if not await abs_service.health_check():
                    raise RuntimeError("Unable to connect to Audiobookshelf server")

                self._notify_progress(Step.VALIDATING, 0, "Fetching book details...")

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

                self._notify_progress(Step.VALIDATING, 0, "Checking existing cues...")

                # Check for existing Audiobookshelf cues
                if book.media.chapters:
                    abs_cues: List[SimpleChapter] = []
                    for chapter in book.media.chapters:
                        abs_cues.append(
                            SimpleChapter(
                                timestamp=chapter.start,
                                title=chapter.title,
                            )
                        )
                    if abs_cues:
                        self.existing_cue_sources.append(
                            ExistingCueSource(
                                id="abs",
                                name="Audiobookshelf Chapters",
                                short_name="ABS",
                                description="Uses the existing Audiobookshelf chapter data for this book",
                                cues=abs_cues,
                                duration=book.duration,
                            )
                        )

                # Check for existing embedded cues
                if audio_files:
                    embedded_cues: List[SimpleChapter] = []
                    for audio_file in audio_files:
                        if audio_file.chapters:
                            for chapter in audio_file.chapters:
                                embedded_cues.append(
                                    SimpleChapter(
                                        timestamp=chapter.start,
                                        title=chapter.title,
                                    )
                                )
                    if embedded_cues:
                        self.existing_cue_sources.append(
                            ExistingCueSource(
                                id="embedded",
                                name="Embedded Chapters",
                                short_name="Embedded",
                                description="Uses chapter data from the book's embedded metadata",
                                cues=embedded_cues,
                                duration=book.duration,
                            )
                        )

                # Check for existing Audnexus cues
                audnexus_chapter_data = None
                if book.media.metadata.asin:
                    audnexus_chapter_data = await abs_service.get_audnexus_chapters(book.media.metadata.asin)
                if audnexus_chapter_data:
                    audnexus_cues: List[SimpleChapter] = []
                    for chapter in audnexus_chapter_data.chapters:
                        audnexus_cues.append(
                            SimpleChapter(
                                timestamp=chapter.startOffsetMs / 1000,
                                title=chapter.title,
                            )
                        )
                    if audnexus_cues:
                        self.existing_cue_sources.append(
                            ExistingCueSource(
                                id="audnexus",
                                name="Audnexus Chapters",
                                short_name="Audnexus",
                                description="Uses the Audnexus chapter data associated with the ASIN assigned to this book",
                                cues=audnexus_cues,
                                duration=float(audnexus_chapter_data.runtimeLengthMs) / 1000,
                            )
                        )

                # Check for file start cues
                if audio_files and len(audio_files) > 1:
                    file_start_cues: List[SimpleChapter] = []
                    current_start = 0.0
                    for audio_file in audio_files:
                        file_start_cues.append(
                            SimpleChapter(
                                timestamp=current_start,
                                title=audio_file.metadata.filename,
                            )
                        )
                        current_start += audio_file.duration
                    if file_start_cues:
                        self.existing_cue_sources.append(
                            ExistingCueSource(
                                id="file_starts",
                                name="File Info",
                                short_name="Files",
                                description="Uses the audiobook file names and start times as chapter data",
                                cues=file_start_cues,
                                duration=book.duration,
                            )
                        )

                self._notify_progress(Step.VALIDATING, 0, "Validation complete")

                # Step 2: Download audio files
                self._notify_progress(
                    Step.DOWNLOADING,
                    0,
                    f"Starting download of {len(audio_files)} audio file(s)...",
                )

                # Create download task for proper cancellation handling
                self._download_task = asyncio.create_task(self._download_audio_files(abs_service, item_id, audio_files))
                audio_file_paths = await self._download_task
                self._download_task = None

                # Check if download was cancelled
                if audio_file_paths is None or self.step not in [Step.DOWNLOADING, Step.FILE_PREP]:
                    logger.info("Download was cancelled, stopping fetch process")
                    return {"success": False, "message": "Download was cancelled"}

                # Get file durations and start positions for multi-file processing
                if len(audio_files) > 1:
                    file_durations, self.file_starts = await self._get_file_durations_and_starts(audio_files)
                else:
                    self.audio_file_path = audio_file_paths[0]
                    self.file_starts = None

                self._notify_progress(Step.DOWNLOADING, 100, f"Downloaded {len(audio_files)} audio file(s)")

                # Concat multi-file audio if needed
                if len(audio_file_paths) > 1:
                    self._notify_progress(Step.FILE_PREP, 0, "Preparing files...")

                    # Store original count before concatenation
                    original_file_count = len(audio_file_paths)

                    total_duration = sum(file_durations) if file_durations else None

                    audio_service = AudioProcessingService(
                        self._notify_progress, self.smart_detect_config, self._running_processes
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

                self.step = Step.SELECT_CUE_SOURCE

            return {
                "success": True,
                "step": Step.SELECT_CUE_SOURCE,
            }

        except Exception as e:
            logger.error(f"Fetching item failed: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.IDLE, f"Fetching item failed: {str(e)}")
            raise

    async def create_cues_from_source(self, cue_source: str):
        """Create cues from the user-selected cue source"""

        try:
            # Step 4: Determine chapter breaks based on user selection
            if cue_source == "smart_detect":
                # Smart Detect (regular) - generate cue sets and pause for user selection
                await self._detect_cues()
            elif cue_source == "smart_detect_vad":
                # VAD-based smart detection - generate cue sets and pause for user selection
                await self._detect_cues_vad()
            else:
                # Create cues from an existing source
                existing_source = next((src for src in self.existing_cue_sources if src.id == cue_source), None)

                if not existing_source:
                    raise ValueError(f"Invalid cue source: {cue_source}")

                self._notify_progress(
                    Step.AUDIO_EXTRACTION,
                    0,
                    f"Using {len(existing_source.cues)} cues from {existing_source.short_name}...",
                )
                self.cues = [c.timestamp for c in existing_source.cues]
                self._extraction_task = asyncio.create_task(self.extract_segments())
                await self._extraction_task

        except Exception as e:
            logger.error(f"Failed to create cues: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.SELECT_CUE_SOURCE, f"Processing failed: {str(e)}")
            raise

    async def realign_chapters(self, source_id: str, dramatized: bool = False):
        """Realign chapter timestamps from the user-selected source"""

        try:
            existing_source = next((src for src in self.existing_cue_sources if src.id == source_id), None)

            if not existing_source:
                raise ValueError(f"Invalid realignment source: {source_id}")
            
            self.is_realignment = True

            self.smart_detect_config = SmartDetectConfig(
                asr_buffer=0.5,
                min_silence_duration=1.5,
            )

            self._notify_progress(
                Step.AUDIO_EXTRACTION,
                0,
                f"Calculating audio extraction targets...",
            )

            padding: float = max(30, abs(self.book.duration - existing_source.duration) * 1.5)

            raw_segments = []
            for chapter in existing_source.cues:
                start = max(0, chapter.timestamp - padding)
                end = min(self.book.duration, chapter.timestamp + padding)

                if start > self.book.duration:
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

            if self.detected_silences is None or self.step not in [Step.AUDIO_ANALYSIS, Step.VAD_ANALYSIS]:
                # Detection was canceled
                return

            if self.detected_silences:
                self.detected_silences = [(start, end - 0.25) for start, end in self.detected_silences]
            
            await self._realign_chapters(existing_source, padding)

        except Exception as e:
            logger.error(f"Failed to align chapters: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.SELECT_CUE_SOURCE, f"Processing failed: {str(e)}")
            raise

    async def _realign_chapters(self, source: ExistingCueSource, ransac_threshold: float):
        """Realign chapters using the detected silences and the source chapters"""
        self._notify_progress(Step.AUDIO_ANALYSIS, 100, "Aligning chapters...")

        try:
            source_chapters = [{'time': c.timestamp, 'title': c.title} for c in source.cues]
            
            detected_cues = []
            for start, end in self.detected_silences:
                detected_cues.append({
                    'time': end,
                    'silence_duration': end - start
                })

            aligner = ChapterAligner(
                ransac_threshold=ransac_threshold,
            )
            
            aligned_chapters, _ = aligner.align(
                source_chapters, 
                detected_cues, 
                source.duration, 
                self.book.duration
            )

            new_chapters = []
            for i, ch in enumerate(aligned_chapters):
                timestamp = ch['timestamp']
                confidence = ch['confidence']
                is_guess = ch['is_guess']

                if i == 0:
                    timestamp = 0.0
                    confidence = 1.0
                    is_guess = False

                original_chapter = source.cues[i]
                
                chapter_data = ChapterData(
                    timestamp=timestamp,
                    asr_title=ch['title'],
                    current_title=ch['title'],
                    realignment=RealignmentData(
                        original_timestamp=original_chapter.timestamp,
                        confidence=confidence,
                        is_guess=is_guess,
                    )
                )
                new_chapters.append(chapter_data)

            self.chapters = new_chapters
            
            self._notify_progress(Step.CHAPTER_EDITING, 0, f"Realigned {len(self.chapters)} chapters")

        except Exception as e:
            logger.error(f"Error during chapter alignment: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.SELECT_CUE_SOURCE, f"Alignment failed: {str(e)}")
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
        """Detect chapter breaks and generate cue sets for user selection"""

        # Initialize services
        audio_service = AudioProcessingService(self._notify_progress, self.smart_detect_config, self._running_processes)
        detection_service = SmartDetectionService(self._notify_progress, self.smart_detect_config)

        self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Analyzing audio...")

        # Detect silences
        silences = await audio_service.get_silence_boundaries(
            self.audio_file_path,
            duration=self.book.duration,
        )

        # Check if processing was cancelled (None return indicates cancellation)
        # If the step was changed during processing, we should not continue
        if silences is None or self.step != Step.AUDIO_ANALYSIS:
            logger.info("Processing was cancelled during audio analysis, stopping cue detection")
            return

        self._notify_progress(Step.AUDIO_ANALYSIS, 100, f"Found {len(silences)} silence segments")

        # Store silences in the detection service for clustering
        detection_service.silences = silences

        self.detected_silences = silences.copy() if silences else []

        await self._cluster_and_set_cues(detection_service)

    async def _detect_cues_vad(self):
        """Detect potential chapter boundaries using VAD (Voice Activity Detection)."""
        try:
            if not self.smart_detect_config:
                raise ProcessingError("Smart detection configuration is required for VAD detection")

            self._notify_progress(Step.VAD_PREP, 0, "Preparing files...")

            service = VadDetectionService(
                progress_callback=self._notify_progress,
                smart_detect_config=self.smart_detect_config,
                running_processes=self._running_processes,
            )

            # Create VAD task for proper cancellation handling
            self._vad_task = asyncio.create_task(
                service.get_vad_silence_boundaries(self.audio_file_path, self.book.duration)
            )
            silences = await self._vad_task
            self._vad_task = None

            # Check if processing was cancelled (None return indicates cancellation)
            if silences is None or self.step not in [Step.VAD_PREP, Step.VAD_ANALYSIS]:
                logger.info("Processing was cancelled during VAD analysis, stopping cue detection")
                return

            # Store silences in the detection service for clustering
            service.silences = silences

            self.detected_silences = silences.copy() if silences else []

            await self._cluster_and_set_cues(service)

        except asyncio.CancelledError:
            logger.info("VAD detection was cancelled")
            self._vad_task = None
            raise
        except Exception as e:
            logger.error(f"VAD detection failed: {e}", exc_info=True)
            self._vad_task = None
            await self.restart_at_step(RestartStep.SELECT_CUE_SOURCE, f"VAD detection failed: {str(e)}")
            raise ProcessingError(f"Error during VAD detection: {str(e)}")

    async def _detect_realignment_cues(self, segments: List[Tuple[float, str]]):
        """Detect chapter cues for realignment"""

        audio_service = AudioProcessingService(self._notify_progress, self.smart_detect_config, self._running_processes)

        self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Analyzing audio...")

        silences: List[Tuple[float, float]] = []

        for idx, (segment_start, segment_file) in enumerate(segments):
            segment_silences = await audio_service.get_silence_boundaries(
                segment_file,
                min_silence_duration=1,
                publish_progress=False,
            )
            if segment_silences:
                adjusted_silences = [(start + segment_start, end + segment_start) for start, end in segment_silences]
                silences.extend(adjusted_silences)
            progress = (idx + 1) / len(segments) * 100
            self._notify_progress(Step.AUDIO_ANALYSIS, progress, "Performing focused audio analysis...")

        if silences is None or self.step != Step.AUDIO_ANALYSIS:
            logger.info("Processing was cancelled during audio analysis, stopping cue detection")
            return

        self.detected_silences = silences.copy()

    async def _detect_realignment_cues_vad(self, segments: List[Tuple[float, str]]):
        """Detect potential chapter boundaries using VAD (Voice Activity Detection)."""
        try:
            self._notify_progress(Step.VAD_ANALYSIS, 0, "Preparing to analyze files...")

            service = VadDetectionService(
                progress_callback=self._notify_progress,
                smart_detect_config=self.smart_detect_config,
                running_processes=self._running_processes,
            )

            self._vad_task = asyncio.create_task(
                service.get_vad_silence_boundaries_from_segments(segments)
            )
            silences = await self._vad_task
            self._vad_task = None

            if silences is None or self.step not in [Step.VAD_PREP, Step.VAD_ANALYSIS]:
                logger.info("Processing was cancelled during VAD analysis, stopping cue detection")
                return

            self.detected_silences = silences.copy() if silences else []

        except asyncio.CancelledError:
            logger.info("VAD detection was cancelled")
            self._vad_task = None
            raise
        except Exception as e:
            logger.error(f"VAD detection failed: {e}", exc_info=True)
            self._vad_task = None
            await self.restart_at_step(RestartStep.SELECT_CUE_SOURCE, f"VAD detection failed: {str(e)}")
            raise ProcessingError(f"Error during VAD detection: {str(e)}")

    async def _cluster_and_set_cues(self, service):
        """Generate cue sets from detection service and store for user selection"""
        # Generate cue sets
        self._notify_progress(Step.CUE_SET_SELECTION, 0, "Generating cue set options...")
        cue_sets = service.get_clustered_cue_sets(service.silences, self.book.duration)

        # Check again if processing was cancelled during cue set generation
        if self.step != Step.CUE_SET_SELECTION:
            logger.info("Processing was cancelled during cue set generation, stopping cue detection")
            return

        # Store cue sets for user selection
        self.cue_sets = cue_sets

        self._notify_progress(Step.CUE_SET_SELECTION, 100, f"Generated {len(cue_sets)} cue sets")

        logger.info(f"Generated {len(cue_sets)} cue sets")

    async def _extract_audio_segments(self):
        """Extract audio segments for transcription"""

        self._notify_progress(Step.AUDIO_EXTRACTION, 0, "Extracting chapter audio segments...")

        # Filter chapter breaks to remove any that occur after the audiobook ends
        self.cues = self._filter_cues_by_duration(self.cues)

        audio_service = AudioProcessingService(self._notify_progress, self.smart_detect_config, self._running_processes)

        self.segment_files = await audio_service.extract_segments(self.audio_file_path, self.cues, self.temp_dir)

        # Check if extraction was cancelled (None return indicates cancellation)
        # If the step was changed during processing, we should not continue
        if self.segment_files is None or self.step != Step.AUDIO_EXTRACTION:
            logger.info("Processing was cancelled during audio extraction, stopping extraction")
            return

        self._notify_progress(Step.AUDIO_EXTRACTION, 100, f"Extracted {len(self.segment_files)} chapter segments")

        logger.info(f"Extracted {len(self.segment_files)} segments")

    async def _extract_realignment_segments(self, segment_times: List[Tuple[float, float]]):
        """Extract audio segments for realignment detection"""

        self._notify_progress(Step.AUDIO_EXTRACTION, 0, "Performing targeted audio extraction...")

        audio_service = AudioProcessingService(self._notify_progress, self.smart_detect_config, self._running_processes)

        self.segment_files = await audio_service.extract_segments(
            audio_file=self.audio_file_path,
            timestamps=segment_times,
            output_dir=self.temp_dir,
        )

        if self.segment_files is None or self.step != Step.AUDIO_EXTRACTION:
            logger.info("Processing was cancelled during audio extraction, stopping extraction")
            return

        self._notify_progress(Step.AUDIO_EXTRACTION, 100, f"Extracted {len(self.segment_files)} target segments")

        logger.info(f"Extracted {len(self.segment_files)} target segments")

    async def _create_trimmed_segments(self):
        """Create trimmed segments for transcription based on ASR options"""
        try:
            app_config = get_app_config()
            copy_only = not app_config.asr_options.trim

            audio_service = AudioProcessingService(
                self._notify_progress, self.smart_detect_config, self._running_processes
            )

            # Create trimmed segments from original segments
            self._trimming_task = asyncio.create_task(audio_service.trim_segments(self.segment_files, copy_only))
            trimmed_files = await self._trimming_task
            self._trimming_task = None

            # Store the trimmed segments for transcription
            self.trimmed_segment_files = trimmed_files

            self._notify_progress(Step.ASR_PROCESSING, 100, f"Finished trimming {len(trimmed_files)} chapters")
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
            0,
            "Initializing. This may take a while the first time...",
        )

        # Run ASR operations in a thread pool to avoid blocking the event loop
        def run_transcription():
            """Run transcription in a separate thread"""
            import asyncio

            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Run the ASR service in this thread's event loop
                async def transcribe():
                    async with create_asr_service(self._notify_progress) as asr_service:
                        self._transcription_task = asyncio.create_task(
                            asr_service.transcribe(self.trimmed_segment_files)
                        )
                        result = await self._transcription_task
                        self.transcription_task = None
                        return result

                return loop.run_until_complete(transcribe())
            finally:
                loop.close()

        # Run in thread pool executor to avoid blocking main event loop
        self.transcriptions = await asyncio.get_event_loop().run_in_executor(None, run_transcription)

        # Check if processing was cancelled during transcription
        if self.step != Step.ASR_PROCESSING:
            logger.info("Processing was cancelled during transcription, stopping transcription")
            return

        self._notify_progress(Step.ASR_PROCESSING, 100, "Transcription complete")

        logger.info(f"Transcribed {len(self.transcriptions)} segments")

    async def _create_initial_chapters(self):
        """Create initial chapter objects with basic titles (without AI cleanup)"""

        # Check if processing was cancelled before creating chapters
        if self.step != Step.ASR_PROCESSING:
            logger.info("Processing was cancelled before creating chapters, stopping chapter creation")
            return

        self._notify_progress(Step.CHAPTER_EDITING, 0, "Creating initial chapters...")

        # Create chapter objects with basic titles
        for i, timestamp in enumerate(self.cues):
            # Use transcription for title if available, otherwise use empty string
            if i < len(self.transcriptions) and self.transcriptions[i].strip():
                # Use full transcription as basic title
                initial_title = self.transcriptions[i].strip()
            else:
                # Fallback to empty string
                initial_title = ""

            chapter = ChapterData(
                timestamp=timestamp,
                asr_title=initial_title,
                current_title=initial_title,
                selected=True,
                audio_segment_path=self.trimmed_segment_files[i] if i < len(self.trimmed_segment_files) else "",
            )
            self.transcribed_chapters.append(chapter)

        # Also populate the main chapters list for the UI
        self.chapters = self.transcribed_chapters.copy()
        self.step = Step.CHAPTER_EDITING

        self._notify_progress(
            Step.CHAPTER_EDITING,
            100,
            f"Created {len(self.transcribed_chapters)} initial chapters",
        )

        logger.info(f"Created {len(self.transcribed_chapters)} initial chapters")

    async def proceed_with_transcription(self):
        """Proceed with trimming and transcription from CONFIGURE_ASR step"""
        try:
            self._notify_progress(Step.ASR_PROCESSING, 0, "Preparing files...")

            # First create trimmed segments for transcription
            await self._create_trimmed_segments()

            # Then transcribe the trimmed segments
            await self._transcribe_segments()

            # Check if transcription was cancelled
            if self.step != Step.ASR_PROCESSING:
                logger.info("Processing was cancelled during transcription")
                return {"success": False, "message": "Processing was cancelled"}

            # Create initial chapters
            await self._create_initial_chapters()

            # Check if chapter creation was cancelled
            if self.step != Step.CHAPTER_EDITING:
                logger.info("Processing was cancelled during chapter creation")
                return {"success": False, "message": "Processing was cancelled"}

            return {
                "success": True,
                "book": self.book,
                "chapters": self.transcribed_chapters,
                "segment_files": self.segment_files,
                "step": Step.CHAPTER_EDITING,
                "message": "Chapter extraction and transcription complete",
            }
        except asyncio.CancelledError:
            logger.info("Processing was cancelled during transcription")
            await self.restart_at_step(RestartStep.CONFIGURE_ASR)
        except Exception as e:
            logger.error(f"Failed to proceed with transcription: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CONFIGURE_ASR, f"Transcription failed: {str(e)}")
            raise

    async def skip_transcription(self) -> Dict[str, Any]:
        """Skip transcription and create empty chapters with timestamps only"""
        try:
            # Create chapter objects with empty titles
            for i, timestamp in enumerate(self.cues):
                chapter = ChapterData(
                    timestamp=timestamp,
                    asr_title="",
                    current_title="",
                    selected=True,
                    audio_segment_path=self.segment_files[i] if i < len(self.segment_files) else "",
                )
                self.transcribed_chapters.append(chapter)

            # Also populate the main chapters list for the UI
            self.chapters = self.transcribed_chapters.copy()

            # Set empty transcriptions to match chapter count
            self.transcriptions = [""] * len(self.cues)

            # self.step = Step.CHAPTER_EDITING
            self._notify_progress(Step.CHAPTER_EDITING, 0)

            logger.info(f"Skipped transcription, created {len(self.transcribed_chapters)} empty chapters")

            return {
                "success": True,
                "book": self.book,
                "chapters": self.transcribed_chapters,
                "segment_files": [],
                "step": Step.CHAPTER_EDITING,
                "message": "Chapters created without transcription",
            }

        except Exception as e:
            logger.error(f"Failed to skip transcription: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CONFIGURE_ASR, f"Failed to create chapters: {str(e)}")
            raise

    async def extract_segments(self) -> None:
        """Extract initial audio segments without trimming for CONFIGURE_ASR step"""
        try:
            await self._extract_audio_segments()

            # Check if extraction was cancelled
            if self.segment_files is None or self.step != Step.AUDIO_EXTRACTION:
                logger.info("Processing was cancelled during segment extraction")
                return

            # Transition to CONFIGURE_ASR step (the _notify_progress method will handle the broadcast)
            self._notify_progress(Step.CONFIGURE_ASR, 0, "Ready for transcription configuration")

            logger.info(f"Extracted {len(self.segment_files)} segments, transitioned to CONFIGURE_ASR")

        except Exception as e:
            logger.error(f"Initial segment extraction failed: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CUE_SET_SELECTION, f"Initial extraction failed: {str(e)}")
            raise

    def _deduplicate_timestamps(
        self,
        timestamps: List[float],
        tolerance: float,
        priority_timestamps: List[float] = None,
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
        cue_sources: List[ExistingCueSource],
        include_unaligned: List[str],
    ) -> List[float]:
        """Merge unaligned timestamps from existing chapter sets with selected timestamps"""
        if not include_unaligned or not cue_sources:
            return selected_timestamps

        all_unaligned_timestamps = []
        tolerance = 5.0

        for source_id in include_unaligned:
            cue_source = self._get_existing_cue_source(source_id)
            if not cue_source:
                logger.warning(f"No existing cue source found for include_unaligned: {source_id}")
                continue

            existing_timestamps = [c.timestamp for c in cue_source.cues]

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
            logger.info(f"Found {len(unaligned_timestamps)} unaligned timestamps from {source_id} chapters")

        # Merge all timestamps and remove near-duplicates within tolerance
        all_timestamps = selected_timestamps + all_unaligned_timestamps
        deduplicated_timestamps = self._deduplicate_timestamps(all_timestamps, tolerance, selected_timestamps)

        logger.info(
            f"Merged {len(all_unaligned_timestamps)} total unaligned timestamps from {include_unaligned} chapter sets. "
            f"Total timestamps: {len(deduplicated_timestamps)} (was {len(selected_timestamps)}) after deduplication"
        )

        return deduplicated_timestamps

    async def select_cue_set(self, chapter_count: int, include_unaligned: List[str] = None) -> Dict[str, Any]:
        """Select a cue set from smart detect and proceed to CONFIGURE_ASR"""
        try:
            if chapter_count not in self.cue_sets:
                raise ValueError(f"Invalid chapter count: {chapter_count}")

            # Set the selected cues
            self.cues = self.cue_sets[chapter_count]
            self.include_unaligned = include_unaligned or []

            # Add unaligned cues if specified
            if self.include_unaligned:
                self.cues = self._merge_unaligned_timestamps(
                    self.cues,
                    self.existing_cue_sources,
                    self.include_unaligned,
                )

            logger.info(f"Selected cue set with {len(self.cues)} cues")

            # Extract initial segments first, then go to CONFIGURE_ASR
            await self.extract_segments()

            return {
                "success": True,
                "step": Step.CONFIGURE_ASR,
                "message": "Ready for transcription configuration",
            }

        except Exception as e:
            logger.error(f"Failed to select cue set: {e}", exc_info=True)
            await self.restart_at_step(RestartStep.CUE_SET_SELECTION, f"Cue set selection failed: {str(e)}")
            raise

    def get_segment_count(self) -> int:
        """Get the number of segments that will be transcribed"""
        return len(self.cues) if self.cues else 0

    async def submit_chapters(self, chapters: List[ChapterData]) -> bool:
        """Submit final chapters to Audiobookshelf"""

        # Convert chapters to the format expected by ABS
        chapter_data = []
        for chapter in chapters:
            if chapter.selected:  # Only submit selected chapters
                chapter_data.append((chapter.timestamp, chapter.current_title))

        try:
            async with ABSService() as abs_service:
                success = await abs_service.upload_chapters(
                    self.book.id,
                    chapter_data,
                    self.book.duration,
                )

                if success:
                    self._notify_progress(Step.COMPLETED, 100, "Chapter submission completed successfully")

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
            self._notify_progress(Step.AI_CLEANUP, 0, "Starting AI cleanup...")

            # Process with AI using the new provider system
            from ..core.config import get_app_config
            from ..services.llm_providers.registry import create_provider

            # Create the AI provider using the registry system
            # The provider classes handle their own configuration via saved settings
            ai_provider = create_provider(self.ai_options.provider_id, self._notify_progress)
            if not ai_provider:
                raise ValueError(f"Failed to create provider {self.ai_options.provider_id}")

            # Prepare transcriptions for processing (use ASR titles as raw transcriptions)
            transcriptions = []
            for chapter in selected_chapters:
                transcriptions.append(chapter.current_title)

            # Use AI options
            infer_opening_credits = self.ai_options.inferOpeningCredits
            infer_end_credits = self.ai_options.inferEndCredits
            deselect_non_chapters = self.ai_options.deselectNonChapters
            keep_deselected_titles = self.ai_options.keepDeselectedTitles
            additional_instructions = self.ai_options.additionalInstructions
            preferred_titles: List[str] = None

            # Get preferred titles
            if self.ai_options.usePreferredTitles and self.ai_options.preferredTitlesSource:
                selected_source: Optional[ExistingCueSource] = next(
                    (s for s in self.existing_cue_sources if s.id == self.ai_options.preferredTitlesSource), None
                )
                if selected_source:
                    preferred_titles = [ch.title for ch in selected_source.cues if ch.title]

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
                    transcriptions,
                    model_id=self.ai_options.model_id,
                    additional_instructions=instructions_list,
                    deselect_non_chapters=deselect_non_chapters,
                    infer_opening_credits=infer_opening_credits,
                    infer_end_credits=infer_end_credits,
                    preferred_titles=preferred_titles,
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

                    # Check if title is None, empty, just whitespace, or the literal string "null"
                    is_valid_title = (
                        new_title is not None
                        and str(new_title).strip() != ""
                        and str(new_title).strip().lower() != "null"
                    )

                    if is_valid_title:
                        operations.append(
                            AICleanupOperation(
                                chapter_id=chapter.id,
                                old_title=chapter.current_title,
                                new_title=new_title,
                            )
                        )
                    else:
                        operations.append(
                            AICleanupOperation(
                                chapter_id=chapter.id,
                                old_title=chapter.current_title,
                                new_title=chapter.current_title if keep_deselected_titles else "",
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

            logger.info(f"AI cleanup completed")
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

        has_cue_sets = len(self.cue_sets) > 0 if self.cue_sets else False

        match self.step:
            case Step.SELECT_CUE_SOURCE:
                restart_options.append(RestartStep.IDLE)
            case Step.CUE_SET_SELECTION:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_CUE_SOURCE)
            case Step.CONFIGURE_ASR:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_CUE_SOURCE)
                if has_cue_sets:
                    restart_options.append(RestartStep.CUE_SET_SELECTION)
            case Step.CHAPTER_EDITING:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_CUE_SOURCE)
                if has_cue_sets:
                    restart_options.append(RestartStep.CUE_SET_SELECTION)
                if not self.is_realignment:
                    restart_options.append(RestartStep.CONFIGURE_ASR)
            case Step.REVIEWING | Step.COMPLETED:
                restart_options.append(RestartStep.IDLE)
                restart_options.append(RestartStep.SELECT_CUE_SOURCE)
                if has_cue_sets:
                    restart_options.append(RestartStep.CUE_SET_SELECTION)
                if not self.is_realignment:
                    restart_options.append(RestartStep.CONFIGURE_ASR)
                restart_options.append(RestartStep.CHAPTER_EDITING)
            case _:
                pass

        restart_options.reverse()
        return [option.value for option in restart_options]
