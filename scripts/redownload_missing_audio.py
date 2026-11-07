#!/usr/bin/env python
"""Re-downloads videos whose local file has no audio track (an old yt-dlp format selector
fetched video-only streams, which makes Whisper transcripts empty).

For every approved video in the merged sheet (optionally only one reviewer's batch) whose
file in data/raw_videos has no audio, downloads it again with audio, replaces the file, and
updates checksum / duration in the database. It does NOT change processing status or touch
keyframes, and it does not upload anything -- upload afterwards with:

    rclone copy data/raw_videos gdrive:raw_videos --progress

Usage:
    python scripts/redownload_missing_audio.py --reviewer reviewer2            # dry run
    python scripts/redownload_missing_audio.py --reviewer reviewer2 --execute
"""
from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path

from loguru import logger

from scripts.import_reviewed_videos import load_rows
from src.config import settings
from src.db.models import Video
from src.db.session import SessionLocal
from src.ingestion.downloader import _sha256_of_file, download_video
from src.preprocessing.ffmpeg_utils import has_audio_stream


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviewer", help="only this reviewer's rows, e.g. reviewer2")
    parser.add_argument("--execute", action="store_true", help="actually re-download and update the DB")
    args = parser.parse_args()

    db = SessionLocal()
    todo: list[tuple[Video, Path]] = []
    for row in load_rows(args.reviewer):
        video = db.query(Video).filter_by(source_url=row["video_url"]).one_or_none()
        if video is None:
            continue
        local = settings.raw_videos_dir / re.split(r"[\\/]", video.raw_file_path)[-1]
        if not local.exists():
            logger.warning(f"Not on this machine, skipping: {local.name}")
            continue
        if has_audio_stream(local):
            continue
        todo.append((video, local))

    logger.info(f"{len(todo)} local video(s) have no audio track")
    if not args.execute:
        for video, local in todo:
            print(f"{video.status.value:<20} {video.source_url}")
        logger.info("Dry run only -- pass --execute to re-download these.")
        db.close()
        return

    fixed = 0
    for video, local in todo:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                info = download_video(video.source_url, Path(tmp))
            except Exception as exc:
                logger.error(f"Download failed for {video.source_url}: {exc}")
                continue
            fresh = Path(tmp) / f"{info['id']}.{info.get('ext', 'mp4')}"
            if not fresh.exists() or not has_audio_stream(fresh):
                logger.error(f"Re-download still has no audio, keeping old file: {video.source_url}")
                continue
            shutil.move(str(fresh), str(local))
        video.checksum_sha256 = _sha256_of_file(local)
        video.duration_seconds = info.get("duration")
        db.commit()
        fixed += 1
        logger.success(f"Replaced {local.name} (now has audio)")
    logger.info(f"Done: {fixed}/{len(todo)} replaced. Now run: rclone copy data/raw_videos gdrive:raw_videos --progress")
    db.close()


if __name__ == "__main__":
    main()
