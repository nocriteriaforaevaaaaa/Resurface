"""FFmpeg-based normalisation (Section 5.5 step 1, 5)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.config import settings
from src.storage.remote import ensure_local


def normalise_video(input_path: Path, output_path: Path, fps: int | None = None) -> Path:
    """Re-encode to a standard container/frame rate so downstream steps see uniform input."""
    input_path = ensure_local(input_path)
    fps = fps or settings.ffmpeg_target_fps
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def has_audio_stream(input_path: Path) -> bool:
    """True if the file has at least one audio stream (silent clips are common in news footage)."""
    input_path = ensure_local(input_path)
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(input_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return bool(result.stdout.strip())


def extract_audio(input_path: Path, output_path: Path, sample_rate: int = 16000) -> Path:
    """Extract the audio track as a mono waveform (Section 5.5 step 5) for Whisper."""
    input_path = ensure_local(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def probe_duration_seconds(input_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(input_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())
