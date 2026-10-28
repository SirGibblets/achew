"""Tests for xHE-AAC handling with the bundled ffmpeg (app/core/ffmpeg.py, app/services/audio_service.py).

FFmpeg's native aac decoder can't decode xHE-AAC (USAC) speech-mode frames, so Achew
decodes those files with libfdk_aac from the achew-ffmpeg wheel. The fixture is 34 s of
synthetic speech (espeak-ng, original text) encoded as xHE-AAC with three 1.5 s pauses,
copied from the achew-ffmpeg repo's tests/fixtures, where tools/xhe-fixture regenerates it.
"""

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import pytest

from app.core import ffmpeg as ffmpeg_module
from app.core.constants import CHAPTER_START_PADDING
from app.core.ffmpeg import ffmpeg_path, put_ffmpeg_on_path, supports_xhe_aac
from app.services import audio_service as audio_service_module
from app.services.audio_service import (
    XHE_AAC_DECODER_ARGS,
    AudioProcessingService,
    audio_uses_xhe_aac,
    decodable_audio,
    decoder_args,
    pick_segment_extension,
    probe_segment_extension,
)

XHE_FIXTURE = Path(__file__).parent / "fixtures" / "xhe-aac-speech.m4a"

# The fixture's three planted 1.5 s pauses between "chapters"
XHE_FIXTURE_SILENCES = 3

needs_fdk = pytest.mark.skipif(not supports_xhe_aac(), reason="ffmpeg in use lacks libfdk_aac")


def _write_tone_wav(path: Path, seconds: float = 4.0, rate: int = 16000) -> None:
    """A tone with a 1.5 s gap in the middle, as 16-bit mono PCM."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(seconds * rate)):
            t = i / rate
            silent = 1.25 <= t < 2.75
            sample = 0 if silent else int(8000 * math.sin(2 * math.pi * 440 * t))
            frames += struct.pack("<h", sample)
        w.writeframes(bytes(frames))


def _encode(src: Path, dst: Path) -> None:
    subprocess.run([ffmpeg_path(), "-y", "-loglevel", "error", "-i", str(src), str(dst)], check=True)


@pytest.fixture
def aac_lc_m4a(tmp_path: Path) -> Path:
    wav = tmp_path / "tone.wav"
    _write_tone_wav(wav)
    m4a = tmp_path / "tone.m4a"
    _encode(wav, m4a)
    return m4a


@pytest.fixture
def xhe_copy(tmp_path: Path) -> Path:
    path = tmp_path / "book.m4b"
    shutil.copy(XHE_FIXTURE, path)
    return path


def test_bundled_ffmpeg_is_used():
    import achew_ffmpeg

    assert ffmpeg_path() == achew_ffmpeg.ffmpeg_path()


def test_ffmpeg_env_override(monkeypatch):
    monkeypatch.setenv(ffmpeg_module.FFMPEG_ENV_VAR, "/opt/custom/ffmpeg")
    ffmpeg_module.ffmpeg_path.cache_clear()
    try:
        assert ffmpeg_module.ffmpeg_path() == "/opt/custom/ffmpeg"
    finally:
        ffmpeg_module.ffmpeg_path.cache_clear()


def _fake_tool(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def fresh_ffmpeg_resolution(monkeypatch, tmp_path: Path):
    """Re-resolve ffmpeg_path() under the test's environment, with link directories
    created under tmp_path, and restore the real resolution afterwards."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    ffmpeg_module.ffmpeg_path.cache_clear()
    yield
    monkeypatch.undo()
    ffmpeg_module.ffmpeg_path.cache_clear()


def test_put_ffmpeg_on_path_leaves_path_alone_when_it_already_resolves(monkeypatch):
    # How every launch path runs Achew: `uv run` puts the venv's scripts first
    path = os.pathsep.join([os.path.dirname(ffmpeg_path()), "/usr/bin", "/bin"])
    monkeypatch.setenv("PATH", path)
    put_ffmpeg_on_path()
    assert os.environ["PATH"] == path


