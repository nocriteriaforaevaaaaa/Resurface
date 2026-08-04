"""Scene detection and keyframe extraction (Section 5.5 steps 2-4).

Uses PySceneDetect for scene boundaries with a fallback to fixed-interval sampling
when scene detection returns too few or too many scenes, as described in Section 5.5.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from src.config import settings

MIN_SCENES = 2
MAX_SCENES = 200


@dataclass
class Keyframe:
    frame_index: int
    timestamp_seconds: float
    scene_index: int | None
    frame_path: Path


def _detect_scenes(video_path: Path) -> list[tuple[float, float]]:
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector

    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector())
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()
    return [(start.get_seconds(), end.get_seconds()) for start, end in scene_list]


def _save_frame_at(cap: cv2.VideoCapture, timestamp_seconds: float, out_path: Path) -> bool:
    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000)
    ok, frame = cap.read()
    if not ok:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), frame)
    return True


def extract_keyframes(video_id: str, video_path: Path, output_dir: Path | None = None) -> list[Keyframe]:
    output_dir = output_dir or (settings.keyframes_dir / video_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        scenes = _detect_scenes(video_path)
    except Exception:
        scenes = []

    cap = cv2.VideoCapture(str(video_path))
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    fps = cap.get(cv2.CAP_PROP_FPS) or settings.ffmpeg_target_fps
    duration = total_frames / fps if fps else 0.0

    keyframes: list[Keyframe] = []

    use_fallback = not (MIN_SCENES <= len(scenes) <= MAX_SCENES)
    if use_fallback:
        # interval-based sampling (Section 5.5 fallback strategy)
        step = settings.fallback_interval_seconds
        t = 0.0
        idx = 0
        while t < duration:
            out_path = output_dir / f"frame_{idx:05d}.jpg"
            if _save_frame_at(cap, t, out_path):
                keyframes.append(Keyframe(idx, round(t, 3), None, out_path))
                idx += 1
            t += step
    else:
        for scene_index, (start, end) in enumerate(scenes):
            mid = start + (end - start) / 2
            out_path = output_dir / f"frame_{scene_index:05d}.jpg"
            if _save_frame_at(cap, mid, out_path):
                keyframes.append(Keyframe(scene_index, round(mid, 3), scene_index, out_path))

    cap.release()
    return keyframes
