#!/usr/bin/env python
"""CLI entry point for Section 5.4 data collection.

Usage:
    python scripts/collect_dataset.py [--config config/sources.yaml] [--max-videos N]
"""
import argparse
from pathlib import Path

from loguru import logger

from src.db.session import SessionLocal
from src.ingestion.downloader import SOURCES_CONFIG_PATH, collect_from_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Nepal news videos into the historical repository.")
    parser.add_argument("--config", type=Path, default=SOURCES_CONFIG_PATH)
    parser.add_argument(
        "--max-videos", type=int, default=None, help="Stop after this many new videos (default: unlimited)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        created = collect_from_sources(db, args.config, max_videos=args.max_videos)
        logger.info(f"Collection run complete: {len(created)} new video(s) recorded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
