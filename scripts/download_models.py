#!/usr/bin/env python
"""Pre-downloads model weights referenced in Table 6.1 so first pipeline runs
are not slowed down by cold-start downloads.

Usage:
    python scripts/download_models.py
"""
from loguru import logger

from src.config import settings


def download_whisper() -> None:
    import whisper

    logger.info(f"Downloading Whisper model '{settings.whisper_model_name}'...")
    whisper.load_model(settings.whisper_model_name)  # default cache: ~/.cache/whisper
    logger.success("Whisper model ready.")


def download_open_clip() -> None:
    import open_clip

    logger.info(
        f"Downloading OpenCLIP model '{settings.open_clip_model_name}' "
        f"({settings.open_clip_pretrained})..."
    )
    open_clip.create_model_and_transforms(
        settings.open_clip_model_name, pretrained=settings.open_clip_pretrained
    )
    logger.success("OpenCLIP model ready.")


def download_easyocr() -> None:
    import easyocr

    logger.info(f"Downloading EasyOCR models for languages {settings.ocr_languages}...")
    easyocr.Reader(settings.ocr_languages, gpu=False)
    logger.success("EasyOCR models ready.")


if __name__ == "__main__":
    download_whisper()
    download_open_clip()
    download_easyocr()
    logger.success("All models downloaded.")
