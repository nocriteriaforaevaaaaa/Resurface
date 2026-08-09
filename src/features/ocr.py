"""On-screen text extraction (Section 5.8)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src.config import settings
from src.storage.remote import ensure_local


@lru_cache(maxsize=1)
def _load_reader():
    import easyocr

    return easyocr.Reader(settings.ocr_languages, gpu=False)


def extract_text(image_path: Path) -> tuple[str, float]:
    """Returns (cleaned_text, mean_confidence) for one frame."""
    image_path = ensure_local(image_path)
    reader = _load_reader()
    results = reader.readtext(str(image_path))
    if not results:
        return "", 0.0

    texts, confidences = zip(*[(text, conf) for _, text, conf in results])
    cleaned = clean_text(" ".join(texts))
    # EasyOCR returns numpy.float64 confidences, which psycopg2 cannot adapt directly.
    return cleaned, float(sum(confidences) / len(confidences))


def clean_text(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw).strip()
    # collapse immediate repeated tokens (e.g. subtitle flicker duplicates)
    tokens = text.split(" ")
    deduped = [tok for i, tok in enumerate(tokens) if i == 0 or tok != tokens[i - 1]]
    return " ".join(deduped)
