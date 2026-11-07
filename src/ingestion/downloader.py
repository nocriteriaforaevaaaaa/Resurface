"""Semi-automatic data collection (Section 5.4 "Data Collection Procedure").

Reads config/sources.yaml, lists videos published within the collection window
(Section 1.3) from each declared channel, downloads permitted files via yt-dlp,
records public metadata, and inserts 'pending' rows into the videos table for the
preprocessing pipeline (src/preprocessing) to pick up.

This module intentionally stops at "download + record metadata": event-category
and location annotation (Sec 5.4 steps 4-5) and inclusion in the verified subset
(step 6) are manual review steps performed by the project team, not automated here.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import EventCategory, ProcessingStatus, Source, Video

SOURCES_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"


@dataclass
class SourceConfig:
    name: str
    platform: str
    homepage_url: str
    channel_url: str
    reliability_tier: int
    is_verified: bool
    event_categories: list[str]


def load_sources(config_path: Path = SOURCES_CONFIG_PATH) -> list[SourceConfig]:
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return [SourceConfig(**entry) for entry in raw.get("sources", [])]


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_or_create_source(db: Session, cfg: SourceConfig) -> Source:
    source = db.query(Source).filter_by(name=cfg.name).one_or_none()
    if source is None:
        source = Source(
            name=cfg.name,
            platform=cfg.platform,
            homepage_url=cfg.homepage_url,
            reliability_tier=cfg.reliability_tier,
            is_verified=cfg.is_verified,
        )
        db.add(source)
        db.flush()
        logger.info(f"Created source '{cfg.name}'")
    return source


def list_channel_videos(channel_url: str, since: datetime) -> list[dict]:
    """Return flat metadata (no download) for videos published on/after `since`."""
    import yt_dlp

    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "skip_download": True,
        "dateafter": since.strftime("%Y%m%d"),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    entries = info.get("entries", []) if info else []
    return [e for e in entries if e]


def download_video(url: str, dest_dir: Path, max_height: int = 480) -> dict:
    """Download a single video + metadata via yt-dlp. Returns the yt-dlp info dict."""
    import yt_dlp

    dest_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        # YouTube often serves video and audio as separate streams only; the old
        # "best[height<=...]" selector then picked a video-only file (no transcript possible).
        # Prefer mp4/m4a so the ffmpeg merge into mp4 always works.
        "format": (
            f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]"
            f"/bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
        ),
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
        "writeinfojson": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return info


def _download_and_record(
    db: Session,
    source: Source,
    video_url: str,
    event_category: EventCategory = EventCategory.other,
    is_verified_subset: bool = False,
) -> Video | None:
    """Shared download + dedup + insert logic (Sec 5.4 steps 1-3) for one video URL."""
    exists = db.query(Video).filter_by(source_url=video_url).one_or_none()
    if exists:
        logger.info(f"Already recorded, skipping: {video_url}")
        return None  # Sec 5.4 step 2: duplicate URL skip

    try:
        info = download_video(video_url, settings.raw_videos_dir)
    except Exception as exc:
        logger.error(f"Download failed for {video_url}: {exc}")
        return None

    file_path = settings.raw_videos_dir / f"{info['id']}.{info.get('ext', 'mp4')}"
    if not file_path.exists():
        logger.error(f"Expected downloaded file not found: {file_path}")
        return None

    checksum = _sha256_of_file(file_path)
    duplicate = db.query(Video).filter_by(checksum_sha256=checksum).one_or_none()
    if duplicate:
        logger.info(f"Exact duplicate file, removing: {file_path}")
        file_path.unlink(missing_ok=True)
        return None

    upload_date = info.get("upload_date")  # 'YYYYMMDD'
    publication_ts = (
        datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        if upload_date
        else datetime.now(timezone.utc)
    )

    video = Video(
        source_id=source.source_id,
        source_url=video_url,
        publication_ts=publication_ts,
        title=info.get("title"),
        caption=info.get("description"),
        event_category=event_category,
        duration_seconds=info.get("duration"),
        video_format=f"{info.get('ext', 'mp4')}",
        raw_file_path=str(file_path),
        checksum_sha256=checksum,
        status=ProcessingStatus.pending,
        is_verified_subset=is_verified_subset,
    )
    db.add(video)
    db.commit()
    logger.success(f"Recorded video {video.video_id} ({video.title!r})")
    return video


def collect_from_sources(
    db: Session, config_path: Path = SOURCES_CONFIG_PATH, max_videos: int | None = None
) -> list[Video]:
    """Entry point used by scripts/collect_dataset.py: crawls each configured channel's
    full upload history within the collection window (Sec 1.3)."""
    since = datetime.now(timezone.utc) - timedelta(days=365 * settings.collection_window_years)
    created: list[Video] = []

    for cfg in load_sources(config_path):
        if "REPLACE_ME" in cfg.channel_url or "REPLACE_WITH" in cfg.name:
            logger.warning(f"Skipping placeholder source entry: {cfg.name}")
            continue

        source = _get_or_create_source(db, cfg)
        db.commit()

        logger.info(f"Listing videos for '{cfg.name}' since {since.date()}")
        try:
            entries = list_channel_videos(cfg.channel_url, since)
        except Exception as exc:  # network/yt-dlp errors shouldn't abort the whole run
            logger.error(f"Failed to list videos for {cfg.channel_url}: {exc}")
            continue

        for entry in entries:
            if max_videos is not None and len(created) >= max_videos:
                return created
            video_url = entry.get("url") or entry.get("webpage_url")
            if not video_url:
                continue
            video = _download_and_record(db, source, video_url)
            if video is not None:
                created.append(video)

    return created


@dataclass
class SeedVideo:
    source_name: str
    video_url: str
    event_category: EventCategory


def collect_specific_videos(
    db: Session, seeds: list[SeedVideo], config_path: Path = SOURCES_CONFIG_PATH
) -> list[Video]:
    """Downloads an explicit, pre-vetted list of video URLs rather than crawling whole
    channel histories -- used for small targeted/seed collection runs
    (see scripts/collect_seed_videos.py) where the relevant videos are already known.
    """
    sources_by_name = {cfg.name: cfg for cfg in load_sources(config_path)}
    created: list[Video] = []

    for seed in seeds:
        cfg = sources_by_name.get(seed.source_name)
        if cfg is None:
            logger.error(f"No source config named '{seed.source_name}' in {config_path}")
            continue
        source = _get_or_create_source(db, cfg)
        db.commit()

        video = _download_and_record(
            db, source, seed.video_url, event_category=seed.event_category, is_verified_subset=True
        )
        if video is not None:
            created.append(video)

    return created
