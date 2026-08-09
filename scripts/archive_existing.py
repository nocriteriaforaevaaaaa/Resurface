#!/usr/bin/env python
"""One-off backfill: archives already-processed videos' local media (raw file,
normalised copy, audio, keyframes directory) to Drive and frees local disk, for
videos that finished processing before remote storage was wired up.

Usage:
    python scripts/archive_existing.py
"""
from pathlib import Path

from loguru import logger

from src.config import settings
from src.db.models import ProcessingStatus, Video
from src.db.session import SessionLocal
from src.storage.remote import archive, is_configured


def main() -> None:
    if not is_configured():
        raise SystemExit(
            f"rclone remote '{settings.rclone_remote}' is not configured yet -- "
            "run `rclone config` first (see README 'Remote storage')."
        )

    db = SessionLocal()
    try:
        videos = db.query(Video).filter_by(status=ProcessingStatus.indexed).all()
        logger.info(f"Archiving media for {len(videos)} already-indexed video(s)...")
        for video in videos:
            video_id = str(video.video_id)
            paths = [
                Path(video.raw_file_path),
                settings.raw_videos_dir / f"{video_id}_norm.mp4",
                settings.audio_dir / f"{video_id}.wav",
                settings.keyframes_dir / video_id,
            ]
            for path in paths:
                try:
                    archive(path)
                except Exception:
                    logger.exception(f"Failed to archive {path}")
        logger.success("Backfill archival complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
