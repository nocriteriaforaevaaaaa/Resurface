"""End-to-end query pipeline (Figure 5.1).

This module is the reusable core behind both the CLI and the web UI.  It takes a
`query_posts` row, normalises the uploaded video, extracts multimodal features,
retrieves candidates from the shared FAISS index, reranks them, extracts the
claim, and stores a final decision.

The API runs this function in a background task after `POST /queries`; the CLI
(`scripts/run_query_pipeline.py`) remains a thin wrapper for batch/manual use.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from loguru import logger
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import (
    Decision,
    ProcessingStatus,
    QueryKeyframe,
    QueryOcrResult,
    QueryPost,
    QueryTranscript,
    RetrievalCandidate,
    Video,
)
from src.db.session import SessionLocal
from src.features import ocr as ocr_module
from src.features import whisper_asr
from src.features.openclip_embed import embed_images
from src.features.phash import compute_phash
from src.indexing.faiss_index import INDEX_PATH, load_or_create_index
from src.preprocessing import ffmpeg_utils
from src.preprocessing.keyframes import extract_keyframes
from src.retrieval.candidate_retrieval import stage1_fast_candidates
from src.retrieval.reranking import (
    check_temporal_consistency,
    get_active_weights,
    metadata_score,
)
from src.retrieval.text_similarity import text_similarity
from src.storage.remote import pull
from src.verification.claim_extraction import extract_claim
from src.verification.decision_logic import EvidenceReport, decide

MAX_OCR_FRAMES_PER_QUERY = 8


def _reset_query_artifacts(db: Session, query_id: uuid.UUID) -> None:
    """Remove previous artefacts so a failed query can be retried cleanly."""
    db.query(Decision).filter_by(query_id=query_id).delete(synchronize_session=False)
    db.query(RetrievalCandidate).filter_by(query_id=query_id).delete(
        synchronize_session=False
    )
    db.query(QueryOcrResult).filter_by(query_id=query_id).delete(
        synchronize_session=False
    )
    db.query(QueryKeyframe).filter_by(query_id=query_id).delete(
        synchronize_session=False
    )
    db.query(QueryTranscript).filter_by(query_id=query_id).delete(
        synchronize_session=False
    )
    db.commit()


def _process_query(query: QueryPost, db: Session) -> EvidenceReport:
    _reset_query_artifacts(db, query.query_id)

    query.status = ProcessingStatus.normalising
    db.commit()

    raw_path = Path(query.video_file_path)
    normalised_path = raw_path.with_suffix(".norm.mp4")
    ffmpeg_utils.normalise_video(raw_path, normalised_path)

    query.status = ProcessingStatus.extracting_features
    db.commit()

    # --- Keyframes + visual features (Sec 5.5, 5.6) ---
    keyframes = extract_keyframes(f"query_{query.query_id}", normalised_path)
    query_phashes = [compute_phash(kf.frame_path) for kf in keyframes]
    query_embeddings = (
        embed_images([kf.frame_path for kf in keyframes])
        if keyframes
        else np.empty((0, 512), dtype=np.float32)
    )

    for keyframe, phash in zip(keyframes, query_phashes):
        db.add(
            QueryKeyframe(
                query_id=query.query_id,
                frame_index=keyframe.frame_index,
                timestamp_seconds=keyframe.timestamp_seconds,
                frame_path=str(keyframe.frame_path),
                phash=phash,
            )
        )
    db.commit()

    # --- Audio transcription (Sec 5.7) ---
    audio_path = raw_path.with_suffix(".wav")
    if ffmpeg_utils.has_audio_stream(normalised_path):
        ffmpeg_utils.extract_audio(normalised_path, audio_path)
        transcript_result = whisper_asr.transcribe(audio_path)
    else:
        logger.warning(
            f"Query {query.query_id} has no audio track; storing an empty transcript"
        )
        transcript_result = {"full_text": "", "segments": [], "language": None}

    db.add(
        QueryTranscript(
            query_id=query.query_id,
            full_text=transcript_result["full_text"],
            segments=transcript_result["segments"],
            language=transcript_result["language"],
            asr_model=settings.whisper_model_name,
        )
    )
    db.commit()

    # --- OCR on selected frames (Sec 5.8) ---
    ocr_texts: list[str] = []
    for keyframe in keyframes[:MAX_OCR_FRAMES_PER_QUERY]:
        cleaned_text, _confidence = ocr_module.extract_text(keyframe.frame_path)
        if not cleaned_text:
            continue
        ocr_texts.append(cleaned_text)
        db.add(
            QueryOcrResult(
                query_id=query.query_id,
                frame_index=keyframe.frame_index,
                raw_text=cleaned_text,
                cleaned_text=cleaned_text,
            )
        )
    db.commit()

    query_ocr_text = " ".join(ocr_texts)
    query_transcript_text = transcript_result["full_text"] or ""

    # --- Stage 1: fast candidate generation (Sec 5.10.1) ---
    pull(INDEX_PATH)  # search against every teammate's latest indexed vectors
    index = load_or_create_index()
    candidates = stage1_fast_candidates(
        db, index, query_embeddings, query_phashes
    )

    # --- Stage 2: multimodal reranking (Sec 5.10.2) ---
    weights = get_active_weights(db)
    candidate_rows: list[RetrievalCandidate] = []
    videos_by_id: dict[uuid.UUID, Video] = {}

    for video_id, signal in candidates.items():
        video = db.get(Video, video_id)
        if video is None:
            continue
        videos_by_id[video_id] = video

        visual_score = min(
            1.0, signal["visual_frame_matches"] / max(len(keyframes), 1)
        )
        hash_score = min(1.0, signal["hash_matches"] / max(len(keyframes), 1))

        candidate_transcript = (
            video.transcript.full_text if video.transcript is not None else ""
        )
        candidate_ocr = " ".join(
            (row.cleaned_text or row.raw_text or "") for row in video.ocr_results
        )
        transcript_score = text_similarity(
            query_transcript_text, candidate_transcript
        )
        ocr_score = text_similarity(query_ocr_text, candidate_ocr)

        meta_score = metadata_score(db, video)
        matched_timestamps = sorted(
            signal.get("matched_visual_timestamps", []), key=lambda item: item[0]
        )

        final_score = (
            float(weights.w_visual) * visual_score
            + float(weights.w_hash) * hash_score
            + float(weights.w_transcript) * transcript_score
            + float(weights.w_ocr) * ocr_score
            + float(weights.w_metadata) * meta_score
        )

        row = RetrievalCandidate(
            query_id=query.query_id,
            video_id=video.video_id,
            hash_matches=signal["hash_matches"],
            visual_frame_matches=signal["visual_frame_matches"],
            visual_score=visual_score,
            hash_score=hash_score,
            transcript_score=transcript_score,
            ocr_score=ocr_score,
            metadata_score=meta_score,
            final_score=final_score,
            temporal_consistent=check_temporal_consistency(
                [timestamp for _, timestamp in matched_timestamps]
            ),
        )
        db.add(row)
        candidate_rows.append(row)

    db.commit()

    candidate_rows.sort(key=lambda row: float(row.final_score or 0), reverse=True)
    for rank, row in enumerate(candidate_rows, start=1):
        row.rank = rank
    db.commit()

    best_candidate = candidate_rows[0] if candidate_rows else None
    best_video = (
        videos_by_id.get(best_candidate.video_id) if best_candidate is not None else None
    )

    # --- Claim extraction (Sec 5.11) ---
    reference_time = (
        query.post_timestamp or query.submitted_at or datetime.now(timezone.utc)
    )
    claim = extract_claim(
        caption_text=query.caption_text or "",
        ocr_text=query_ocr_text,
        transcript_text=query_transcript_text,
        post_timestamp=reference_time,
    )
    query.claimed_date = claim.claimed_date
    query.claimed_location = claim.claimed_location
    query.claimed_event_category = claim.claimed_event_category
    db.commit()

    # --- Decision (Sec 5.12) ---
    report = decide(best_candidate, best_video, claim)
    db.add(
        Decision(
            query_id=query.query_id,
            matched_video_id=best_video.video_id if best_video else None,
            matched_candidate_id=best_candidate.candidate_id if best_candidate else None,
            label=report.label,
            confidence_score=report.confidence_score,
            explanation=report.explanation,
            evidence_report=report.to_dict(),
        )
    )
    query.status = ProcessingStatus.indexed
    db.commit()

    logger.success(
        f"Decision for {query.query_id}: {report.label.value} "
        f"({report.confidence_score:.3f})"
    )
    return report


def run_query_pipeline(query_id: str | uuid.UUID) -> EvidenceReport | None:
    """Run the full query pipeline for one query row.

    The query row is marked ``failed`` if any stage raises, so the web UI can
    stop polling and show an actionable error instead of hanging forever.
    """
    db = SessionLocal()
    try:
        query = db.get(QueryPost, uuid.UUID(str(query_id)))
        if query is None:
            raise ValueError(f"No query_posts row with id {query_id}")

        try:
            return _process_query(query, db)
        except Exception:
            db.rollback()
            query.status = ProcessingStatus.failed
            db.commit()
            logger.exception(f"Failed to process query {query_id}")
            raise
    finally:
        db.close()
