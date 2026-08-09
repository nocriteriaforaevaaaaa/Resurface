"""Google Drive archival via rclone (Section 5.9 "local or object storage").

Design: every local path under settings.data_dir has a deterministic remote
counterpart (same relative path, under the configured rclone remote/root). Postgres
rows keep storing the *local* path as before -- nothing else in the codebase needs to
know a file might live on Drive. Two operations bridge the gap:

  archive(path)      Uploads a file or directory to Drive, verifies the upload, then
                      deletes the local copy. Called automatically after a video
                      finishes processing (src/preprocessing/pipeline.py).

  ensure_local(path)  Guarantees `path` exists locally, transparently pulling it back
                      down from Drive first if it was archived. Called at the top of
                      every low-level function that opens a video/audio/image file
                      (ffmpeg_utils, keyframes, phash, openclip_embed, whisper_asr,
                      ocr), so reprocessing or serving an already-archived video "just
                      works" without callers needing to think about where the bytes
                      currently live.

Requires `rclone config` to have been run once, interactively, to authorise a remote
named settings.rclone_remote (default "gdrive") against the user's Google account --
see README "Remote storage" for the walkthrough. That OAuth consent step cannot be
scripted; everything else here is fully automatic.
"""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from loguru import logger

from src.config import settings


class RemoteStorageError(RuntimeError):
    pass


def _remote_target(local_path: Path) -> str:
    rel = local_path.resolve().relative_to(settings.data_dir.resolve())
    # rclone_remote_root is "" for teammates whose remote's root_folder_id already
    # points directly at the shared Drive folder (see README "Team setup") -- avoid
    # emitting a stray leading slash in that case.
    prefix = f"{settings.rclone_remote_root}/" if settings.rclone_remote_root else ""
    return f"{settings.rclone_remote}:{prefix}{rel.as_posix()}"


@lru_cache(maxsize=1)
def is_configured() -> bool:
    """True if rclone is installed and the configured remote has been authorised."""
    try:
        result = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return f"{settings.rclone_remote}:" in result.stdout


def archive(local_path: Path, delete_local: bool = True) -> str | None:
    """Uploads local_path (file or directory) to Drive and, once verified, deletes the
    local copy. Returns the remote target path, or None if archiving was skipped
    (remote storage disabled, not configured, or the path doesn't exist).
    """
    if not settings.use_remote_storage:
        return None
    if not local_path.exists():
        return None
    if not is_configured():
        logger.warning(
            f"Remote storage enabled but rclone remote '{settings.rclone_remote}' is not "
            f"configured -- leaving {local_path} on local disk. Run `rclone config` (see README)."
        )
        return None

    remote = _remote_target(local_path)
    try:
        subprocess.run(
            ["rclone", "copyto", str(local_path), remote, "--checksum"],
            check=True, capture_output=True, text=True, timeout=1800,
        )
        verify = subprocess.run(
            ["rclone", "lsf", "-R", remote], capture_output=True, text=True, timeout=60
        )
    except subprocess.CalledProcessError as exc:
        raise RemoteStorageError(f"rclone upload failed for {local_path}: {exc.stderr}") from exc
    if verify.returncode != 0 or not verify.stdout.strip():
        raise RemoteStorageError(f"Upload verification failed for {local_path} -> {remote}")

    if delete_local:
        if local_path.is_dir():
            shutil.rmtree(local_path)
        else:
            local_path.unlink()
        logger.info(f"Archived to Drive and freed local disk: {local_path} -> {remote}")
    return remote


def ensure_local(local_path: Path) -> Path:
    """Guarantees local_path exists on disk, fetching it from Drive first if it was
    archived. No-op (returns immediately) if the path is already present locally or
    remote storage is disabled/unconfigured -- callers should treat a still-missing
    path after this call as a genuine error, not a storage-location problem.
    """
    if local_path.exists() or not settings.use_remote_storage or not is_configured():
        return local_path

    remote = _remote_target(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["rclone", "copyto", remote, str(local_path)],
            check=True, capture_output=True, text=True, timeout=1800,
        )
    except subprocess.CalledProcessError as exc:
        raise RemoteStorageError(f"Failed to fetch {local_path} from Drive ({remote}): {exc.stderr}") from exc

    if not local_path.exists():
        raise RemoteStorageError(f"rclone reported success but {local_path} is still missing")
    logger.info(f"Fetched from Drive: {remote} -> {local_path}")
    return local_path
