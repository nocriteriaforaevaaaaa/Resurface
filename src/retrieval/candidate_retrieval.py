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

    Returns {video_id: {"visual_frame_matches": int, "hash_matches": int}}.
    """
    scores: dict = defaultdict(lambda: {"visual_frame_matches": 0, "hash_matches": 0})

    # --- FAISS visual search ---
    if len(query_embeddings):
        _, ids = search(index, query_embeddings, settings.faiss_top_k)
        flat_ids = [int(i) for row in ids for i in row if i != -1]
        if flat_ids:
            rows = db.execute(select(Keyframe).where(Keyframe.faiss_vector_id.in_(flat_ids))).scalars()
            for kf in rows:
                scores[kf.video_id]["visual_frame_matches"] += 1

    # --- Perceptual hash search (brute-force Hamming; fine at repository scale) ---
    if query_phashes:
        all_keyframes = db.execute(select(Keyframe).where(Keyframe.phash.is_not(None))).scalars()
        for kf in all_keyframes:
            for qh in query_phashes:
                if hamming_distance(qh, kf.phash) <= settings.phash_hamming_threshold:
                    scores[kf.video_id]["hash_matches"] += 1
                    break

    return dict(scores)
