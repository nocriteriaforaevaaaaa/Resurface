#!/usr/bin/env python
"""Downloads the reviewed-and-approved videos from the merged candidate sheet and records
them as 'pending' rows in the (shared) database.

Only rows with approved_for_dataset = TRUE *and* verified_real = TRUE are imported;
FALSE, NOT SURE, "to be thought" and blanks are all treated as rejected. Sources are
created from the sheet's channel_name / reliability_tier, so channels do not need to be
listed in config/sources.yaml first. Already-recorded URLs are skipped, so re-running is safe.

This only writes database rows and raw video files -- it does not touch the FAISS index,
so teammates can run it in parallel as long as each uses a different --reviewer batch.

Usage:
    python scripts/merge_reviews.py                          # build the merged sheet first
    python scripts/import_reviewed_videos.py                 # dry run: list what would be imported
    python scripts/import_reviewed_videos.py --reviewer reviewer2 --execute
    python scripts/import_reviewed_videos.py --reviewer reviewer2 --execute --limit 5
"""
from __future__ import annotations

import argparse
from pathlib import Path

import openpyxl
from loguru import logger

MERGED = Path(__file__).resolve().parent.parent / "data" / "candidate_videos_merged.xlsx"


def load_rows(reviewer: str | None) -> list[dict]:
    rows = list(openpyxl.load_workbook(MERGED, read_only=True).active.iter_rows(values_only=True))
    header = rows[0]
    recs = [dict(zip(header, r)) for r in rows[1:] if r[0]]
    return [
        r for r in recs
        if r["approved_status"] == "true"
        and r["verified_status"] == "true"
        and (reviewer is None or r["reviewer"] == reviewer)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviewer", help="only import this reviewer's rows, e.g. reviewer2")
    parser.add_argument("--limit", type=int, help="stop after this many NEW videos are recorded")
    parser.add_argument("--execute", action="store_true", help="actually download and write to the DB")
    args = parser.parse_args()

    if not MERGED.exists():
        raise SystemExit(f"{MERGED.name} not found -- run scripts/merge_reviews.py first")

    rows = load_rows(args.reviewer)
    logger.info(f"{len(rows)} approved+verified row(s)" + (f" for {args.reviewer}" if args.reviewer else ""))

    if not args.execute:
        for r in rows:
            print(f"{r['event_category_db']:<14} {r['channel_name']:<40.40} {r['video_url']}")
        logger.info("Dry run only -- pass --execute to download and record these.")
        return

    from src.db.models import EventCategory, Source
    from src.db.session import SessionLocal
    from src.ingestion.downloader import SourceConfig, _download_and_record, _get_or_create_source

    db = SessionLocal()
    recorded = 0
    try:
        for r in rows:
            if args.limit is not None and recorded >= args.limit:
                break
            tier = r.get("reliability_tier")
            cfg = SourceConfig(
                name=r["channel_name"],
                platform="youtube",
                homepage_url=r.get("channel_url") or "",
                channel_url=r.get("channel_url") or "",
                reliability_tier=int(tier) if isinstance(tier, (int, float)) and 1 <= tier <= 5 else 3,
                is_verified=True,
                event_categories=[],
            )
            source: Source = _get_or_create_source(db, cfg)
            db.commit()
            video = _download_and_record(
                db, source, r["video_url"],
                event_category=EventCategory(r["event_category_db"]),
                is_verified_subset=True,
            )
            if video is not None:
                video.location_text = r.get("location")
                db.commit()
                recorded += 1
        logger.info(f"Import complete: {recorded} new video(s) recorded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
