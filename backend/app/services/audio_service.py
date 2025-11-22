import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    """Convert seconds to hh:mm:ss format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class AudioProcessingService:
    """Service for audio processing operations using ffmpeg"""

    def __init__(self, progress_callback: ProgressCallback, smart_detect_config=None, running_processes=None):
        self.progress_callback: ProgressCallback = progress_callback
        self._progress_queue = []
        self._running_processes = running_processes if running_processes is not None else []

        # Use smart detect config if provided, otherwise use defaults
        if smart_detect_config:
            self.segment_length = smart_detect_config.segment_length
            self.min_clip_length = smart_detect_config.min_clip_length
            self.asr_buffer = smart_detect_config.asr_buffer
            self.min_silence_duration = smart_detect_config.min_silence_duration
        else:
            # Default values (same as before)
            self.segment_length = 8.0
            self.min_clip_length = 1.0
            self.asr_buffer = 0.25
            self.min_silence_duration = 2

    def _notify_progress(self, step: Step, percent: float, message: str = "", details: dict = None):
        """Notify progress via callback"""
        self.progress_callback(step, percent, message, details or {})

    async def _process_queued_progress(self):
        """Process any queued progress updates from thread"""
        if not self._progress_queue or not self.progress_callback:
            return

        # Process all queued progress updates
        while self._progress_queue:
            progress_data = self._progress_queue.pop(0)
            try:
                self.progress_callback(
                    progress_data["step"],
                    progress_data["percent"],
                    progress_data["message"],
                    progress_data["details"],
                )
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

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
        input_file: List[str],
        silence_threshold: float = -30,
        min_silence_duration: float = None,
        duration: Optional[float] = None,
        publish_progress: bool = True,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Detect silence boundaries in audio files using ffmpeg.
        Can handle single file (for backward compatibility) or multiple files.
        Returns a list of tuples containing (silence_start, silence_end) timestamps.
        For multiple files, timestamps are adjusted to a continuous timeline.
        """
        if min_silence_duration is None:
            min_silence_duration = self.min_silence_duration

        if publish_progress:
            self._notify_progress(Step.AUDIO_ANALYSIS, 0, "Starting audio analysis...")

        all_silences = []

        # noinspection SpellCheckingInspection
        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-af",
            f"silencedetect=n={silence_threshold}dB:d={min_silence_duration}",
            "-f",
            "null",
            "-",
        ]

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()

        executor_task = loop.run_in_executor(
            None,
            self._run_silence_detection,
            cmd,
            duration,
        )

        # Process queued progress updates while waiting
        while not executor_task.done():
            await self._process_queued_progress()
            await asyncio.sleep(0.1)  # Brief sleep to avoid busy loop

        # Get the result for this file
        file_silences = await executor_task

        # Check if processing was cancelled
        if file_silences is None:
            logger.info("Silence detection was cancelled, returning None")
            return None

        all_silences.extend(file_silences)

        if publish_progress:
            # Process any remaining progress updates
            await self._process_queued_progress()

            self._notify_progress(Step.AUDIO_ANALYSIS, 100, f"Found {len(all_silences)} potential chapter breaks")

        return all_silences

    def _run_silence_detection(
        self,
        cmd: List[str],
        duration: Optional[float],
        publish_progress: bool = True,
    ) -> Optional[List[Tuple[float, float]]]:
        """Run silence detection in a separate thread"""
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

        self._running_processes.append(process)

        try:
            silence_starts = []
            silence_ends = []

            pattern_start = re.compile(r"silence_start:\s*([\d\.]+)")
            pattern_end = re.compile(r"silence_end:\s*([\d\.]+)")

            last_progress = 0.0

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

                            # Store progress for later async processing
                            self._progress_queue.append(
                                {
                                    "step": Step.AUDIO_ANALYSIS,
                                    "percent": file_progress,
                                    "message": message,
                                    "details": None,
                                }
                            )

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
            try:
                self._running_processes.remove(process)
            except ValueError:
                pass

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

        # Process queued progress updates while waiting
        while not executor_task.done():
            await self._process_queued_progress()
            await asyncio.sleep(0.1)  # Brief sleep to avoid busy loop

        # Get the result
        result = await executor_task

        # Process any remaining progress updates
        await self._process_queued_progress()

        # Check if extraction was cancelled (empty result could indicate cancellation)
        if not result:
            logger.info("Audio extraction was cancelled or failed")
            return None

        self._notify_progress(Step.AUDIO_EXTRACTION, 100, f"Extracted audio for {len(result)} chapters")

        return result

    def _trim_segment(self, segment_path: str, extension: str):
        """Trim a segment at its longest silence"""
        silences = self._sync_get_silence_boundaries(segment_path, min_silence_duration=1.0)

        # Filter out silences before the first 2 seconds
        if silences:
            silences = [s for s in silences if s[1] >= 2.0]

        if silences:
            # Sort by duration and get the longest silence
            longest = sorted(silences, key=lambda x: (x[1] - x[0]), reverse=True)[0]
            trim_point = longest[0] + 0.5  # Add 0.5s to avoid cutting off speech

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
            for i, ts in enumerate(timestamps):
                expanded_timestamps.append(ts)  # Original timestamp
                # Calculate additional timestamp (segment_length seconds later)
                extra_ts = ts + self.segment_length
                # Check if the extra timestamp overlaps with the next original timestamp
                if i < len(timestamps) - 1 and extra_ts >= timestamps[i + 1] - self.min_clip_length:
                    # Set it to min_clip_length before the next timestamp if it would overlap
                    extra_ts = timestamps[i + 1] - self.min_clip_length
                expanded_timestamps.append(extra_ts)

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

        process = subprocess.Popen(command, stderr=subprocess.PIPE, text=True)

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

                        # Store progress for later async processing
                        self._progress_queue.append(
                            {
                                "step": Step.AUDIO_EXTRACTION,
                                "percent": progress_percent,
                                "message": message,
                                "details": details,
                            }
                        )

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

        # Process queued progress updates while waiting
        while not executor_task.done():
            await self._process_queued_progress()
            await asyncio.sleep(0.1)  # Brief sleep to avoid busy loop

        # Get the result
        result = await executor_task

        # Process any remaining progress updates
        await self._process_queued_progress()

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
        """Run segment extraction in a separate thread"""
        trimmed_paths = []
        for i, path in enumerate(paths):
            try:
                # Check if any processes were terminated (indicates cancellation)
                if any(
                    proc.poll() is not None and proc.returncode in [-15, 254, 255] for proc in self._running_processes
                ):
                    output_dir = os.path.dirname(path)
                    logger.info(f"Segment trimming was cancelled. Cleaning up trimmed files in {output_dir}...")
                    self.clean_up_orphaned_trimmed_files(output_dir)
                    return []

                trimmed_path = path.replace("segment_", "trimmed_")
                trimmed_paths.append(trimmed_path)

                if copy_only:
                    shutil.copy2(path, trimmed_path)
                    continue

                # Use synchronous version for trimming (called from thread)
                silences = self._sync_get_silence_boundaries(path, min_silence_duration=1.0)

                # Filter out silences at the beginning
                # This avoids trimming too early in the audio
                # and potentially cutting off speech
                if silences:
                    silences = [s for s in silences if s[0] >= 0.5]

                if silences:
                    # Sort by duration and get the longest silence
                    longest = sorted(silences, key=lambda x: (x[1] - x[0]), reverse=True)[0]
                    trim_point = longest[0] + 0.5  # Add 0.5s to avoid cutting off speech

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

                    try:
                        process = subprocess.Popen(trim_cmd)

                        self._running_processes.append(process)

                        process.wait()

                        if process.returncode in [-15, 254, 255]:
                            output_dir = os.path.dirname(path)
                            logger.info(f"Segment trimming was cancelled. Cleaning up trimmed files in {output_dir}...")
                            self.clean_up_orphaned_trimmed_files(output_dir)
                            return []
                        elif process.returncode != 0:
                            logger.error(
                                f"Failed to trim segment {path}, will use untrimmed copy:\nExit code {process.returncode}\n{process.stderr.read()}"
                            )
                            shutil.copy2(path, trimmed_path)
                            continue
                    finally:
                        try:
                            self._running_processes.remove(process)
                        except ValueError:
                            pass

                # If no silences were found, just copy the file without trimming
                if not silences:
                    shutil.copy2(path, trimmed_path)

                # Update trimming progress
                if len(paths) > 0:
                    trim_progress = ((i + 1) / len(paths)) * 100
                    message = f"Trimmed chapter {i + 1} of {len(paths)}..."
                    details = {"trimmed_segments": i + 1, "total_segments": len(paths)}

                    # Store progress for later async processing
                    self._progress_queue.append(
                        {
                            "step": Step.TRIMMING,
                            "percent": trim_progress,
                            "message": message,
                            "details": details,
                        }
                    )

            except Exception as e:
                logger.warning(f"Failed to trim segment {path}: {e}")
                continue

        return trimmed_paths

    def _sync_get_silence_boundaries(
        self,
        input_file: str,
        silence_threshold: float = -30,
        min_silence_duration: float = None,
    ) -> Optional[List[Tuple[float, float]]]:
        """Synchronous version of silence detection for use in threads"""
        if min_silence_duration is None:
            min_silence_duration = self.min_silence_duration

        # noinspection SpellCheckingInspection
        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-af",
            f"silencedetect=n={silence_threshold}dB:d={min_silence_duration}",
            "-f",
            "null",
            "-",
        ]

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

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
                return None
            if process.returncode != 0:
                logger.error(
                    f"ffmpeg silence detection failed in _sync_get_silence_boundaries with return code {process.returncode}"
                )
                return None

            return list(zip(silence_starts, silence_ends))
        finally:
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

        # Process queued progress updates while waiting
        while not executor_task.done():
            await self._process_queued_progress()
            await asyncio.sleep(0.1)

        # Get the result
        output_file = await executor_task

        # Process any remaining progress updates
        await self._process_queued_progress()

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
            self._progress_queue.append(
                {
                    "step": Step.FILE_PREP,
                    "percent": 0,
                    "message": "Preparing files, please wait...",
                    "details": {},
                }
            )

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
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
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

                            # Queue progress update for async processing
                            self._progress_queue.append(
                                {
                                    "step": Step.FILE_PREP,
                                    "percent": progress_percent,
                                    "message": message,
                                    "details": details,
                                }
                            )

                            last_progress_update = current_time

                    except (ValueError, IndexError):
                        pass
                elif line.startswith("progress=") and line.endswith("end"):
                    # Concatenation completed
                    if total_duration:
                        self._progress_queue.append(
                            {
                                "step": Step.FILE_PREP,
                                "percent": 100.0,
                                "message": "File concatenation completed",
                                "details": {
                                    "current_time": total_duration,
                                    "total_duration": total_duration,
                                    "files_count": len(input_files),
                                },
                            }
                        )

            # Wait for process to complete
            process.wait()

            if process.returncode != 0:
                logger.error(f"ffmpeg concat failed with return code {process.returncode}.\nffmpeg output:\n" + "\n".join(stderr_output))
                return None

            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                logger.error(f"Concatenated output file was not created or is empty: {output_file}.\nffmpeg output:\n" + "\n".join(stderr_output))
                return None

            return output_file
        except Exception as e:
            logger.error(f"Exception during file concatenation: {e}")
            return None
        finally:
            try:
                self._running_processes.remove(process)
            except ValueError:
                pass
            if os.path.exists(filelist_path):
                try:
                    os.remove(filelist_path)
                except Exception:
                    pass
