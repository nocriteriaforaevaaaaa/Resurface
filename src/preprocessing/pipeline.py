"""End-to-end per-video preprocessing (Sections 5.5-5.9), for both historical
repository videos and query-post videos.

Wires together: FFmpeg normalisation -> keyframe extraction -> pHash + OpenCLIP
embeddings -> FAISS indexing -> audio extraction + Whisper transcript -> OCR.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import Keyframe, OcrResult, ProcessingStatus, Transcript, Video
from src.features import ocr as ocr_module
from src.features import phash as phash_module
from src.features import whisper_asr
from src.features.openclip_embed import embed_images
from src.indexing.faiss_index import INDEX_PATH, add_vectors, load_or_create_index, next_vector_id, save_index
from src.preprocessing import ffmpeg_utils
from src.preprocessing.keyframes import extract_keyframes
from src.storage.remote import archive, pull, push

MAX_OCR_FRAMES_PER_VIDEO = 8  # Sec 5.8: OCR selected frames, not every frame


def process_video(video: Video, db: Session) -> None:
    video_id = str(video.video_id)
    # raw_file_path was recorded as an absolute path on whichever machine downloaded the
    # video; resolve it by file name under *this* machine's raw_videos_dir so Colab (or a
    # teammate) can process it -- ensure_local() fetches it from Drive if it isn't here.
    raw_path = settings.raw_videos_dir / Path(video.raw_file_path).name

    try:
        video.status = ProcessingStatus.normalising
        db.commit()

        normalised_path = settings.raw_videos_dir / f"{video_id}_norm.mp4"
        ffmpeg_utils.normalise_video(raw_path, normalised_path)

        video.status = ProcessingStatus.extracting_features
        db.commit()

        # --- Keyframes + visual features (Sec 5.5, 5.6) ---
        kfs = extract_keyframes(video_id, normalised_path)
        pull(INDEX_PATH)  # pick up any vectors a teammate has pushed since our last run
        index = load_or_create_index()

        if kfs:
            embeddings = embed_images([kf.frame_path for kf in kfs])
            ids = np.array([next_vector_id(index) + i for i in range(len(kfs))])
            add_vectors(index, ids, embeddings)
            save_index(index)
            push(INDEX_PATH)  # share our additions immediately (see remote.py caveat)

            for kf, vec_id in zip(kfs, ids):
                db.add(
                    Keyframe(
                        video_id=video.video_id,
                        frame_index=kf.frame_index,
                        timestamp_seconds=kf.timestamp_seconds,
                        scene_index=kf.scene_index,
                        frame_path=str(kf.frame_path),
                        phash=phash_module.compute_phash(kf.frame_path),
                        faiss_vector_id=int(vec_id),
                        embedding_model=f"{settings.open_clip_model_name}/{settings.open_clip_pretrained}",
                    )
                )
            db.commit()

        # --- Audio transcription (Sec 5.7) ---
        audio_path = settings.audio_dir / f"{video_id}.wav"
        ffmpeg_utils.extract_audio(normalised_path, audio_path)
        transcript_result = whisper_asr.transcribe(audio_path)
        db.add(
            Transcript(
                video_id=video.video_id,
                full_text=transcript_result["full_text"],
                segments=transcript_result["segments"],
                language=transcript_result["language"],
                asr_model=settings.whisper_model_name,
            )
        )
        db.commit()

        # --- OCR on selected frames (Sec 5.8) ---
        for kf in kfs[:MAX_OCR_FRAMES_PER_VIDEO]:
            cleaned_text, confidence = ocr_module.extract_text(kf.frame_path)
            if not cleaned_text:
                continue
            keyframe_row = (
                db.query(Keyframe)
                .filter_by(video_id=video.video_id, frame_index=kf.frame_index)
                .one_or_none()
            )
            db.add(
                OcrResult(
                    video_id=video.video_id,
                    keyframe_id=keyframe_row.keyframe_id if keyframe_row else None,
                    raw_text=cleaned_text,
                    cleaned_text=cleaned_text,
                    ocr_engine=settings.ocr_engine,
                    confidence=confidence,
                )
            )
        db.commit()

        video.status = ProcessingStatus.indexed
        db.commit()
        logger.success(f"Processed video {video_id}")

    except Exception:
        db.rollback()
        video.status = ProcessingStatus.failed
        db.commit()
        logger.exception(f"Failed to process video {video_id}")
        raise

    # Archival is a best-effort disk-cleanup step, run only after every DB row for
    # this video has already committed successfully -- a Drive/rclone hiccup here
    # must never flip an already-indexed video back to 'failed'.
    for path in (raw_path, normalised_path, audio_path, settings.keyframes_dir / video_id):
        try:
            archive(path)
        except Exception:
            logger.exception(f"Archival to remote storage failed for {path} (left on local disk)")
