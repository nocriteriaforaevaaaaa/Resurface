#!/usr/bin/env python
"""Runs preprocessing (Sections 5.5-5.9) over every 'pending' video in the
historical repository, populating keyframes/transcripts/OCR/FAISS.

Usage:
    python scripts/build_repository_index.py
"""
from loguru import logger

from src.db.models import ProcessingStatus, Video
from src.db.session import SessionLocal
from src.preprocessing.pipeline import process_video


def main() -> None:
    db = SessionLocal()
    try:
        pending = db.query(Video).filter_by(status=ProcessingStatus.pending).all()
        logger.info(f"{len(pending)} video(s) pending processing")
        failures = 0
        for video in pending:
            try:
                process_video(video, db)
            except Exception:
                # process_video() already marks the row 'failed' and logs the traceback;
                # one bad video should not block the rest of the batch.
                failures += 1
                continue
        logger.info(f"Batch complete: {len(pending) - failures} succeeded, {failures} failed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
