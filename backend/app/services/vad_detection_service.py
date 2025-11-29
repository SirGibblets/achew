import logging
import asyncio
import numpy as np
import os
import subprocess
import tempfile
import glob
import json
import sys
from typing import List, Tuple, Dict, Optional
from sklearn.cluster import KMeans

from app.models.enums import Step
from app.models.progress import ProgressCallback

logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    """Convert seconds to hh:mm:ss format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class VadDetectionService:
    """Service for detecting chapter boundaries using Voice Activity Detection (VAD) and k-means clustering"""

    def __init__(self, progress_callback: ProgressCallback, smart_detect_config=None, running_processes=None):
        self.progress_callback: ProgressCallback = progress_callback
        self._progress_queue = []
        self._running_processes = running_processes if running_processes is not None else []
        self._vad_processes = []  # Track spawned VAD processes for cancellation
        self._is_cancelled = False  # Track cancellation state

        # Use smart detect config if provided, otherwise use defaults
        if smart_detect_config:
            self.asr_buffer = smart_detect_config.asr_buffer
            self.segment_length = smart_detect_config.segment_length
            self.min_clip_length = smart_detect_config.min_clip_length
            self.min_silence_duration = smart_detect_config.min_silence_duration
        else:
            # Default values (same as SmartDetectionService)
            self.asr_buffer = 0.25
            self.segment_length = 8.0
            self.min_clip_length = 1.0
            self.min_silence_duration = 2.0

        # VAD-specific parameters
        self.segment_duration = 600  # 10 minutes in seconds

        # Calculate number of parallel processes: 2/3 of available cores, minimum 1
        import multiprocessing

        total_cores = multiprocessing.cpu_count()
        self.max_processes = max(1, int(total_cores * 0.667))  # 2/3 of total cores
        logger.info(f"VAD service will use {self.max_processes} parallel processes ({total_cores} total cores)")

        # Get path to VAD worker script
        self.vad_worker_path = os.path.join(os.path.dirname(__file__), "vad_worker.py")
        if not os.path.exists(self.vad_worker_path):
            raise RuntimeError(f"VAD worker script not found at {self.vad_worker_path}")
        logger.info(f"VAD worker script located at: {self.vad_worker_path}")

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

    def _get_vad_worker_path(self) -> str:
        """Get path to the permanent VAD worker script"""
        return self.vad_worker_path

    def _split_audio_into_chunks(self, audio_file: str, duration: float, temp_dir: str) -> List[str]:
        """Split audio file into 10-minute chunks using efficient ffmpeg segmentation with progress monitoring"""
        logger.info(f"Splitting audio into chunks using ffmpeg segment...")

        # Check for cancellation before starting
        if self._is_cancelled:
            return []

        _, ext = os.path.splitext(audio_file)
        output_pattern = os.path.join(temp_dir, f"vad_chunk_%03d{ext}")

        # Use ffmpeg segment to efficiently split the file
        cmd = [
            "ffmpeg",
            "-y",  # -y to overwrite existing files
            "-i",
            audio_file,
            "-f",
            "segment",  # Use segment muxer
            "-segment_time",
            str(self.segment_duration),  # 10 minutes per segment
            "-c",
            "copy",
            output_pattern,
        ]

        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            self._running_processes.append(process)

            # Monitor progress by watching stderr for segment creation
            import re

            segment_pattern = re.compile(r"Opening '.*vad_chunk_(\d+)\.[^']+' for writing")
            segments_created = 0
            expected_segments = int(duration // self.segment_duration) + 1

            for line in process.stderr:
                # Check for cancellation during processing
                if self._is_cancelled:
                    logger.info("VAD audio splitting was cancelled, terminating ffmpeg process")
                    try:
                        process.terminate()
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    return []

                # Look for segment creation messages
                match = segment_pattern.search(line)
                if match:
                    segments_created += 1
                    # Queue progress update for async processing
                    self._progress_queue.append(
                        {
                            "step": Step.VAD_PREP,
                            "percent": segments_created / expected_segments * 100,
                            "message": f"Preparing...",
                            "details": {"chunks_created": segments_created},
                        }
                    )

                # Also check for any error messages
                if "Error" in line or "error" in line:
                    logger.warning(f"ffmpeg warning/error: {line.strip()}")

            process.wait()

            # Check for cancellation after process completion
            if self._is_cancelled:
                return []

            if process.returncode != 0:
                logger.error(f"ffmpeg segmentation failed with return code {process.returncode}")
                return []

        except Exception as e:
            logger.error(f"Failed to split audio: {e}")
            return []
        finally:
            try:
                self._running_processes.remove(process)
            except ValueError:
                pass

        # Find all created chunk files
        chunk_files = sorted(glob.glob(os.path.join(temp_dir, "vad_chunk_*")))
        logger.info(f"Successfully created {len(chunk_files)} audio chunks")

        return chunk_files

    async def _process_chunk_batch_subprocess(
        self,
        chunk_batch: List[Tuple[int, str]],
        vad_worker_path: str,
        progress_tracker: dict,
        segment_duration: float = None,
    ) -> List[Tuple[int, List[Tuple[float, float]]]]:
        """Process a batch of audio chunks with VAD using a single subprocess for efficiency"""
        try:
            chunk_indices = [chunk_index for chunk_index, _ in chunk_batch]
            logger.debug(f"Starting subprocess for chunk batch {[i+1 for i in chunk_indices]}")

            # Prepare chunk data for worker (format: [["chunk1.wav", 0], ["chunk2.wav", 1], ...])
            # Convert from [(chunk_index, chunk_file), ...] to [["chunk_file", chunk_index], ...]
            worker_chunk_data = [[chunk_file, chunk_index] for chunk_index, chunk_file in chunk_batch]
            chunk_data = json.dumps(worker_chunk_data)

            duration_to_use = segment_duration if segment_duration is not None else self.segment_duration

            # Create subprocess command with progress enabled
            cmd = [
                sys.executable,  # Current Python interpreter
                vad_worker_path,
                chunk_data,  # JSON array of [chunk_file, chunk_index] pairs
                str(duration_to_use),
                str(self.min_silence_duration),
                "true",  # Enable progress tracking
            ]

            # Start subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=os.getcwd()
            )

            # Track process for cancellation
            self._vad_processes.append(process)

            try:
                # Read output line by line to capture progress updates and results
                stdout_lines = []
                results = []

                async for line in process.stdout:
                    line_text = line.decode().strip()
                    stdout_lines.append(line_text)

                    if line_text.startswith("PROGRESS:"):
                        # Parse progress update and update shared tracker
                        try:
                            progress_json = line_text[9:]  # Remove "PROGRESS:" prefix
                            progress_data = json.loads(progress_json)

                            if progress_data.get("type") == "progress":
                                chunk_index = progress_data.get("chunk_index")
                                chunk_progress = progress_data.get("progress", 0)

                                # Update progress tracker for this chunk
                                if chunk_index is not None:
                                    progress_tracker[chunk_index] = chunk_progress

                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse progress data: {e}")

                    elif line_text.startswith("RESULT:"):
                        # Parse individual chunk result
                        try:
                            result_json = line_text[7:]  # Remove "RESULT:" prefix
                            result_data = json.loads(result_json)
                            results.append(result_data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse result data: {e}")

                # Wait for process to complete
                await process.wait()

                # Process all results
                final_results = []
                if process.returncode == 0:
                    for result_data in results:
                        chunk_index = result_data.get("chunk_index")
                        if result_data.get("error"):
                            # chunk_index should be an integer from the worker
                            chunk_num = chunk_index + 1 if chunk_index is not None else "unknown"
                            logger.error(f"VAD subprocess error for chunk {chunk_num}: {result_data['error']}")
                            final_results.append((chunk_index, []))
                        else:
                            # Convert gaps back to tuples
                            gaps = [tuple(gap) for gap in result_data.get("gaps", [])]
                            # chunk_index should be an integer from the worker
                            chunk_num = chunk_index + 1 if chunk_index is not None else "unknown"
                            logger.debug(f"Subprocess complete for chunk {chunk_num}: found {len(gaps)} gaps")
                            final_results.append((chunk_index, gaps))
                else:
                    logger.error(f"VAD subprocess failed for batch {chunk_indices} with code {process.returncode}")
                    if process.stderr:
                        stderr_data = await process.stderr.read()
                        logger.error(f"Stderr: {stderr_data.decode()}")
                    # Return empty results for all chunks in the batch
                    final_results = [(chunk_index, []) for chunk_index in chunk_indices]

                return final_results

            except asyncio.TimeoutError:
                logger.error(f"VAD subprocess timeout for batch {chunk_indices}")
                process.kill()
                await process.wait()
                return [(chunk_index, []) for chunk_index in chunk_indices]

        except Exception as e:
            logger.error(f"Failed to run VAD subprocess for batch {chunk_indices}: {e}", exc_info=True)
            return [(chunk_index, []) for chunk_index, _ in chunk_batch]
        finally:
            # Remove from tracking
            try:
                self._vad_processes.remove(process)
            except (ValueError, UnboundLocalError):
                pass

    async def _process_audio_chunks_async(
        self,
        chunk_files: List[str],
        vad_worker_path: str,
        total_duration: float,
    ) -> List[Tuple[float, float]]:
        """Process all audio chunks with VAD using optimized parallel subprocesses"""
        all_gaps = []

        self._check_cancellation()

        # Calculate optimal chunks per worker (distribute chunks across workers)
        total_chunks = len(chunk_files)
        chunks_per_worker = max(1, total_chunks // self.max_processes)
        if total_chunks % self.max_processes != 0:
            chunks_per_worker += 1  # Round up to ensure all chunks are processed

        logger.info(
            f"Processing {total_chunks} chunks with {self.max_processes} workers ({chunks_per_worker} chunks per worker)"
        )

        self._check_cancellation()

        # Create worker batches - each worker gets multiple chunks to process sequentially
        worker_batches = []
        for worker_id in range(self.max_processes):
            start_idx = worker_id * chunks_per_worker
            end_idx = min(start_idx + chunks_per_worker, total_chunks)

            if start_idx < total_chunks:
                # Create batch for this worker: [(chunk_index, chunk_file), ...]
                worker_batch = []
                for chunk_idx in range(start_idx, end_idx):
                    worker_batch.append((chunk_idx, chunk_files[chunk_idx]))
                worker_batches.append(worker_batch)

        # Shared progress tracker for all workers
        progress_tracker = {}
        for i in range(total_chunks):
            progress_tracker[i] = 0  # Initialize progress for all chunks

        self._check_cancellation()

        # Create subprocess tasks for each worker batch
        worker_tasks = []
        for worker_batch in worker_batches:
            if worker_batch:  # Only create task if worker has chunks to process
                task = self._process_chunk_batch_subprocess(worker_batch, vad_worker_path, progress_tracker)
                worker_tasks.append(task)

        # Create a task to monitor overall progress
        progress_task = asyncio.create_task(
            self._monitor_batch_progress(progress_tracker, 0, len(chunk_files), total_duration)
        )

        # Wait for all workers to complete
        try:
            worker_results = await asyncio.gather(*worker_tasks, return_exceptions=True)

            # Cancel progress monitoring
            progress_task.cancel()

            self._check_cancellation()

            # Process results from all workers
            for worker_result in worker_results:
                if isinstance(worker_result, Exception):
                    logger.error(f"Worker processing failed: {worker_result}")
                    continue

                # worker_result is a list of (chunk_index, gaps) tuples
                for chunk_index, gaps in worker_result:
                    all_gaps.extend(gaps)

            # Final progress update
            completed_duration = total_chunks * self.segment_duration
            self._notify_progress(
                Step.VAD_ANALYSIS,
                100,
                f"Analyzing audio... ({_format_time(completed_duration)} / {_format_time(total_duration)})",
                {"chunk": total_chunks, "total_chunks": total_chunks},
            )

            logger.info(
                f"Completed optimized VAD processing of {total_chunks} chunks using {len(worker_tasks)} workers"
            )

        except asyncio.CancelledError:
            logger.info("VAD chunk processing was cancelled")
            progress_task.cancel()
            # Kill any running subprocesses
            await self.cancel_vad_processes()
            raise
        except Exception as e:
            logger.error(f"VAD processing failed: {e}")
            progress_task.cancel()

        return all_gaps

    async def _monitor_batch_progress(
        self,
        progress_tracker: dict,
        batch_start: int,
        total_chunks: int,
        total_duration: float,
    ):
        """Monitor and report averaged progress across all workers"""
        last_update_time = 0

        try:
            while True:
                # Check for cancellation
                if self._is_cancelled:
                    break

                current_time = asyncio.get_event_loop().time()

                # Throttle updates to every 0.1 seconds
                if current_time - last_update_time >= 0.1:
                    # Calculate overall progress across all chunks
                    if progress_tracker:
                        avg_progress = sum(progress_tracker.values()) / len(progress_tracker)

                        # Calculate completed chunks for display
                        completed_chunks = (avg_progress / 100.0) * total_chunks
                        current_duration = completed_chunks * self.segment_duration

                        if avg_progress < 0.01:
                            self._notify_progress(Step.VAD_ANALYSIS, 0, "Starting analysis, please wait...")
                        else:
                            self._notify_progress(
                                Step.VAD_ANALYSIS,
                                avg_progress,
                                f"Analyzing audio... ({_format_time(current_duration)} / {_format_time(total_duration)})",
                                {"chunk": int(completed_chunks), "total_chunks": total_chunks},
                            )

                        last_update_time = current_time

                await asyncio.sleep(0.05)  # Check progress every 50ms

        except asyncio.CancelledError:
            pass  # Expected when processing completes

    async def cancel_vad_processes(self):
        """Cancel all running VAD subprocesses"""
        self._is_cancelled = True
        if self._vad_processes:
            logger.info(f"Cancelling {len(self._vad_processes)} VAD processes...")
            for process in self._vad_processes:
                try:
                    if process.returncode is None:  # Process still running
                        process.kill()
                        await process.wait()
                except Exception as e:
                    logger.warning(f"Error killing VAD process: {e}")

            self._vad_processes.clear()

    def _check_cancellation(self):
        """Check if processing should be cancelled"""
        if self._is_cancelled:
            raise asyncio.CancelledError("VAD processing was cancelled")

    def _find_gaps_in_speech(
        self,
        speech_timestamps: List[Dict],
        segment_start: float,
        segment_end: float,
    ) -> List[Tuple[float, float]]:
        """Find gaps between speech segments and convert to global timeline"""
        gaps = []

        if not speech_timestamps:
            # If no speech detected, treat entire segment as silence
            if segment_end - segment_start >= self.min_silence_duration:
                gaps.append((segment_start, segment_end))
            return gaps

        # Sort speech timestamps by start time
        speech_timestamps.sort(key=lambda x: x["start"])

        # Check for gap at the beginning of segment
        first_speech_start = speech_timestamps[0]["start"] + segment_start
        if first_speech_start - segment_start >= self.min_silence_duration:
            gaps.append((segment_start, first_speech_start))

        # Check for gaps between speech segments
        for i in range(len(speech_timestamps) - 1):
            current_end = speech_timestamps[i]["end"] + segment_start
            next_start = speech_timestamps[i + 1]["start"] + segment_start
            gap_duration = next_start - current_end

            if gap_duration >= self.min_silence_duration:
                gaps.append((current_end, next_start))

        # Check for gap at the end of segment
        last_speech_end = speech_timestamps[-1]["end"] + segment_start
        if segment_end - last_speech_end >= self.min_silence_duration:
            gaps.append((last_speech_end, segment_end))

        return gaps

    def _merge_overlapping_gaps(self, all_gaps: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Merge overlapping silence gaps from different segments"""
        if not all_gaps:
            return []

        # Sort gaps by start time
        sorted_gaps = sorted(all_gaps, key=lambda x: x[0])
        merged_gaps = [sorted_gaps[0]]

        for current_gap in sorted_gaps[1:]:
            last_gap = merged_gaps[-1]

            # Check if gaps overlap or are very close (within 1 second)
            if current_gap[0] <= last_gap[1] + 1.0:
                # Merge gaps by extending the end time
                merged_gaps[-1] = (last_gap[0], max(last_gap[1], current_gap[1]))
            else:
                # Add as separate gap
                merged_gaps.append(current_gap)

        # Filter out gaps shorter than minimum duration after merging
        final_gaps = [gap for gap in merged_gaps if gap[1] - gap[0] >= self.min_silence_duration]

        logger.info(f"Merged {len(all_gaps)} gaps into {len(final_gaps)} final silence segments")
        return final_gaps

    async def get_vad_silence_boundaries(
        self,
        audio_file: str,
        duration: float,
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Detect silence boundaries using VAD processing on audio segments.
        Uses efficient ffmpeg segmentation and subprocess-based parallel processing.
        Returns a list of tuples containing (silence_start, silence_end) timestamps.
        """
        temp_dir = None
        try:
            self._check_cancellation()
            self._notify_progress(Step.VAD_PREP, 0, "Preparing...")

            # Create temporary directory for chunks in the same directory as the source file
            audio_dir = os.path.dirname(audio_file)
            temp_dir = tempfile.mkdtemp(prefix="vad_chunks_", dir=audio_dir)
            logger.info(f"Created temporary directory: {temp_dir}")

            self._check_cancellation()

            # Get VAD worker script path
            vad_worker_path = self._get_vad_worker_path()

            # Run VAD processing with direct async coordination (no executor needed)
            final_gaps = await self._run_vad_processing_async(audio_file, duration, temp_dir, vad_worker_path)

            # Check if processing was cancelled
            if final_gaps is None:
                logger.info("VAD processing was cancelled")
                return None

            self._check_cancellation()

            self._notify_progress(
                Step.VAD_ANALYSIS, 100, f"Smart detect complete, found {len(final_gaps)} potential cues"
            )

            return final_gaps

        except asyncio.CancelledError:
            logger.info("VAD silence boundary detection was cancelled")
            # Cancel any running VAD processes
            await self.cancel_vad_processes()
            return None
        finally:
            # Clean up temporary chunk files
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil

                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")

    async def _run_vad_processing_async(
        self,
        audio_file: str,
        duration: float,
        temp_dir: str,
        vad_worker_path: str,
    ) -> Optional[List[Tuple[float, float]]]:
        """Run VAD processing using subprocess-based parallel processing"""
        try:
            self._check_cancellation()

            # Step 1: Split audio into chunks using efficient ffmpeg segmentation
            self._notify_progress(Step.VAD_PREP, 0, "Preparing...")
            chunk_files = await self._split_audio_into_chunks_async(audio_file, duration, temp_dir)

            self._check_cancellation()

            if not chunk_files:
                logger.error("No chunks created, aborting VAD processing")
                return []

            self._notify_progress(Step.VAD_ANALYSIS, 0, f"File prep complete, starting smart detection...")

            self._check_cancellation()

            # Step 2: Process all chunks with VAD using subprocesses
            all_gaps = await self._process_audio_chunks_async(chunk_files, vad_worker_path, duration)

            self._check_cancellation()

            # Step 3: Merge overlapping gaps and filter by duration
            self._notify_progress(Step.VAD_ANALYSIS, 100, "Gathering results...")

            final_gaps = self._merge_overlapping_gaps(all_gaps)

            logger.info(f"VAD processing complete: found {len(final_gaps)} silence segments")
            return final_gaps

        except asyncio.CancelledError:
            logger.info("VAD processing was cancelled")
            # Cancel any running VAD processes
            await self.cancel_vad_processes()
            return None
        except Exception as e:
            logger.error(f"VAD processing failed: {e}")
            return []

    async def _split_audio_into_chunks_async(self, audio_file: str, duration: float, temp_dir: str) -> List[str]:
        """Async wrapper for splitting audio into chunks with progress monitoring"""
        loop = asyncio.get_event_loop()

        self._check_cancellation()

        # Run the splitting in executor but with periodic progress checks
        future = loop.run_in_executor(None, self._split_audio_into_chunks, audio_file, duration, temp_dir)

        # Monitor progress while waiting
        while not future.done():
            await asyncio.sleep(0.1)  # Check every 100ms

            # Check for cancellation
            if self._is_cancelled:
                # Cancel the executor task if possible and return empty list
                future.cancel()
                return []

            # Process any queued progress from the chunking process
            await self._process_queued_progress()

        return await future

    def generate_cue_set(
        self,
        silences: List[Tuple[float, float]],
        book_length: float,
        k_clusters: int,
    ) -> Dict[int, List[float]]:
        """Generate cue set options using k-means clustering on silence durations (same as SmartDetectionService)"""

        if not silences or k_clusters < 2:
            return {}

        # Prepare data for clustering
        silence_durations = np.array([[s[1] - s[0]] for s in silences])

        # Perform k-means clustering
        try:
            kmeans = KMeans(n_clusters=k_clusters, random_state=1337, n_init=10).fit(silence_durations)
        except Exception as e:
            logger.error(f"K-means clustering failed: {e}")
            return {}

        cue_sets: Dict[int, List[float]] = {}

        for i in range(k_clusters - 1):
            top_n = i + 1

            cue_set = []

            # Identify the clusters with the longest silences
            cluster_centers = kmeans.cluster_centers_
            cluster_ranks = np.argsort(-cluster_centers.flatten())[:top_n]

            # Select silences from the clusters with longer durations
            for idx, silence in enumerate(silences):
                if kmeans.labels_[idx] in cluster_ranks:
                    new_cue = silence[1] - self.asr_buffer

                    # Ensure the new cue is not too close to existing cues
                    if any(abs(new_cue - existing_cue) < self.min_clip_length for existing_cue in cue_set):
                        continue

                    cue_set.append(new_cue)

            # Sort chapter silences
            cue_set.sort()

            # If the first element is less than our segment length, change it to 0
            if cue_set and cue_set[0] <= (self.segment_length + self.min_clip_length):
                cue_set[0] = 0
            else:
                cue_set.insert(0, 0)

            # If the last element is greater than the book length minus segment length, remove it
            if cue_set and cue_set[-1] > (book_length - self.segment_length):
                cue_set.pop()

            cue_sets[len(cue_set)] = cue_set

        return cue_sets

    @staticmethod
    def _filter_consecutive_counts(chapter_counts: List[int]) -> List[int]:
        """Filter out consecutive counts to reduce cue set options (same as SmartDetectionService)"""
        if len(chapter_counts) <= 1:
            return chapter_counts

        filtered_counts = []
        i = 0

        while i < len(chapter_counts):
            # Start of a potential consecutive group
            group_start = i

            # Find the end of the consecutive group
            while i + 1 < len(chapter_counts) and chapter_counts[i + 1] == chapter_counts[i] + 1:
                i += 1

            group_end = i
            group_size = group_end - group_start + 1

            if group_size == 1:
                # Single item, keep it
                filtered_counts.append(chapter_counts[group_start])
            elif group_size == 2:
                # Two consecutive items, keep the higher one
                filtered_counts.append(chapter_counts[group_end])
            else:
                # Three or more consecutive items, keep first and last
                filtered_counts.append(chapter_counts[group_start])
                if chapter_counts[group_start] != chapter_counts[group_end]:  # Avoid duplicates
                    filtered_counts.append(chapter_counts[group_end])

            i += 1

        return sorted(filtered_counts)

    def get_clustered_cue_sets(
        self,
        silences: List[Tuple[float, float]],
        book_length: float,
    ) -> Dict[int, List[float]]:
        """Generate all possible cue set options using clustering (same as SmartDetectionService)"""

        self._notify_progress(Step.CUE_SET_SELECTION, 0, "Finalizing VAD results...")

        k_clusters_min = 2
        k_clusters_max = min(15, len(silences))

        all_clusters: Dict[int, List[float]] = {}

        # Generate cue sets for different k values
        for k_clusters in range(k_clusters_min, k_clusters_max + 1):
            cue_set = self.generate_cue_set(silences, book_length, k_clusters)
            all_clusters.update(cue_set)

        # Convert to sorted list and filter consecutive counts
        cluster_list = [(k, v) for k, v in all_clusters.items()]
        cluster_list = sorted(cluster_list, key=lambda x: x[0])

        # Extract just the chapter counts and filter them
        chapter_counts = [k for k, v in cluster_list]
        filtered_counts = self._filter_consecutive_counts(chapter_counts)

        # Rebuild the dictionary with only the filtered counts
        filtered_clusters = {}
        for count in filtered_counts:
            for k, v in cluster_list:
                if k == count:
                    filtered_clusters[k] = v
                    break

        return filtered_clusters

    async def get_vad_silence_boundaries_from_segments(
        self,
        segments: List[Tuple[float, str]],
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Detect silence boundaries from a list of audio segments.
        Returns a list of tuples containing (silence_start, silence_end) timestamps.
        """
        try:
            self._check_cancellation()
            self._notify_progress(Step.VAD_PREP, 0, "Preparing segments...")

            vad_worker_path = self._get_vad_worker_path()
            total_segments = len(segments)

            all_chunks = [(i, file_path) for i, (_, file_path) in enumerate(segments)]

            chunks_per_worker = max(1, total_segments // self.max_processes)
            if total_segments % self.max_processes != 0:
                chunks_per_worker += 1

            worker_batches = []
            for worker_id in range(self.max_processes):
                start_idx = worker_id * chunks_per_worker
                end_idx = min(start_idx + chunks_per_worker, total_segments)

                if start_idx < total_segments:
                    worker_batches.append(all_chunks[start_idx:end_idx])

            progress_tracker = {i: 0 for i in range(total_segments)}

            progress_task = asyncio.create_task(
                self._monitor_segment_progress(progress_tracker, total_segments)
            )

            self._notify_progress(Step.VAD_ANALYSIS, 0, "Starting analysis...")

            worker_tasks = []
            for batch in worker_batches:
                task = self._process_chunk_batch_subprocess(
                    batch,
                    vad_worker_path,
                    progress_tracker,
                    segment_duration=0.0,
                )
                worker_tasks.append(task)

            worker_results_list = await asyncio.gather(*worker_tasks, return_exceptions=True)

            progress_task.cancel()
            self._check_cancellation()

            all_gaps = []
            for result in worker_results_list:
                if isinstance(result, Exception):
                    logger.error(f"Worker failed: {result}")
                    continue

                for chunk_index, gaps in result:
                    start_offset = segments[chunk_index][0]

                    adjusted_gaps = [(start + start_offset, end + start_offset) for start, end in gaps]
                    all_gaps.extend(adjusted_gaps)

            self._notify_progress(Step.VAD_ANALYSIS, 100, "Finalizing results...")
            final_gaps = self._merge_overlapping_gaps(all_gaps)

            logger.info(
                f"VAD segment processing complete: found {len(final_gaps)} silence segments from {len(segments)} segments"
            )
            return final_gaps

        except asyncio.CancelledError:
            logger.info("VAD segment processing was cancelled")
            await self.cancel_vad_processes()
            return None
        except Exception as e:
            logger.error(f"VAD segment processing failed: {e}", exc_info=True)
            return None

    async def _monitor_segment_progress(
        self,
        progress_tracker: dict,
        total_segments: int,
    ):
        """Monitor and report progress for segment-based processing"""
        last_update_time = 0

        try:
            while True:
                if self._is_cancelled:
                    break

                current_time = asyncio.get_event_loop().time()

                if current_time - last_update_time >= 0.1:
                    if progress_tracker:
                        completed_count: float = sum(1 for v in progress_tracker.values() if v > 0)
                        progress = completed_count / total_segments * 100.0

                        self._notify_progress(
                            Step.VAD_ANALYSIS,
                            progress,
                            f"Performing focused audio analysis...",
                            {"completed": completed_count, "total": total_segments},
                        )

                        last_update_time = current_time

                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            pass
