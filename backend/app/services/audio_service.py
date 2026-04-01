import asyncio
import logging
import multiprocessing
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Optional

from app.core.config import get_app_config
from app.core.constants import (
    CHAPTER_START_PADDING,
    MIN_SEGMENT_GAP,
    MIN_SILENCE_DURATION,
    MIN_TRIMMED_SEGMENT_LENGTH,
)
from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    """Convert seconds to hh:mm:ss format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Seconds of overlap between adjacent segments during parallel silence detection
PARALLEL_SILENCE_OVERLAP = 20


# Minimum duration (in seconds) to warrant parallel detection
MIN_DURATION_FOR_PARALLEL = 30 * 60 # 30 minutes


def _get_worker_count() -> int:
    """Use 2/3 of cores"""
    total_cores = multiprocessing.cpu_count()
    return max(1, total_cores * 2 // 3)


def _compute_virtual_segments(
    total_duration: float,
    num_workers: int,
    overlap: float = PARALLEL_SILENCE_OVERLAP,
) -> List[Tuple[float, float]]:
    """
    Divide audio into overlapping virtual segments for parallel processing.

    Returns list of (seek_position, segment_duration) tuples suitable for
    FFmpeg -ss and -t flags.
    """
    segment_length = total_duration / num_workers
    segments = []
    for i in range(num_workers):
        seg_start = max(0.0, i * segment_length - overlap / 2)
        seg_end = min(total_duration, (i + 1) * segment_length + overlap / 2)
        segments.append((seg_start, seg_end - seg_start))
    return segments


def _merge_overlapping_silences(
    silences: List[Tuple[float, float]],
    tolerance: float = 0.05,
) -> List[Tuple[float, float]]:
    """
    Sort silences by start time and merge intervals that overlap or are
    within tolerance seconds of each other.
    """
    if not silences:
        return []
    sorted_silences = sorted(silences, key=lambda s: s[0])
    merged = [sorted_silences[0]]
    for start, end in sorted_silences[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + tolerance:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def crop_start_to_tempfile(audio_file: str, crop_seconds: float) -> str | None:
    """Crop audio from the start and write to a temporary file.

    Returns the temp file path on success, None on failure.
    """
    from uuid import uuid4

    p = Path(audio_file)
    temp_path = str(p.with_name(f"{p.stem}_jitter_{uuid4().hex[:8]}{p.suffix}"))

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(crop_seconds), "-i", audio_file, "-c", "copy", temp_path],
            capture_output=True,
            check=True,
        )
        return temp_path
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to crop audio {audio_file}: {e}")
        return None


class AudioProcessingService:
    """Service for audio processing operations using ffmpeg"""

    def __init__(self, progress_callback: ProgressCallback, running_processes=None, asr_buffer: float = 0.1, process_lock: threading.Lock = None):
        self.progress_callback: ProgressCallback = progress_callback
        self._running_processes = running_processes if running_processes is not None else []
        self._process_lock = process_lock or threading.Lock()
        self.asr_buffer = asr_buffer

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: dict = None):
        """Notify progress via callback"""
        self.progress_callback(step, percent, message, details or {})

    def clean_up_orphaned_segment_files(self, output_dir: str):
        """Clean up any orphaned segment files from previous runs"""
        for filename in os.listdir(output_dir):
            if filename.startswith("segment_"):
                try:
                    os.remove(os.path.join(output_dir, filename))
                except Exception:
                    pass

    def clean_up_orphaned_trimmed_files(self, output_dir: str):
        """Clean up any orphaned trimmed file"""
        for filename in os.listdir(output_dir):
            if filename.startswith("trimmed_"):
                try:
                    os.remove(os.path.join(output_dir, filename))
                except Exception:
                    pass

    async def get_silence_boundaries(
        self,
        input_file: str,
        silence_threshold: float = -30,
        duration: Optional[float] = None,
        publish_progress: bool = True,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Detect silence boundaries in an audio file using ffmpeg.
        Returns a list of tuples containing (silence_start, silence_end) timestamps.

        When duration is known and long enough, runs parallel detection across
        virtual segments for faster results on multi-core machines.
        """
        if publish_progress:
            self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Starting audio analysis...")

        num_workers = _get_worker_count()
        use_parallel = (
            duration is not None
            and duration >= MIN_DURATION_FOR_PARALLEL
            and num_workers > 1
        )

        loop = asyncio.get_event_loop()

        if use_parallel:
            executor_task = loop.run_in_executor(
                None,
                self._run_parallel_silence_detection,
                input_file,
                silence_threshold,
                duration,
            )
        else:
            # noinspection SpellCheckingInspection
            cmd = [
                "ffmpeg",
                "-i",
                input_file,
                "-af",
                f"silencedetect=n={silence_threshold}dB:d={MIN_SILENCE_DURATION}",
                "-f",
                "null",
                "-",
            ]
            executor_task = loop.run_in_executor(
                None,
                self._run_silence_detection,
                cmd,
                duration,
            )

        file_silences = await executor_task

        # Check if processing was cancelled
        if file_silences is None:
            logger.info("Silence detection was cancelled, returning None")
            return None

        if publish_progress:
            self._notify_progress(Step.AUDIO_ANALYSIS, 100, f"Found {len(file_silences)} potential chapter breaks")

        return file_silences

    def _run_silence_detection(
        self,
        cmd: List[str],
        duration: Optional[float],
        publish_progress: bool = True,
    ) -> Optional[List[Tuple[float, float]]]:
        """Run silence detection in a separate thread"""
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

        with self._process_lock:
            self._running_processes.append(process)

        try:
            silence_starts = []
            silence_ends = []

            pattern_start = re.compile(r"silence_start:\s*([\d\.]+)")
            pattern_end = re.compile(r"silence_end:\s*([\d\.]+)")

            last_progress = 0.0
            last_feed_time = 0.0

            for line in process.stderr:
                if "silence_start" in line:
                    match = pattern_start.search(line)
                    if match:
                        timestamp = float(match.group(1))
                        silence_starts.append(timestamp)
                elif "silence_end" in line:
                    match = pattern_end.search(line)
                    if match:
                        timestamp = float(match.group(1))
                        silence_ends.append(timestamp)

                        # Update progress based on silence end timestamp
                        if publish_progress and duration and timestamp > last_progress:
                            file_progress = min((timestamp / duration) * 100, 100)
                            message = f"Analyzing audio... ({_format_time(timestamp)} / {_format_time(duration)})"

                            # Throttle feed_text to max 2 updates/sec
                            cue_count = len(silence_ends)
                            now = time.monotonic()
                            details = None
                            if now - last_feed_time >= 0.5:
                                details = {
                                    "feed_text": f"Found {cue_count} potential chapter cue{'s' if cue_count != 1 else ''}"
                                }
                                last_feed_time = now

                            self._notify_progress(Step.AUDIO_ANALYSIS, file_progress, message, details)

                            last_progress = timestamp

            process.wait()

            if process.returncode != 0:
                if process.returncode in [254, 255]:
                    # Process was killed (cancelled) or input file missing, return None to indicate cancellation
                    logger.info("ffmpeg silence detection was cancelled")
                    return None
                else:
                    logger.error(
                        f"ffmpeg silence detection failed in _run_silence_detection with return code {process.returncode}"
                    )
                    return []

            return list(zip(silence_starts, silence_ends))
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

    def _run_silence_detection_worker(
        self,
        input_file: str,
        seek: float,
        segment_duration: float,
        silence_threshold: float,
        duration: float,
        cancelled: threading.Event,
        worker_progress: list,
        worker_index: int,
        cue_counter: list,
        last_feed_time: list,
    ) -> Optional[List[Tuple[float, float]]]:
        """Detect silences in a virtual segment of the audio file."""
        if cancelled.is_set():
            return None

        # noinspection SpellCheckingInspection
        cmd = [
            "ffmpeg",
            "-ss", str(seek),
            "-i", input_file,
            "-t", str(segment_duration),
            "-af", f"silencedetect=n={silence_threshold}dB:d={MIN_SILENCE_DURATION}",
            "-f", "null",
            "-",
        ]

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

        with self._process_lock:
            self._running_processes.append(process)

        try:
            silence_starts = []
            silence_ends = []

            pattern_start = re.compile(r"silence_start:\s*([\d\.]+)")
            pattern_end = re.compile(r"silence_end:\s*([\d\.]+)")

            for line in process.stderr:
                if cancelled.is_set():
                    process.terminate()
                    process.wait()
                    return None

                if "silence_start" in line:
                    match = pattern_start.search(line)
                    if match:
                        local_ts = float(match.group(1))
                        silence_starts.append(local_ts + seek)
                elif "silence_end" in line:
                    match = pattern_end.search(line)
                    if match:
                        local_ts = float(match.group(1))
                        silence_ends.append(local_ts + seek)

                        if segment_duration > 0:
                            worker_progress[worker_index] = min((local_ts / segment_duration) * 100, 100)

                        # Report aggregate progress from this worker
                        avg_progress = sum(worker_progress) / len(worker_progress)
                        virtual_ts = (avg_progress / 100) * duration
                        message = f"Analyzing audio... ({_format_time(virtual_ts)} / {_format_time(duration)})"

                        with self._process_lock:
                            cue_counter[0] += 1
                            cue_count = cue_counter[0]

                        now = time.monotonic()
                        details = None
                        if now - last_feed_time[0] >= 0.5:
                            details = {
                                "feed_text": f"Found {cue_count} potential chapter cue{'s' if cue_count != 1 else ''}"
                            }
                            last_feed_time[0] = now

                        self._notify_progress(Step.AUDIO_ANALYSIS, avg_progress, message, details)

            process.wait()

            if process.returncode in [-15, 254, 255]:
                cancelled.set()
                return None
            if process.returncode != 0:
                logger.error(
                    f"ffmpeg silence detection worker {worker_index} failed with return code {process.returncode}"
                )
                return []

            worker_progress[worker_index] = 100.0
            return list(zip(silence_starts, silence_ends))
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

    def _run_parallel_silence_detection(
        self,
        input_file: str,
        silence_threshold: float,
        duration: float,
    ) -> Optional[List[Tuple[float, float]]]:
        """Run silence detection across virtual segments in parallel."""
        num_workers = _get_worker_count()
        segments = _compute_virtual_segments(duration, num_workers)
        cancelled = threading.Event()
        worker_progress = [0.0] * len(segments)
        cue_counter = [0]
        last_feed_time = [0.0]

        logger.info(
            f"Running parallel silence detection: {len(segments)} segments "
            f"across {duration:.0f}s audio with {PARALLEL_SILENCE_OVERLAP}s overlap"
        )

        all_silences: List[Tuple[float, float]] = []

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(
                    self._run_silence_detection_worker,
                    input_file, seek, seg_dur, silence_threshold,
                    duration, cancelled, worker_progress, i,
                    cue_counter, last_feed_time,
                ): i
                for i, (seek, seg_dur) in enumerate(segments)
            }

            for future in as_completed(futures):
                result = future.result()

                if cancelled.is_set():
                    for f in futures:
                        f.cancel()
                    return None

                if result:
                    all_silences.extend(result)

        merged = _merge_overlapping_silences(all_silences)
        logger.info(
            f"Parallel silence detection complete: {len(all_silences)} raw silences "
            f"merged to {len(merged)}"
        )
        return merged

    async def extract_segments(
        self,
        audio_file: str,
        timestamps: List[float],
        output_dir: str,
        use_wav: bool = False,
        allow_retry: bool = True,
    ) -> Optional[List[str]]:
        """Extract audio segments based on timestamps from single or multiple files"""

        self._notify_progress(Step.AUDIO_EXTRACTION, 0, "Starting chapter audio extraction...")

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        # Start the extraction in background
        executor_task = loop.run_in_executor(
            None,
            self._run_segment_extraction,
            audio_file,
            timestamps,
            output_dir,
            use_wav,
            allow_retry,
        )

        
        result = await executor_task

        # Check if extraction was cancelled (empty result could indicate cancellation)
        if not result:
            logger.info("Audio extraction was cancelled or failed")
            return None

        self._notify_progress(Step.AUDIO_EXTRACTION, 100, f"Extracted audio for {len(result)} chapters")

        return result

    def extract_single_segment(
        self,
        audio_file: str,
        start_time: float,
        duration: float,
        output_path: str,
    ) -> str:
        """Extract a single audio segment using ffmpeg -ss/-t for direct seeking.

        This is more efficient than the segment-split approach for small numbers of chapters.
        """
        extension = Path(output_path).suffix.lstrip(".")
        use_copy = extension not in ["wav"]

        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_time + CHAPTER_START_PADDING - self.asr_buffer),
            "-t",
            str(duration),
            "-i",
            audio_file,
        ]

        if use_copy:
            command.extend(["-acodec", "copy"])

        command.append(output_path)

        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        with self._process_lock:
            self._running_processes.append(process)

        try:
            _, stderr_output = process.communicate()
            if process.returncode != 0:
                logger.warning(f"Failed to extract segment at {start_time}s: ffmpeg returned {process.returncode}: {stderr_output[-500:] if stderr_output else ''}")
                return None
            return output_path
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

    def _trim_segment(self, segment_path: str, extension: str):
        """Trim a segment at its longest silence"""
        silences = self._sync_get_silence_boundaries(segment_path)

        # Filter out silences that are too close to the beginning
        if silences:
            silences = [s for s in silences if s[1] >= self.asr_buffer + MIN_TRIMMED_SEGMENT_LENGTH]

        if silences:
            # Sort by duration and get the longest silence
            longest = sorted(silences, key=lambda x: (x[1] - x[0]), reverse=True)[0]
            trim_point = max(MIN_TRIMMED_SEGMENT_LENGTH, longest[0] + self.asr_buffer)

            # Create temp file for trimmed audio
            temp_path = segment_path.replace(f".{extension}", f"_tmp.{extension}")
            trim_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                segment_path,
                "-t",
                str(trim_point),
                "-c",
                "copy",
                temp_path,
            ]
            subprocess.run(trim_cmd, capture_output=True, check=True)
            os.replace(temp_path, segment_path)

    def _trim_segment_to_path(self, segment_path: str, output_path: str):
        """Trim a segment at its longest silence, writing to a specific output path"""
        silences = self._sync_get_silence_boundaries(segment_path)

        # Filter out silences that are too close to the beginning
        original_silences = silences.copy() if silences else []
        if silences:
            silences = [s for s in silences if s[1] >= self.asr_buffer + MIN_TRIMMED_SEGMENT_LENGTH]

        if silences:
            longest = sorted(silences, key=lambda x: (x[1] - x[0]), reverse=True)[0]
            trim_point = max(MIN_TRIMMED_SEGMENT_LENGTH, longest[0] + self.asr_buffer)

            trim_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                segment_path,
                "-t",
                str(trim_point),
                "-c",
                "copy",
                output_path,
            ]
            subprocess.run(trim_cmd, capture_output=True, check=True)
        else:
            # No silence found, just copy
            import shutil

            shutil.copy2(segment_path, output_path)

    def _run_segment_extraction(
        self,
        audio_file: str,
        timestamps: List[float] | List[Tuple[float, float]],
        output_dir: str,
        use_wav: bool = False,
        allow_retry: bool = True,
    ) -> List[str]:
        """Run segment extraction in a separate thread"""

        def _timestamp_to_filename(timestamp: float | Tuple[float, float]) -> str:
            """Convert timestamp to filename format using milliseconds"""
            milliseconds: int
            if isinstance(timestamp, tuple):
                milliseconds = int(timestamp[0] * 1000)
            else:
                milliseconds = int(timestamp * 1000)
            return f"{milliseconds}"

        # Generate expanded timestamps for segment extraction
        expanded_timestamps = []

        if isinstance(timestamps[0], tuple):
            for start_ts, end_ts in timestamps:
                expanded_timestamps.append(start_ts)
                expanded_timestamps.append(end_ts)
        else:
            segment_length = get_app_config().asr_options.segment_length
            for i, ts in enumerate(timestamps):
                start_ts = max(0, ts - self.asr_buffer)
                expanded_timestamps.append(start_ts)
                end_ts = ts + segment_length

                # Adjust if the end timestamp overlaps with the next start timestamp
                if i < len(timestamps) - 1:
                    next_start_ts = timestamps[i + 1] - self.asr_buffer
                    end_ts = min(end_ts, next_start_ts - MIN_SEGMENT_GAP)  # Add a small gap to avoid overlap
                expanded_timestamps.append(end_ts)

        segment_times = ",".join(
            str(ts) for ts in expanded_timestamps[1:]
        )  # Drop the first timestamp (0) as it is implicit

        extension = "wav" if use_wav else Path(audio_file).suffix.lstrip(".")

        if extension in ["m4b", "m4a", "mp4"]:
            extension = "aac"  # Use aac for segment extraction to avoid issues with m4b/m4a/mp4 containers

        output_pattern = os.path.join(output_dir, f"segment_%03d.{extension}")

        # noinspection SpellCheckingInspection
        command = [
            "ffmpeg",
            "-y",
            "-i",
            audio_file,
            "-acodec",
            "copy",  # Copy audio without re-encoding
            "-f",
            "segment",  # Segment mode
            "-segment_times",
            segment_times,  # Specify split points
            output_pattern,  # Output pattern
        ]

        if use_wav:
            command = [
                "ffmpeg",
                "-y",
                "-i",
                audio_file,
                "-f",
                "segment",  # Segment mode
                "-segment_times",
                segment_times,  # Specify split points
                output_pattern,  # Output pattern
            ]

        process = subprocess.Popen(command, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

        with self._process_lock:
            self._running_processes.append(process)

        try:
            segment_pattern = re.compile(r"Opening '.*segment.*' for writing")
            segments_created = 0
            total_segments = len(expanded_timestamps) // 2

            for line in process.stderr:
                if segment_pattern.search(line):
                    segments_created += 1
                    corrected_segments = segments_created // 2
                    # Update progress for segment creation
                    if total_segments > 0:
                        progress_percent = (corrected_segments / total_segments) * 100
                        message = f"Extracted chapter {corrected_segments} of {total_segments}..."
                        details = {"segments_created": corrected_segments, "total_segments": total_segments}

                        self._notify_progress(Step.AUDIO_EXTRACTION, progress_percent, message, details)

            process.wait()

            if process.returncode != 0:
                self.clean_up_orphaned_segment_files(output_dir)
                if process.returncode in [254, 255]:
                    # ffmpeg returns 254/255 when cancelled or input file missing
                    logger.info(f"Segment extraction was cancelled. Cleaning up...")
                    return []
                elif allow_retry and not use_wav:
                    logger.warning("Error extracting segments. Cleaning up and retrying with WAV output...")
                    return self._run_segment_extraction(audio_file, timestamps, output_dir, True, False)
                else:
                    raise subprocess.CalledProcessError(process.returncode, command)
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

        # Delete all odd-numbered segments (extended segments) and rename even-numbered ones with timestamps
        paths = []
        for idx in range(0, len(expanded_timestamps), 2):
            # Delete the extended segment (odd index)
            if idx + 1 < len(expanded_timestamps):
                extended_path = os.path.join(output_dir, f"segment_{(idx + 1):03d}.{extension}")
                if os.path.exists(extended_path):
                    os.remove(extended_path)

            # Rename the main segment (even index) with timestamp
            old_path = os.path.join(output_dir, f"segment_{idx:03d}.{extension}")
            if os.path.exists(old_path):
                # Use the original timestamp for naming
                timestamp_idx = idx // 2
                if timestamp_idx < len(timestamps):
                    timestamp_name = _timestamp_to_filename(timestamps[timestamp_idx])
                    new_path = os.path.join(output_dir, f"segment_{timestamp_name}.{extension}")
                    os.rename(old_path, new_path)
                    paths.append(new_path)

        return paths

    async def trim_segments(
        self,
        audio_files: List[str],
        copy_only: bool = False,
    ) -> List[str]:
        """Extract audio segments based on timestamps from single or multiple files"""

        self._notify_progress(Step.TRIMMING, 0, "Starting segment trimming...")

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        # Start the extraction in background
        executor_task = loop.run_in_executor(
            None,
            self._trim_segments,
            audio_files,
            copy_only,
        )

        result = await executor_task

        # Check if extraction was cancelled (empty result indicates cancellation)
        if not result:
            raise asyncio.CancelledError("Audio trimming was cancelled")

        self._notify_progress(Step.TRIMMING, 100, f"Trimmed {len(result)} segments")

        return result

    def _trim_segments(
        self,
        paths: List[str],
        copy_only: bool = False,
    ) -> List[str]:
        """Trim segments in parallel using a thread pool."""
        if not paths:
            return []

        max_workers = min(_get_worker_count(), len(paths))
        cancelled = threading.Event()
        completed_count = [0]
        total = len(paths)

        logger.info(f"Trimming {total} segments with {max_workers} parallel workers")

        results: List[Optional[str]] = [None] * total

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._trim_single_segment, i, path, copy_only, cancelled, completed_count, total
                ): i
                for i, path in enumerate(paths)
            }

            for future in as_completed(futures):
                index, trimmed_path = future.result()
                results[index] = trimmed_path

                if cancelled.is_set():
                    for f in futures:
                        f.cancel()
                    output_dir = os.path.dirname(paths[0])
                    logger.info(f"Segment trimming was cancelled. Cleaning up trimmed files in {output_dir}...")
                    self.clean_up_orphaned_trimmed_files(output_dir)
                    return []

        return [r for r in results if r is not None]

    def _trim_single_segment(
        self,
        index: int,
        path: str,
        copy_only: bool,
        cancelled: threading.Event,
        completed_count: list,
        total: int,
    ) -> Tuple[int, Optional[str]]:
        """Trim a single segment. Runs in a worker thread."""
        trimmed_path = path.replace("segment_", "trimmed_")

        def _finish_with_copy(src: str, dst: str) -> Tuple[int, Optional[str]]:
            """Copy the file and report progress."""
            shutil.copy2(src, dst)
            with self._process_lock:
                completed_count[0] += 1
                count = completed_count[0]
            self._notify_progress(
                Step.TRIMMING, (count / total) * 100,
                f"Trimmed chapter {count} of {total}...",
                {"trimmed_segments": count, "total_segments": total},
            )
            return (index, dst)

        try:
            if cancelled.is_set():
                return (index, None)

            if copy_only:
                return _finish_with_copy(path, trimmed_path)

            if cancelled.is_set():
                return (index, None)

            silences = self._sync_get_silence_boundaries(path, cancelled=cancelled)

            if cancelled.is_set():
                return (index, None)

            # Filter out silences that are too close to the beginning
            if silences:
                silences = [
                    s for s in silences if s[1] >= self.asr_buffer + MIN_TRIMMED_SEGMENT_LENGTH
                ]

            if silences:
                # Sort by duration and get the longest silence
                longest = sorted(silences, key=lambda x: (x[1] - x[0]), reverse=True)[0]
                trim_point = max(MIN_TRIMMED_SEGMENT_LENGTH, longest[0] + self.asr_buffer)

                trim_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    path,
                    "-t",
                    str(trim_point),
                    "-c",
                    "copy",
                    trimmed_path,
                ]

                process = None
                try:
                    process = subprocess.Popen(trim_cmd)

                    with self._process_lock:
                        self._running_processes.append(process)

                    process.wait()

                    if process.returncode in [-15, 254, 255]:
                        cancelled.set()
                        return (index, None)
                    elif process.returncode != 0:
                        logger.error(
                            f"Failed to trim segment {path}, will use untrimmed copy:\nExit code {process.returncode}"
                        )
                        shutil.copy2(path, trimmed_path)
                finally:
                    if process is not None:
                        with self._process_lock:
                            try:
                                self._running_processes.remove(process)
                            except ValueError:
                                pass

            # If no silences were found, just copy the file without trimming
            if not silences:
                shutil.copy2(path, trimmed_path)

            with self._process_lock:
                completed_count[0] += 1
                count = completed_count[0]
            self._notify_progress(
                Step.TRIMMING, (count / total) * 100,
                f"Trimmed chapter {count} of {total}...",
                {"trimmed_segments": count, "total_segments": total},
            )

            return (index, trimmed_path)

        except Exception as e:
            logger.warning(f"Failed to trim segment {path}: {e}")
            try:
                return _finish_with_copy(path, trimmed_path)
            except Exception:
                return (index, None)

    def _sync_get_silence_boundaries(
        self,
        input_file: str,
        silence_threshold: float = -30,
        cancelled: Optional[threading.Event] = None,
    ) -> Optional[List[Tuple[float, float]]]:
        """Synchronous version of silence detection for use in threads."""
        if cancelled and cancelled.is_set():
            return None

        # noinspection SpellCheckingInspection
        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-af",
            f"silencedetect=n={silence_threshold}dB:d={MIN_SILENCE_DURATION}",
            "-f",
            "null",
            "-",
        ]

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

        with self._process_lock:
            self._running_processes.append(process)

        try:
            silence_starts = []
            silence_ends = []

            pattern_start = re.compile(r"silence_start:\s*([\d\.]+)")
            pattern_end = re.compile(r"silence_end:\s*([\d\.]+)")

            for line in process.stderr:
                if "silence_start" in line:
                    match = pattern_start.search(line)
                    if match:
                        timestamp = float(match.group(1))
                        silence_starts.append(timestamp)
                elif "silence_end" in line:
                    match = pattern_end.search(line)
                    if match:
                        timestamp = float(match.group(1))
                        silence_ends.append(timestamp)

            process.wait()

            if process.returncode in [-15, 254, 255]:
                logger.info(f"Silence detection was cancelled. Cleaning up...")
                if cancelled:
                    cancelled.set()
                return None
            if process.returncode != 0:
                logger.error(
                    f"ffmpeg silence detection failed in _sync_get_silence_boundaries with return code {process.returncode}"
                )
                return None

            silences = list(zip(silence_starts, silence_ends))
            return silences
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

    async def concat_files(
        self,
        input_files: List[str],
        total_duration: Optional[float] = None,
    ) -> Optional[str]:
        """Concatenate multiple audio files into one"""

        self._notify_progress(Step.FILE_PREP, 0, "Preparing files...")

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        # Start the concatenation in background
        executor_task = loop.run_in_executor(None, self._run_concat_files, input_files, total_duration)

        output_file = await executor_task

        if not output_file:
            logger.info("File concatenation was cancelled or failed")
            return None

        self._notify_progress(Step.FILE_PREP, 100, "File prep completed...")
        return output_file

    def _run_concat_files(
        self,
        input_files: List[str],
        total_duration: Optional[float] = None,
    ) -> Optional[str]:
        """
        Concatenate multiple audio files into one using ffmpeg concat demuxer.
        Returns the output file path, or None on failure.
        """
        if not input_files or len(input_files) < 2:
            logger.error("At least two input files are required for concatenation.")
            return None

        # Determine output extension from first file
        ext = Path(input_files[0]).suffix.lstrip(".")
        if ext in ["m4b", "m4a", "mp4"]:
            ext = "aac"
        output_file = os.path.join(os.path.dirname(input_files[0]), "concatenated." + ext)

        if not total_duration:
            self._notify_progress(Step.FILE_PREP, 0, "Preparing files, please wait...")

        # Create a temporary file list for ffmpeg concat demuxer
        filelist_path = os.path.join(os.path.dirname(input_files[0]), "concat_filelist.txt")
        try:
            with open(filelist_path, "w", encoding="utf-8") as f:
                for path in input_files:
                    # Escape single quotes in filenames
                    escaped_path = path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                "ffmpeg",
                "-y",
                "-progress",
                "pipe:2",
                "-stats_period",
                "0.1",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                filelist_path,
                "-map",
                "0:a",
                "-c",
                "copy",
                output_file,
            ]
            process = subprocess.Popen(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace"
            )
            with self._process_lock:
                self._running_processes.append(process)

            stderr_output = []

            # Parse progress output in real-time
            current_time = 0.0
            last_progress_update = 0.0

            for line in process.stderr:
                line = line.strip()
                stderr_output.append(line)

                # Parse time progress from ffmpeg output
                if total_duration and line.startswith("out_time_ms="):
                    try:
                        time_ms = int(line.split("=")[1])
                        current_time = time_ms / 1000000.0  # Convert microseconds to seconds

                        # Update progress if we have total duration and significant progress change
                        if current_time > last_progress_update + 1.0:  # Update every second
                            progress_percent = min((current_time / total_duration) * 100, 100)

                            # Format time display
                            current_time_str = _format_time(current_time)
                            total_time_str = _format_time(total_duration)

                            message = f"Preparing files... ({current_time_str} / {total_time_str})"
                            details = {
                                "current_time": current_time,
                                "total_duration": total_duration,
                                "files_count": len(input_files),
                            }

                            self._notify_progress(Step.FILE_PREP, progress_percent, message, details)

                            last_progress_update = current_time

                    except (ValueError, IndexError):
                        pass
                elif line.startswith("progress=") and line.endswith("end"):
                    # Concatenation completed
                    if total_duration:
                        self._notify_progress(
                            Step.FILE_PREP,
                            100.0,
                            "File concatenation completed",
                            {
                                "current_time": total_duration,
                                "total_duration": total_duration,
                                "files_count": len(input_files),
                            },
                        )

            # Wait for process to complete
            process.wait()

            if process.returncode != 0:
                logger.error(
                    f"ffmpeg concat failed with return code {process.returncode}.\nffmpeg output:\n"
                    + "\n".join(stderr_output)
                )
                return None

            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                logger.error(
                    f"Concatenated output file was not created or is empty: {output_file}.\nffmpeg output:\n"
                    + "\n".join(stderr_output)
                )
                return None

            return output_file
        except Exception as e:
            logger.error(f"Exception during file concatenation: {e}")
            return None
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass
            if os.path.exists(filelist_path):
                try:
                    os.remove(filelist_path)
                except Exception:
                    pass
