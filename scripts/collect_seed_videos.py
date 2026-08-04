#!/usr/bin/env python
"""Downloads a small, pre-vetted set of Nepal flood/landslide news clips to seed the
repository and exercise the full pipeline end-to-end.

Each entry was manually checked (title, channel, upload date via yt-dlp metadata)
before being added here -- see config/sources.yaml for the matching source records.
All three fall within the Section 1.3 three-year collection window (uploaded 2024).

Usage:
    python scripts/collect_seed_videos.py
"""
from loguru import logger

from src.db.models import EventCategory
from src.db.session import SessionLocal
from src.ingestion.downloader import SeedVideo, collect_specific_videos

SEEDS = [
    SeedVideo(
        source_name="Nepal Television",
        video_url="https://www.youtube.com/watch?v=Ly9PEnkC3i8",
        event_category=EventCategory.flood,
        # "Flood and landslides affect federal capital Kathmandu valley more" -- footage
        # from the 26-28 Sept 2024 Nepal flood/landslide disaster (217 dead). Uploaded 2024-09-28.
    ),
    SeedVideo(
        source_name="Nepal Times",
        video_url="https://www.youtube.com/watch?v=TaO0tM6c5Nw",
        event_category=EventCategory.flood,
        # "River flood enters Biratnagar settlements, 500 houses submerged." Uploaded 2024-06-26.
    ),
    SeedVideo(
        source_name="Prime Television",
        video_url="https://www.youtube.com/watch?v=pejq1tQfOUM",
        event_category=EventCategory.landslide,
        # "Flood/landslide risk continues nationwide as rain persists, 16 dead in 24 hours."
        # Uploaded 2024-07-07.
    ),
]


def main() -> None:
    db = SessionLocal()
    try:
        created = collect_specific_videos(db, SEEDS)
        logger.info(f"Seed collection complete: {len(created)}/{len(SEEDS)} new video(s) recorded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
