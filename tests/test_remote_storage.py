"""Tests for src/storage/remote.py that don't require a configured rclone remote."""
import subprocess

import pytest

from src.config import settings
from src.storage.remote import _remote_target, archive, ensure_local, is_configured, pull, push


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


@pytest.mark.skipif(not is_configured(), reason="rclone remote not configured on this machine")
def test_push_then_pull_roundtrip():
    # _remote_target requires paths under settings.data_dir, so this can't use tmp_path.
    local = settings.data_dir / "_test_push_pull" / "sample.txt"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("original")
    try:
        push(local)
        assert local.exists()  # push, unlike archive(), must keep the local copy

        local.write_text("locally modified, should be overwritten by pull")
        pull(local)
        assert local.read_text() == "original"
    finally:
        local.unlink(missing_ok=True)
        subprocess.run(["rclone", "deletefile", _remote_target(local)], capture_output=True)


def test_pull_is_noop_when_nothing_on_remote(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    local = tmp_path / "never_pushed.txt"
    local.write_text("stays as-is")
    pull(local)
    assert local.read_text() == "stays as-is"
