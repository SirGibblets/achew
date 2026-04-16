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
        print(f"PROGRESS:{json.dumps({'type': 'worker_init', 'message': 'Loading VAD model…'})}", flush=True)

    try:
        import onnx_asr
        import numpy as np
        import onnxruntime as ort

        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 1
        sess_opts.inter_op_num_threads = 1

        model = onnx_asr.load_vad("silero", sess_options=sess_opts)

        if enable_progress:
            print(
                f"PROGRESS:{json.dumps({'type': 'worker_ready', 'message': 'VAD model loaded, processing chunks…'})}",
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
            cmd = [
                "ffmpeg", "-loglevel", "error", "-y", "-i", chunk_file,
                "-ac", "1", "-ar", "16000", "-f", "f32le", "-"
            ]
            process = subprocess.run(cmd, stdout=subprocess.PIPE, check=True)
            wav = np.frombuffer(process.stdout, dtype=np.float32)
            sr = 16000

            if len(wav) == 0:
                result = {"chunk_index": chunk_index, "gaps": [], "error": "Empty audio"}
                results.append(result)
                print(f"RESULT:{json.dumps(result)}", flush=True)
                continue

            # Get speech timestamps using onnx_asr
            hop_size = 512  # frames per step at 16kHz
            waveforms = np.expand_dims(wav, axis=0)
            waveforms_len = np.array([len(wav)], dtype=np.int64)

            if enable_progress:
                total_frames = len(wav) // hop_size + 2
                last_reported_pct = -1

                def emit_progress(pct):
                    nonlocal last_reported_pct
                    if pct - last_reported_pct >= 5:
                        last_reported_pct = pct
                        progress_data = {
                            "type": "progress",
                            "chunk_index": chunk_index,
                            "progress": pct,
                            "worker_progress": (i / len(chunk_files_with_indices) * 100) + (pct / len(chunk_files_with_indices)),
                            "chunk_in_worker": i + 1,
                            "total_chunks_in_worker": len(chunk_files_with_indices),
                        }
                        print(f"PROGRESS:{json.dumps(progress_data)}", flush=True)

                frame_count = 0

                def counting_encode(*args, **kwargs):
                    nonlocal frame_count
                    for prob in model._encode(*args, **kwargs):
                        frame_count += 1
                        emit_progress(int(frame_count / total_frames * 100))
                        yield prob

                encoding = counting_encode(waveforms, sr, hop_size, 64)
                segments = list(model._merge_segments(
                    model._find_segments(
                        (p[0] for p in encoding), hop_size, speech_pad_ms=30
                    ),
                    int(waveforms_len[0]), sr, speech_pad_ms=30
                ))
                emit_progress(100)
            else:
                seg_results = list(model.segment_batch(waveforms, waveforms_len, speech_pad_ms=30))
                segments = list(seg_results[0]) if seg_results else []

            speech_timestamps = [{"start": s / sr, "end": e / sr} for s, e in segments]

            # Calculate end time for this chunk
            chunk_duration = len(wav) / sr
            end_time = start_time + chunk_duration

            # Convert speech timestamps to gaps
            gaps = find_gaps_in_speech(speech_timestamps, start_time, end_time, min_silence_duration)

            result = {"chunk_index": chunk_index, "gaps": gaps, "error": None}
            results.append(result)
            print(f"RESULT:{json.dumps(result)}", flush=True)

        except Exception as e:
            result = {"chunk_index": chunk_index, "gaps": [], "error": str(e)}
            results.append(result)
            print(f"RESULT:{json.dumps(result)}", flush=True)

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

        process_multiple_chunks(
            chunk_files_with_indices, segment_duration, min_silence_duration, enable_progress
        )

    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"Failed to parse arguments: {str(e)}"}))
        sys.exit(1)