def test_put_ffmpeg_on_path_puts_bundled_build_ahead_of_system_ffmpeg(monkeypatch, tmp_path: Path):
    system = tmp_path / "system-bin"
    _fake_tool(system, "ffmpeg")
    monkeypatch.setenv("PATH", os.pathsep.join([str(system), "/bin"]))
    put_ffmpeg_on_path()
    put_ffmpeg_on_path()
    # The bundled build lives in the interpreter's scripts directory, which goes first
    # exactly as venv activation would put it
    assert os.environ["PATH"].split(os.pathsep) == [os.path.dirname(ffmpeg_path()), str(system), "/bin"]
    assert os.path.samefile(shutil.which("ffmpeg") or "", ffmpeg_path())


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell stand-ins")
def test_put_ffmpeg_on_path_links_override_without_reordering(monkeypatch, tmp_path: Path, fresh_ffmpeg_resolution):
    # An override in a shared directory, under another name, next to other tools
    shared = tmp_path / "usr-bin"
    override = _fake_tool(shared, "ffmpeg-7")
    _fake_tool(shared, "python")
    monkeypatch.setenv(ffmpeg_module.FFMPEG_ENV_VAR, str(override))
    venv_bin = os.path.dirname(sys.executable)
    monkeypatch.setenv("PATH", os.pathsep.join([venv_bin, str(shared), "/bin"]))

    put_ffmpeg_on_path()
    put_ffmpeg_on_path()

    link_dir, *rest = os.environ["PATH"].split(os.pathsep)
    assert rest == [venv_bin, str(shared), "/bin"]
    assert os.listdir(link_dir) == ["ffmpeg"]
    assert os.path.samefile(shutil.which("ffmpeg") or "", override)
    # Nothing else in the override's directory moved ahead of the venv
    assert os.path.samefile(shutil.which("python") or "", os.path.join(venv_bin, "python"))


def test_put_ffmpeg_on_path_leaves_missing_override_alone(monkeypatch, tmp_path: Path, fresh_ffmpeg_resolution):
    monkeypatch.setenv(ffmpeg_module.FFMPEG_ENV_VAR, str(tmp_path / "missing" / "ffmpeg"))
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))
    put_ffmpeg_on_path()
    assert os.environ["PATH"] == os.pathsep.join(["/usr/bin", "/bin"])


@needs_fdk
def test_decoder_args_select_libfdk_for_xhe_aac(xhe_copy: Path, aac_lc_m4a: Path, tmp_path: Path):
    assert audio_uses_xhe_aac(str(xhe_copy))
    assert decoder_args(str(xhe_copy)) == XHE_AAC_DECODER_ARGS
    assert decoder_args(str(aac_lc_m4a)) == []
    # Non-mp4 files skip the probe entirely
    wav = tmp_path / "tone.wav"
    _write_tone_wav(wav)
    assert decoder_args(str(wav)) == []


