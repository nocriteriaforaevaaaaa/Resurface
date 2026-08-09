"""Tests for src/storage/remote.py that don't require a configured rclone remote."""
from pathlib import Path

from src.storage.remote import _remote_target, archive, ensure_local, is_configured
from src.config import settings


def test_remote_target_path_mapping():
    local = settings.data_dir / "raw_videos" / "abc123.mp4"
    remote = _remote_target(local)
    assert remote == f"{settings.rclone_remote}:{settings.rclone_remote_root}/raw_videos/abc123.mp4"


def test_remote_target_path_mapping_with_empty_root(monkeypatch):
    # Teammates whose remote's root_folder_id already points at the shared Drive
    # folder set RCLONE_REMOTE_ROOT="" -- must not produce a stray leading slash.
    monkeypatch.setattr(settings, "rclone_remote_root", "")
    local = settings.data_dir / "raw_videos" / "abc123.mp4"
    remote = _remote_target(local)
    assert remote == f"{settings.rclone_remote}:raw_videos/abc123.mp4"


def test_is_configured_does_not_raise():
    # Whatever the actual answer is on this machine, it must be a clean bool, not an exception.
    assert isinstance(is_configured(), bool)


def test_ensure_local_is_noop_for_existing_file(tmp_path):
    f = tmp_path / "already_here.txt"
    f.write_text("hello")
    result = ensure_local(f)
    assert result == f
    assert result.read_text() == "hello"


def test_archive_is_noop_for_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.txt"
    assert archive(missing) is None
