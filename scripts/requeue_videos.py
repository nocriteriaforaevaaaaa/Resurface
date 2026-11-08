#!/usr/bin/env python
"""Reset failed or stuck repository-build rows to ``pending``.

This is useful after a transient failure (corrupt local download, FFmpeg/ffprobe
error, interrupted Colab session).  It never deletes a video or a Drive file --
it only changes the processing status so the build script can pick the row up
again.

Dry run by default:

    python scripts/requeue_videos.py
    python scripts/requeue_videos.py --status failed --status normalising --execute
    python scripts/requeue_videos.py --video-id <uuid> --execute
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.models import ProcessingStatus, Video  # noqa: E402
from src.db.session import SessionLocal  # noqa: E402

RESETTABLE = [
    ProcessingStatus.failed,
    ProcessingStatus.normalising,
    ProcessingStatus.extracting_features,
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        action="append",
        choices=[status.value for status in RESETTABLE],
        help="Status to reset (repeatable; default: failed)",
    )
    parser.add_argument(
        "--video-id",
        action="append",
        help="Only reset this video_id (repeatable)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write the changes; without this flag the command is a dry run",
    )
    args = parser.parse_args()

    statuses = (
        [ProcessingStatus(value) for value in args.status]
        if args.status
        else [ProcessingStatus.failed]
    )

    db = SessionLocal()
    try:
        query = db.query(Video).filter(Video.status.in_(statuses))
        if args.video_id:
            query = query.filter(Video.video_id.in_(args.video_id))
        videos = query.order_by(Video.source_url).all()

        if not videos:
            print("No matching videos.")
            return 0

        for video in videos:
            print(
                f"{video.video_id}  {video.status.value:18s}  "
                f"{video.source_url}  {video.title or ''}"
            )

        if not args.execute:
            print(
                f"\nDry run: {len(videos)} video(s) would be reset to pending. "
                "Re-run with --execute to apply."
            )
            return 0

        for video in videos:
            video.status = ProcessingStatus.pending
        db.commit()
        print(f"\nReset {len(videos)} video(s) to pending.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