@needs_fdk
def test_native_decoder_rejects_fixture_speech_frames():
    """Guards the fixture: it must keep exercising what only libfdk_aac can decode."""
    result = subprocess.run(
        [ffmpeg_path(), "-nostdin", "-c:a", "aac", "-i", str(XHE_FIXTURE), "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert "Not yet implemented" in result.stderr


def test_xhe_aac_segment_extensions(xhe_copy: Path, tmp_path: Path):
    # Whole-file stream copies (multi-file merges) stay in mp4: ADTS can't carry USAC
    assert pick_segment_extension(str(xhe_copy)) == "m4a"
    # Analysis segments decode to WAV, since stream copies can only start at sparse
    # independent frames
    assert probe_segment_extension(str(xhe_copy), str(tmp_path)) == "wav"


@needs_fdk
@pytest.mark.parametrize("seek_margin", [60.0, 1.0])
def test_range_extraction_reports_every_range(xhe_copy: Path, tmp_path: Path, monkeypatch, seek_margin: float):
    """Progress must reach every range, whether a block's ffmpeg extracts several ranges
    or just one (decoded extraction splits at long gaps). Counting only on the next
    output's open left one-range blocks stuck at 0% until the whole extraction ended."""
    monkeypatch.setattr(audio_service_module, "_RANGE_SEEK_MARGIN", seek_margin)
    reported: list[int] = []

    def record(*args, **kwargs) -> None:
        # (step, percent, message, details), as AudioProcessingService reports progress
        reported.append(args[3]["segments_created"])

    service = AudioProcessingService(record)
    ranges = [(s, s + 4.0) for s in (3.1, 9.4, 17.8, 26.5)]
    paths = service._run_parallel_range_extraction(
        str(xhe_copy), ranges, str(tmp_path), False, True, segment_extension="wav"
    )
    assert len(paths) == len(ranges)
    assert sorted(reported) == [1, 2, 3, 4]


@needs_fdk
@pytest.mark.parametrize(("seek_margin", "expected_blocks"), [(60.0, [4]), (1.0, [1, 1, 1, 1])])
def test_xhe_aac_segments_start_exactly(
    xhe_copy: Path, tmp_path: Path, monkeypatch, seek_margin: float, expected_blocks: list[int]
):
    """Segments cut from an xHE-AAC book must start where asked. Stream copies cut by the
    segment muxer start at the next independent frame instead (here up to ~2 s late),
    which clipped the first words of chapter transcripts.

    Covers both the batch range extraction and the single-snippet extraction behind
    transcript previews and realignment verification. Both must write 16 kHz mono WAVs,
    since whisper.cpp refuses any other WAV. Batch extraction decodes through short gaps
    in one ffmpeg and seeks past longer ones with a new one; the fixture is too short for
    real gaps longer than the seek margin, so the second case shrinks the margin."""
    import numpy as np

    monkeypatch.setattr(audio_service_module, "_RANGE_SEEK_MARGIN", seek_margin)
    service = AudioProcessingService(lambda *args, **kwargs: None, asr_buffer=0.0)
    extract_block = service._extract_range_block
    blocks: list[int] = []

    def counting_extract_block(*args, **kwargs):
        blocks.append(len(args[1]))
        return extract_block(*args, **kwargs)

    monkeypatch.setattr(service, "_extract_range_block", counting_extract_block)
    ext = probe_segment_extension(str(xhe_copy), str(tmp_path))
    starts = [3.1, 9.4, 17.8, 26.5]
    range_paths = service._run_parallel_range_extraction(
        str(xhe_copy), [(s, s + 4.0) for s in starts], str(tmp_path), False, True, segment_extension=ext
    )
    assert len(range_paths) == len(starts)
    assert blocks == expected_blocks
    single_paths = []
    for start in starts:
        path = str(tmp_path / f"single_{start}.{ext}")
        # extract_single_segment starts CHAPTER_START_PADDING after the time it's given
        assert service.extract_single_segment(str(xhe_copy), start - CHAPTER_START_PADDING, 4.0, path) == path
        single_paths.append(path)

    def pcm(path: str) -> "np.ndarray":
        with wave.open(path) as w:
            assert (w.getnchannels(), w.getframerate()) == (1, 16000)
            return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)

    reference = tmp_path / "reference.wav"
    subprocess.run(
        [ffmpeg_path(), "-y", "-v", "error", *decoder_args(str(xhe_copy)), "-i", str(xhe_copy)]
        + ["-ac", "1", "-ar", "16000", str(reference)],
        check=True,
    )
    whole = pcm(str(reference))
    for paths in (range_paths, single_paths):
        for start, path in zip(starts, paths):
            segment = pcm(path)[: 16000 * 2]
            expected = int(start * 16000)
            window = range(expected - 16000, expected + 16000)
            found = max(window, key=lambda k: float(np.dot(segment, whole[k : k + len(segment)])))
            assert abs(found - expected) / 16000 < 0.03, f"{path} starts {(found - expected) / 16:.0f} ms off"


@needs_fdk
def test_silence_detection_on_xhe_aac(xhe_copy: Path):
    service = AudioProcessingService(lambda *args, **kwargs: None)
    silences = service._sync_get_silence_boundaries(str(xhe_copy))
    assert silences is not None
    assert len(silences) == XHE_FIXTURE_SILENCES
    assert all(end - start >= 1.4 for start, end in silences)


@needs_fdk
def test_stream_copied_segment_decodes(xhe_copy: Path, tmp_path: Path):
    """Segments are stream copies of the book, so they carry xHE-AAC and need the decoder too."""
    service = AudioProcessingService(lambda *args, **kwargs: None, asr_buffer=0.0)
    segment = tmp_path / "segment_001.m4a"
    assert service.extract_single_segment(str(xhe_copy), 0.0, 12.0, str(segment)) == str(segment)
    assert decoder_args(str(segment)) == XHE_AAC_DECODER_ARGS
    silences = service._sync_get_silence_boundaries(str(segment))
    assert silences is not None and len(silences) == 1


@needs_fdk
def test_decodable_audio_gives_asr_libraries_a_wav(xhe_copy: Path, aac_lc_m4a: Path):
    with decodable_audio(str(xhe_copy)) as path:
        assert path.endswith(".wav")
        with wave.open(path) as w:
            assert (w.getnchannels(), w.getframerate()) == (1, 16000)
            assert 33 < w.getnframes() / w.getframerate() < 35
        # A bare ffmpeg call with no decoder options, like the ASR libraries make
        result = subprocess.run([ffmpeg_path(), "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True)
        assert result.returncode == 0 and not result.stderr
    assert not os.path.exists(path)

    with decodable_audio(str(aac_lc_m4a)) as path:
        assert path == str(aac_lc_m4a)
