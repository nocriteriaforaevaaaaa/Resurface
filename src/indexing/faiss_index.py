"""FAISS-backed dense visual index (Section 5.9, Section 4.3).

Stores OpenCLIP frame embeddings with an IndexIDMap so each vector can be mapped
back to a `keyframes.faiss_vector_id` -> `videos.video_id` join in Postgres. The
index is persisted to disk under settings.faiss_index_dir.
"""
from __future__ import annotations

import threading
from pathlib import Path

import faiss
import numpy as np

from src.config import settings

_EMBEDDING_DIM = 512  # ViT-B-32 output dimension
INDEX_PATH = settings.faiss_index_dir / "visual_index.faiss"
_lock = threading.Lock()


def _new_index(dim: int = _EMBEDDING_DIM) -> faiss.Index:
    # Inner product over L2-normalised vectors == cosine similarity (Eq. 5.1).
    base = faiss.IndexFlatIP(dim)
    return faiss.IndexIDMap2(base)


def load_or_create_index(path: Path = INDEX_PATH) -> faiss.Index:
    if path.exists():
        return faiss.read_index(str(path))
    return _new_index()


def save_index(index: faiss.Index, path: Path = INDEX_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))


def add_vectors(index: faiss.Index, ids: np.ndarray, vectors: np.ndarray) -> None:
    """ids: (N,) int64 array of faiss_vector_id values; vectors: (N, D) float32, L2-normalised."""
    with _lock:
        index.add_with_ids(vectors.astype("float32"), ids.astype("int64"))


def search(index: faiss.Index, query_vectors: np.ndarray, top_k: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Returns (distances, ids) both shaped (Nq, top_k). Distances are cosine similarities."""
    top_k = top_k or settings.faiss_top_k
    distances, ids = index.search(query_vectors.astype("float32"), top_k)
    return distances, ids


def next_vector_id(index: faiss.Index) -> int:
    """Monotonically increasing id allocator; safe as long as ids are never reused."""
    return int(index.ntotal)
