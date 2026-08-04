#!/usr/bin/env python
"""Runs the full Figure 5.1 pipeline for one pending query post:
preprocessing -> candidate retrieval -> reranking -> claim extraction -> decision.

Usage:
    python scripts/run_query_pipeline.py <query_id>
"""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from loguru import logger

from src.db.models import (
    Decision,
    ProcessingStatus,
    QueryPost,
    RetrievalCandidate,
    Video,
)
from src.db.session import SessionLocal
from src.features.openclip_embed import embed_images
from src.features.phash import compute_phash
from src.indexing.faiss_index import load_or_create_index
from src.preprocessing.ffmpeg_utils import extract_audio, normalise_video
from src.preprocessing.keyframes import extract_keyframes
from src.retrieval.candidate_retrieval import stage1_fast_candidates
from src.retrieval.reranking import check_temporal_consistency, get_active_weights, metadata_score
from src.features import whisper_asr
from src.features import ocr as ocr_module
from src.verification.claim_extraction import extract_claim
from src.verification.decision_logic import decide


def run(query_id: str) -> None:
    db = SessionLocal()
    try:
        query: QueryPost = db.get(QueryPost, uuid.UUID(query_id))
        if query is None:
            raise SystemExit(f"No query_posts row with id {query_id}")

        query.status = ProcessingStatus.extracting_features
        db.commit()

        raw_path = Path(query.video_file_path)
        normalised = normalise_video(raw_path, raw_path.with_suffix(".norm.mp4"))
        kfs = extract_keyframes(f"query_{query_id}", normalised)
        query_phashes = [compute_phash(kf.frame_path) for kf in kfs]
        query_embeddings = embed_images([kf.frame_path for kf in kfs]) if kfs else None

        audio_path = raw_path.with_suffix(".wav")
        extract_audio(normalised, audio_path)
        transcript = whisper_asr.transcribe(audio_path)

        ocr_texts = [ocr_module.extract_text(kf.frame_path)[0] for kf in kfs[:8]]

        # --- Stage 1: fast candidate generation (Sec 5.10.1) ---
        index = load_or_create_index()
        candidates = stage1_fast_candidates(db, index, query_embeddings, query_phashes)

        # --- Stage 2: multimodal reranking (Sec 5.10.2) ---
        weights = get_active_weights(db)
        best_candidate: RetrievalCandidate | None = None
        best_video: Video | None = None

        for video_id, sig in candidates.items():
            video = db.get(Video, video_id)
            if video is None:
                continue
            visual_score = min(1.0, sig["visual_frame_matches"] / max(len(kfs), 1))
            hash_score = min(1.0, sig["hash_matches"] / max(len(kfs), 1))
            meta_score = metadata_score(db, video)
            # transcript/OCR textual overlap left as a TF-IDF/embedding similarity exercise;
            # 0.0 placeholder keeps the weighted sum well-defined until that scorer is added.
            transcript_score = 0.0
            ocr_score = 0.0

            final = (
                float(weights.w_visual) * visual_score
                + float(weights.w_hash) * hash_score
                + float(weights.w_transcript) * transcript_score
                + float(weights.w_ocr) * ocr_score
                + float(weights.w_metadata) * meta_score
            )

            candidate_row = RetrievalCandidate(
                query_id=query.query_id,
                video_id=video.video_id,
                hash_matches=sig["hash_matches"],
                visual_frame_matches=sig["visual_frame_matches"],
                visual_score=visual_score,
                hash_score=hash_score,
                transcript_score=transcript_score,
                ocr_score=ocr_score,
                metadata_score=meta_score,
                final_score=final,
                temporal_consistent=check_temporal_consistency(
                    [kf.timestamp_seconds for kf in kfs]
                ),
            )
            db.add(candidate_row)

            if best_candidate is None or final > float(best_candidate.final_score):
                best_candidate, best_video = candidate_row, video

        db.commit()

        # --- Claim extraction (Sec 5.11) ---
        claim = extract_claim(
            caption_text=query.caption_text or "",
            ocr_text=" ".join(ocr_texts),
            transcript_text=transcript["full_text"],
            post_timestamp=query.post_timestamp or query.submitted_at,
        )
        query.claimed_date = claim.claimed_date
        query.claimed_location = claim.claimed_location
        query.claimed_event_category = claim.claimed_event_category

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

        logger.success(f"Decision for {query_id}: {report.label.value} ({report.confidence_score:.3f})")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query_id")
    args = parser.parse_args()
    run(args.query_id)
