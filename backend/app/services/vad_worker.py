#!/usr/bin/env python3
"""
VAD Worker Script for Parallel Chapter Detection

This script processes individual audio chunks using Voice Activity Detection (VAD)
in isolated subprocess environments to avoid shared memory issues and provide
true parallelism for dramatized audiobook chapter detection.

Usage:
    python vad_worker.py <chunk_file> <chunk_index> <segment_duration> <min_silence_duration>

Returns:
    JSON object with chunk_index, gaps array, and error status
"""

import sys
import json
import librosa
import warnings
import time
import subprocess
import os


def find_gaps_in_speech(speech_timestamps, segment_start, segment_end, min_silence_duration):
    """Find gaps between speech segments and convert to global timeline"""
    gaps = []

    if not speech_timestamps:
        # If no speech detected, treat entire segment as silence
        if segment_end - segment_start >= min_silence_duration:
            gaps.append([segment_start, segment_end])
        return gaps

    # Sort speech timestamps by start time
    speech_timestamps.sort(key=lambda x: x["start"])

    # Check for gap at the beginning of segment
    first_speech_start = speech_timestamps[0]["start"] + segment_start
    if first_speech_start - segment_start >= min_silence_duration:
        gaps.append([segment_start, first_speech_start])

    # Check for gaps between speech segments
    for i in range(len(speech_timestamps) - 1):
        current_end = speech_timestamps[i]["end"] + segment_start
        next_start = speech_timestamps[i + 1]["start"] + segment_start
        gap_duration = next_start - current_end

        if gap_duration >= min_silence_duration:
            gaps.append([current_end, next_start])

    # Check for gap at the end of segment
    last_speech_end = speech_timestamps[-1]["end"] + segment_start
    if segment_end - last_speech_end >= min_silence_duration:
        gaps.append([last_speech_end, segment_end])

    return gaps


def process_multiple_chunks(chunk_files_with_indices, segment_duration, min_silence_duration, enable_progress=False):
    """Process multiple chunks sequentially in a single worker process"""
    results = []

    # Load VAD model once for all chunks
    if enable_progress:
        print(f"PROGRESS:{json.dumps({'type': 'worker_init', 'message': 'Loading VAD model...'})}", flush=True)

    try:
        from silero_vad import load_silero_vad

        model = load_silero_vad()

        if enable_progress:
            print(
                f"PROGRESS:{json.dumps({'type': 'worker_ready', 'message': 'VAD model loaded, processing chunks...'})}",
                flush=True,
            )

    except Exception as e:
        error_result = {"error": f"Failed to load VAD model: {str(e)}"}
        for chunk_file, chunk_index in chunk_files_with_indices:
            results.append({**error_result, "chunk_index": chunk_index, "gaps": []})
        return results

    # Process each chunk with the loaded model
    for i, (chunk_file, chunk_index) in enumerate(chunk_files_with_indices):
        try:
            # Calculate start time for this chunk
            start_time = chunk_index * segment_duration

            # Load the audio file
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                warnings.simplefilter("ignore", FutureWarning)
                wav, sr = librosa.load(chunk_file, sr=16000, mono=True)

            if len(wav) == 0:
                results.append({"chunk_index": chunk_index, "gaps": [], "error": "Empty audio"})
                continue

            # Progress callback for this specific chunk
            if enable_progress:
                last_progress_time = 0

                def progress_callback(progress_percent):
                    nonlocal last_progress_time
                    current_time = time.time()
                    if current_time - last_progress_time >= 0.1:  # Throttle to 0.1 second intervals
                        last_progress_time = current_time
                        # Calculate overall progress across all chunks in this worker
                        overall_progress = (i / len(chunk_files_with_indices) * 100) + (
                            progress_percent / len(chunk_files_with_indices)
                        )
                        progress_data = {
                            "type": "progress",
                            "chunk_index": chunk_index,
                            "progress": progress_percent,
                            "worker_progress": overall_progress,
                            "chunk_in_worker": i + 1,
                            "total_chunks_in_worker": len(chunk_files_with_indices),
                        }
                        print(f"PROGRESS:{json.dumps(progress_data)}", flush=True)

                # Get speech timestamps with progress tracking
                from silero_vad import get_speech_timestamps

                speech_timestamps = get_speech_timestamps(
                    wav,
                    model,
                    speech_pad_ms=100,
                    return_seconds=True,
                    progress_tracking_callback=progress_callback,
                )
            else:
                from silero_vad import get_speech_timestamps

                speech_timestamps = get_speech_timestamps(
                    wav,
                    model,
                    speech_pad_ms=100,
                    return_seconds=True,
                )

            # Calculate end time for this chunk
            chunk_duration = len(wav) / sr
            end_time = start_time + chunk_duration

            # Convert speech timestamps to gaps
            gaps = find_gaps_in_speech(speech_timestamps, start_time, end_time, min_silence_duration)

            results.append({"chunk_index": chunk_index, "gaps": gaps, "error": None})

        except Exception as e:
            results.append({"chunk_index": chunk_index, "gaps": [], "error": str(e)})

    return results


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Invalid arguments"}))
        sys.exit(1)

    try:
        chunk_files_with_indices = json.loads(sys.argv[1])
        segment_duration = float(sys.argv[2])
        min_silence_duration = float(sys.argv[3])
        enable_progress = len(sys.argv) >= 5 and sys.argv[4].lower() == "true"

        results = process_multiple_chunks(
            chunk_files_with_indices, segment_duration, min_silence_duration, enable_progress
        )

        # Output all results
        for result in results:
            print(f"RESULT:{json.dumps(result)}")

    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"Failed to parse arguments: {str(e)}"}))
        sys.exit(1)
