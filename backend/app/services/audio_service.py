import asyncio
import functools
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from pathlib import Path
from typing import List, Tuple, Optional

from app.core.config import get_app_config
from app.core.constants import (
    CHAPTER_START_PADDING,
    MIN_SEGMENT_GAP,
    MIN_SILENCE_DURATION,
    MIN_TRIMMED_SEGMENT_LENGTH,
)
from app.core.system_info import get_worker_count
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


# Matches the first audio stream line ffmpeg prints to stderr
_AUDIO_STREAM_RE = re.compile(r"Stream #\d+[:.\d\[\]\w()]*: Audio:\s+([\w\-]+)")


@functools.lru_cache(maxsize=32)
def _ffmpeg_probe_stderr(audio_file: str) -> str:
    """Run `ffmpeg -i` and return stderr. ffmpeg exits non-zero because no output
    was specified, but the stream header info is still printed to stderr."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", audio_file],
            capture_output=True, text=True, timeout=30,
        )
        return result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"Failed to probe audio file {audio_file}: {e}")
        return ""


def audio_uses_xhe_aac(audio_file: str) -> bool:
    """Return True if ffmpeg reports the audio stream as xHE-AAC."""
    return "xhe-aac" in _ffmpeg_probe_stderr(audio_file).lower()


def get_audio_codec(audio_file: str) -> Optional[str]:
    """Return the codec name of the first audio stream as reported by ffmpeg,
    or None if the probe failed or no audio stream was found."""
    match = _AUDIO_STREAM_RE.search(_ffmpeg_probe_stderr(audio_file))
    return match.group(1).lower() if match else None


# Containers where the default ffmpeg muxer (inferred from extension) can reject
# streams whose codec doesn't match the container's typical codec. For these,
# pick an output extension based on the actual audio codec so `-c copy` succeeds.
_REMUX_CONTAINER_EXTS = {"m4b", "m4a", "mp4"}

# Container/codec extensions whose muxer writes packets sequentially without
# seeking back to rewrite headers on close. Safe to redirect to /dev/null
# via a symlink (see _extract_range_block). WAV/FLAC/M4A/MP4/OGG all patch
# headers at trailer-write time and would fail against a non-seekable sink.
_NULL_SINK_SAFE_EXTS = {"aac", "mp3", "ac3", "eac3"}

# Map of audio codec (from ffprobe) to a compatible raw/container extension.
_CODEC_EXT_MAP = {
    "mp3": "mp3",
    "aac": "aac",
    "alac": "m4a",
    "flac": "flac",
    "opus": "opus",
    "vorbis": "ogg",
    "ac3": "ac3",
    "eac3": "eac3",
}


def pick_segment_extension(audio_file: str, fallback_ext: Optional[str] = None) -> str:
    """Choose an output file extension suitable for `ffmpeg -c copy` segments.

    For M4A/M4B/MP4 containers we probe the actual audio codec and pick a matching
    extension, since the default muxer inferred from `.m4b` etc. (ipod) only accepts
    AAC. For other containers, keep the original extension.
    """
    ext = (fallback_ext if fallback_ext is not None else Path(audio_file).suffix.lstrip(".")).lower()
    if ext not in _REMUX_CONTAINER_EXTS:
        return ext
    codec = get_audio_codec(audio_file)
    if codec and codec in _CODEC_EXT_MAP:
        return _CODEC_EXT_MAP[codec]
    # Default: AAC is the canonical codec for these containers.
    return "aac"


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
            self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Starting audio analysis…")

        num_workers = get_worker_count()
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
                            message = f"Analyzing audio… ({_format_time(timestamp)} / {_format_time(duration)})"

                            # Throttle feed_text to max 2 updates/sec
                            cue_count = len(silence_ends)
                            now = time.monotonic()
                            details = None
                            if now - last_feed_time >= 0.2:
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
                    raise RuntimeError(
                        f"ffmpeg silence detection failed with return code {process.returncode}"
                    )

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
        last_progress_time: list,
        finishing: threading.Event,
        progress_lock: threading.Lock,
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
            "-progress", "pipe:2",
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
            pattern_progress = re.compile(r"out_time=(\d+):(\d+):([\d.]+)")

            # Monotonic floor for progress timestamps. silencedetect reports
            # input-stream time while -progress out_time reports the muxer's
            # output position, and the two can drift wildly apart when the
            # decoder produces few frames (e.g. repeated AAC decode errors on
            # the first worker pin out_time near 0 while silencedetect is
            # already minutes in). Clamping to max_progress_ts prevents the
            # slot from bouncing backwards.
            max_progress_ts = 0.0

            for line in process.stderr:
                if cancelled.is_set():
                    process.terminate()
                    process.wait()
                    return None

                local_ts = None
                is_silence_end = False

                if "silence_start" in line:
                    match = pattern_start.search(line)
                    if match:
                        silence_starts.append(float(match.group(1)) + seek)
                    continue
                elif "silence_end" in line:
                    match = pattern_end.search(line)
                    if match:
                        local_ts = float(match.group(1))
                        silence_ends.append(local_ts + seek)
                        is_silence_end = True
                elif "out_time=" in line:
                    match = pattern_progress.search(line)
                    if match:
                        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
                        local_ts = h * 3600 + m * 60 + s

                if local_ts is None:
                    continue

                if local_ts > max_progress_ts:
                    max_progress_ts = local_ts

                with progress_lock:
                    if segment_duration > 0:
                        worker_progress[worker_index] = min(
                            (max_progress_ts / segment_duration) * 100, 100
                        )

                    avg_progress = sum(worker_progress) / len(worker_progress)
                    virtual_ts = (avg_progress / 100) * duration
                    message = f"Analyzing audio… ({_format_time(virtual_ts)} / {_format_time(duration)})"

                    details = None
                    if is_silence_end:
                        cue_counter[0] += 1
                        cue_count = cue_counter[0]

                        now = time.monotonic()
                        if now - last_feed_time[0] >= 0.2:
                            details = {
                                "feed_text": f"Found {cue_count} potential chapter cue{'s' if cue_count != 1 else ''}"
                            }
                            last_feed_time[0] = now

                    last_progress_time[0] = time.monotonic()
                    if not finishing.is_set():
                        self._notify_progress(Step.AUDIO_ANALYSIS, avg_progress, message, details)

            process.wait()

            if process.returncode in [-15, 254, 255]:
                cancelled.set()
                return None
            if process.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg silence detection worker {worker_index} failed with return code {process.returncode}"
                )

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
        num_workers = get_worker_count()
        segments = _compute_virtual_segments(duration, num_workers)
        cancelled = threading.Event()
        worker_progress = [0.0] * len(segments)
        cue_counter = [0]
        last_feed_time = [0.0]
        last_progress_time = [time.monotonic()]
        finishing = threading.Event()
        progress_lock = threading.Lock()

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
                    cue_counter, last_feed_time, last_progress_time, finishing,
                    progress_lock,
                ): i
                for i, (seek, seg_dur) in enumerate(segments)
            }

            pending = set(futures.keys())

            while pending:
                done, pending = wait(pending, timeout=0.5)

                if cancelled.is_set():
                    for f in futures.keys():
                        f.cancel()
                    return None

                for future in done:
                    try:
                        result = future.result()
                    except Exception:
                        # Signal other workers to stop, let the executor drain,
                        # and propagate the failure so the pipeline can fail
                        # detection as a whole instead of proceeding with
                        # partial results.
                        cancelled.set()
                        raise

                    if result:
                        all_silences.extend(result)

                if not finishing.is_set() and pending:
                    avg_progress = sum(worker_progress) / len(worker_progress)
                    if avg_progress > 95.0 and (time.monotonic() - last_progress_time[0]) > 0.5:
                        self._notify_progress(Step.AUDIO_ANALYSIS, -1, "Processing results…")
                        finishing.set()

        if not finishing.is_set():
            self._notify_progress(Step.AUDIO_ANALYSIS, -1, "Processing results…")

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

        self._notify_progress(Step.AUDIO_EXTRACTION, 0, "Starting chapter audio extraction…")

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

    def _run_parallel_range_extraction(
        self,
        audio_file: str,
        ranges: List[Tuple[float, float]],
        output_dir: str,
        use_wav: bool,
        allow_retry: bool,
        name_timestamps: Optional[List[float]] = None,
    ) -> List[str]:
        """Extract a list of [start, end) ranges in parallel.

        Ranges are sorted and partitioned into at most `num_workers` contiguous
        blocks. Each block runs as one ffmpeg invocation with an input-side
        `-ss`/`-t` so that worker only demuxes its own portion of the source
        file. Within each block we use ffmpeg's segment muxer with timestamps
        relative to the block start, splitting the kept ranges out from the 
        inter-range gaps.

        `name_timestamps`, when provided, gives the timestamp to use for each
        output file's name (segment_<ms>.ext). If None, each range's own start
        timestamp is used. Must be the same length as `ranges` when provided.
        """
        if not ranges:
            return []

        if name_timestamps is not None and len(name_timestamps) != len(ranges):
            raise ValueError("name_timestamps must match ranges in length")

        # Attach names to ranges so sorting keeps them in sync.
        effective_names = (
            name_timestamps if name_timestamps is not None
            else [r[0] for r in ranges]
        )
        indexed = sorted(
            zip(ranges, effective_names), key=lambda pair: pair[0][0]
        )
        sorted_ranges = [r for r, _ in indexed]
        sorted_names = [n for _, n in indexed]

        num_workers = get_worker_count()
        num_blocks = max(1, min(num_workers, len(sorted_ranges)))

        # Split into balanced contiguous blocks — index-range slicing so
        # neighboring ranges stay together (amortizes the input-seek)
        k, m = divmod(len(sorted_ranges), num_blocks)
        blocks: List[List[Tuple[float, float]]] = []
        block_names: List[List[float]] = []
        pos = 0
        for i in range(num_blocks):
            size = k + (1 if i < m else 0)
            if size:
                blocks.append(sorted_ranges[pos:pos + size])
                block_names.append(sorted_names[pos:pos + size])
            pos += size

        extension = "wav" if use_wav else pick_segment_extension(audio_file)
        cancelled = threading.Event()
        completed = [0]
        progress_lock = threading.Lock()
        total = len(sorted_ranges)

        logger.debug(
            f"Parallel range extraction: {total} ranges across {len(blocks)} blocks"
        )
        extraction_start = time.monotonic()

        block_results: List[Optional[List[str]]] = [None] * len(blocks)
        worker_failed = False

        with ThreadPoolExecutor(max_workers=len(blocks)) as executor:
            futures = {
                executor.submit(
                    self._extract_range_block,
                    block_idx, block, names, audio_file, output_dir, extension,
                    cancelled, completed, progress_lock, total,
                ): block_idx
                for block_idx, (block, names) in enumerate(zip(blocks, block_names))
            }

            for future in as_completed(futures):
                block_idx = futures[future]
                try:
                    paths = future.result()
                except Exception:
                    cancelled.set()
                    worker_failed = True
                    logger.exception(f"Range extraction block {block_idx} failed")
                    continue
                if paths is None:
                    cancelled.set()
                    continue
                block_results[block_idx] = paths

        if cancelled.is_set():
            self._cleanup_range_block_outputs(output_dir, len(blocks), extension)
            self.clean_up_orphaned_segment_files(output_dir)
            if worker_failed and allow_retry and not use_wav:
                logger.warning("Parallel range extraction failed; retrying with WAV")
                return self._run_parallel_range_extraction(
                    audio_file, ranges, output_dir, True, False, name_timestamps,
                )
            return []

        all_paths: List[str] = []
        for paths in block_results:
            if paths:
                all_paths.extend(paths)
        logger.info(
            f"Parallel range extraction finished: {total} ranges across "
            f"{len(blocks)} blocks in {time.monotonic() - extraction_start:.2f}s"
        )
        return all_paths

    def _extract_range_block(
        self,
        block_idx: int,
        block: List[Tuple[float, float]],
        name_timestamps: List[float],
        audio_file: str,
        output_dir: str,
        extension: str,
        cancelled: threading.Event,
        completed: list,
        progress_lock: threading.Lock,
        total: int,
    ) -> Optional[List[str]]:
        """Extract one contiguous block of ranges.

        Returns the extracted segment paths in input order, or None if this
        block was cancelled or failed."""
        if not block or cancelled.is_set():
            return []

        block_start_time = time.monotonic()
        b_start = block[0][0]
        b_end = block[-1][1]

        # Flatten (start, end) into alternating timestamps. The first (b_start)
        # becomes our input-seek target; the remaining timestamps become the
        # segment muxer split points relative to b_start.
        expanded: List[float] = []
        for start, end in block:
            expanded.append(start)
            expanded.append(end)
        splits_rel = [t - b_start for t in expanded[1:]]
        segment_times_str = ",".join(f"{t:.6f}" for t in splits_rel)

        block_prefix = f"xrng{block_idx:02d}_"
        output_pattern = os.path.join(output_dir, f"{block_prefix}%03d.{extension}")
        use_copy = extension != "wav"

        # Gap segments (odd indices) are pure overhead — ffmpeg must write them
        # so the segment muxer can split at our range boundaries. For codecs
        # whose muxer doesn't seek back on close, pre-creating each gap path
        # as a symlink to /dev/null makes those writes no-ops at the kernel
        # level, avoiding disk thrashing.
        use_null_gaps = extension in _NULL_SINK_SAFE_EXTS
        if use_null_gaps:
            for gap_idx in range(1, 2 * len(block), 2):
                gap_path = os.path.join(
                    output_dir, f"{block_prefix}{gap_idx:03d}.{extension}"
                )
                try:
                    try:
                        os.unlink(gap_path)
                    except FileNotFoundError:
                        pass
                    os.symlink("/dev/null", gap_path)
                except OSError:
                    logger.debug(
                        f"Null-sink symlink failed at {gap_path}; "
                        f"falling back to real gap writes for this block."
                    )
                    for cleanup_idx in range(1, gap_idx, 2):
                        stale = os.path.join(
                            output_dir,
                            f"{block_prefix}{cleanup_idx:03d}.{extension}",
                        )
                        try:
                            os.unlink(stale)
                        except OSError:
                            pass
                    break

        # noinspection SpellCheckingInspection
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{b_start:.6f}",
            "-t", f"{b_end - b_start:.6f}",
            "-i", audio_file,
        ]
        if use_copy:
            cmd.extend(["-acodec", "copy"])
        cmd.extend([
            "-f", "segment",
            "-segment_times", segment_times_str,
            output_pattern,
        ])

        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        with self._process_lock:
            self._running_processes.append(process)

        try:
            open_pattern = re.compile(
                r"Opening '.*" + re.escape(block_prefix) + r"\d+\."
                + re.escape(extension) + r"' for writing"
            )
            block_opens = 0
            for line in process.stderr or []:
                if cancelled.is_set():
                    process.terminate()
                    break
                if open_pattern.search(line):
                    block_opens += 1
                    # Every even-numbered open (2, 4, 6, …) marks the close of
                    # a kept segment (output 0, 2, 4, …). Odd opens are gap
                    # segments; don't count them toward progress.
                    if block_opens >= 2 and block_opens % 2 == 0:
                        with progress_lock:
                            completed[0] += 1
                            if total > 0:
                                pct = min((completed[0] / total) * 100, 99.0)
                                self._notify_progress(
                                    Step.AUDIO_EXTRACTION, pct,
                                    f"Extracted chapter {completed[0]} of {total}…",
                                    {
                                        "segments_created": completed[0],
                                        "total_segments": total,
                                    },
                                )
            process.wait()
            if cancelled.is_set() or process.returncode in [254, 255]:
                return None
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)
        finally:
            with self._process_lock:
                try:
                    self._running_processes.remove(process)
                except ValueError:
                    pass

        # Rename kept outputs (even indices) to their timestamped names and
        # delete the gap outputs (odd indices).
        paths: List[str] = []
        for seg_idx in range(len(block)):
            kept = os.path.join(
                output_dir, f"{block_prefix}{2 * seg_idx:03d}.{extension}"
            )
            if os.path.exists(kept):
                name_ts = name_timestamps[seg_idx]
                dst = os.path.join(
                    output_dir, f"segment_{int(name_ts * 1000)}.{extension}"
                )
                os.rename(kept, dst)
                paths.append(dst)
            gap = os.path.join(
                output_dir, f"{block_prefix}{2 * seg_idx + 1:03d}.{extension}"
            )
            if os.path.exists(gap):
                os.remove(gap)

        logger.debug(
            f"  block {block_idx} ({len(block)} ranges, "
            f"{b_start:.1f}s–{b_end:.1f}s) in "
            f"{time.monotonic() - block_start_time:.2f}s"
        )
        return paths

    def _cleanup_range_block_outputs(
        self, output_dir: str, num_blocks: int, extension: str,
    ):
        """Remove any leftover xrngNN_* files from a cancelled/failed run."""
        for filename in os.listdir(output_dir):
            if filename.startswith("xrng") and filename.endswith(f".{extension}"):
                try:
                    os.remove(os.path.join(output_dir, filename))
                except Exception:
                    pass

    def _run_segment_extraction(
        self,
        audio_file: str,
        timestamps: List[float] | List[Tuple[float, float]],
        output_dir: str,
        use_wav: bool = False,
        allow_retry: bool = True,
    ) -> List[str]:
        """Run segment extraction in a separate thread.

        Both input shapes (float cue timestamps for ASR extraction, and
        [start, end) tuples for realignment) funnel through the parallel
        range-extraction path — each worker demuxes only its own portion of
        the source so the per-invocation container-parse cost is paid once
        per worker rather than once per range.
        """
        if not timestamps:
            return []

        if isinstance(timestamps[0], tuple):
            return self._run_parallel_range_extraction(
                audio_file, timestamps, output_dir,  # type: ignore[arg-type]
                use_wav, allow_retry,
            )

        # Float cue timestamps: derive (start, end) ranges using the ASR
        # segment-length / next-cue overlap-avoidance rules, and preserve the
        # original cue timestamps as the naming keys.
        cue_timestamps: List[float] = list(timestamps)  # type: ignore[arg-type]
        segment_length = get_app_config().asr_options.segment_length
        ranges: List[Tuple[float, float]] = []
        for i, ts in enumerate(cue_timestamps):
            start_ts = max(0, ts - self.asr_buffer)
            end_ts = ts + segment_length
            if i < len(cue_timestamps) - 1:
                next_start_ts = cue_timestamps[i + 1] - self.asr_buffer
                end_ts = min(end_ts, next_start_ts - MIN_SEGMENT_GAP)
            ranges.append((start_ts, end_ts))

        return self._run_parallel_range_extraction(
            audio_file, ranges, output_dir, use_wav, allow_retry,
            name_timestamps=cue_timestamps,
        )

    async def trim_segments(
        self,
        audio_files: List[str],
        copy_only: bool = False,
    ) -> List[str]:
        """Extract audio segments based on timestamps from single or multiple files"""

        self._notify_progress(Step.TRIMMING, 0, "Starting segment trimming…")

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

        max_workers = min(get_worker_count(), len(paths))
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
                    logger.info(f"Segment trimming was cancelled. Cleaning up trimmed files in {output_dir}…")
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
                    f"Trimmed chapter {count} of {total}…",
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
                    f"Trimmed chapter {count} of {total}…",
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
                logger.info(f"Silence detection was cancelled. Cleaning up…")
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

        self._notify_progress(Step.FILE_PREP, 0, "Preparing files…")

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        # Start the concatenation in background
        executor_task = loop.run_in_executor(None, self._run_concat_files, input_files, total_duration)

        output_file = await executor_task

        if not output_file:
            logger.info("File concatenation was cancelled or failed")
            return None

        self._notify_progress(Step.FILE_PREP, 100, "File prep completed…")
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
        ext = pick_segment_extension(input_files[0])
        output_file = os.path.join(os.path.dirname(input_files[0]), "concatenated." + ext)

        if not total_duration:
            self._notify_progress(Step.FILE_PREP, -1, "Preparing files, please wait…")

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

                            message = f"Preparing files… ({current_time_str} / {total_time_str})"
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
