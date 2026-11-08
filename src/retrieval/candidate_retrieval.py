"""Two-stage candidate retrieval (Section 5.10)."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import Keyframe
from src.features.phash import hamming_distance
from src.indexing.faiss_index import search


def stage1_fast_candidates(
    db: Session,
    index,
    query_embeddings: np.ndarray,
    query_phashes: list[str],
) -> dict:
    """Group top-K FAISS + pHash matches by candidate video_id.

    Returns ``{video_id: {...}}`` with:

    * ``visual_frame_matches``: number of top-K FAISS hits for that video
    * ``hash_matches``: number of candidate keyframes within the pHash threshold
    * ``matched_visual_timestamps``: ``(query_frame_index, candidate_timestamp)``
      pairs for the best visual match per query frame, used to check temporal
      consistency in the reranker.
    """
    scores: dict = defaultdict(
        lambda: {
            "visual_frame_matches": 0,
            "hash_matches": 0,
            "matched_visual_timestamps": [],
        }
    )

    # --- FAISS visual search ---
    if len(query_embeddings):
        _, ids = search(index, query_embeddings, settings.faiss_top_k)
        flat_ids = {
            int(i) for row in ids for i in row if i != -1
        }
        if flat_ids:
            rows = (
                db.execute(select(Keyframe).where(Keyframe.faiss_vector_id.in_(flat_ids)))
                .scalars()
                .all()
            )
            by_vector_id = {
                int(kf.faiss_vector_id): kf
                for kf in rows
                if kf.faiss_vector_id is not None
            }

            for query_frame_index, row in enumerate(ids):
                best_per_video: dict = {}
                for vector_id in row:
                    if int(vector_id) == -1:
                        continue
                    kf = by_vector_id.get(int(vector_id))
                    if kf is None:
                        continue

                    scores[kf.video_id]["visual_frame_matches"] += 1
                    # FAISS returns nearest first, so setdefault keeps the best
                    # candidate frame for this query frame.
                    best_per_video.setdefault(
                        kf.video_id, float(kf.timestamp_seconds)
                    )

                for video_id, timestamp in best_per_video.items():
                    scores[video_id]["matched_visual_timestamps"].append(
                        (query_frame_index, timestamp)
                    )

    # --- Perceptual hash search (brute-force Hamming; fine at repository scale) ---
    if query_phashes:
        all_keyframes = (
            db.execute(select(Keyframe).where(Keyframe.phash.is_not(None)))
            .scalars()
            .all()
        )
        for kf in all_keyframes:
            for query_hash in query_phashes:
                if hamming_distance(query_hash, kf.phash) <= settings.phash_hamming_threshold:
                    scores[kf.video_id]["hash_matches"] += 1
                    break

    return dict(scores)
