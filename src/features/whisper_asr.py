"""Audio transcription via Whisper (Section 5.7)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from src.config import settings
from src.storage.remote import ensure_local


class TranscriptSegment(TypedDict):
    start: float
    end: float
    text: str


class TranscriptResult(TypedDict):
    full_text: str
    segments: list[TranscriptSegment]
    language: str


@lru_cache(maxsize=1)
def _load_model():
    import whisper

    return whisper.load_model(settings.whisper_model_name)


def transcribe(audio_path: Path) -> TranscriptResult:
    audio_path = ensure_local(audio_path)
    model = _load_model()
    result = model.transcribe(str(audio_path))
    segments: list[TranscriptSegment] = [
        {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
        for seg in result.get("segments", [])
    ]
    return {
        "full_text": result.get("text", "").strip(),
        "segments": segments,
        "language": result.get("language", "unknown"),
    }
