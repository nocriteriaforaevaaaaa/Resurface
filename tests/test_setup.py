"""Smoke tests verifying the initial project setup is wired correctly."""
from sqlalchemy import text

from src.db.session import SessionLocal
from src.indexing.faiss_index import load_or_create_index
from src.features.phash import hamming_distance


def test_database_connection():
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        db.close()


def test_reranking_weight_seed_row_exists():
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT w_visual + w_hash + w_transcript + w_ocr + w_metadata AS total "
                 "FROM reranking_weight_sets WHERE is_active = TRUE")
        ).one()
        assert abs(float(row.total) - 1.0) < 1e-6
    finally:
        db.close()


def test_faiss_index_loads():
    index = load_or_create_index()
    assert index.ntotal >= 0


def test_phash_hamming_distance():
    assert hamming_distance("0" * 16, "0" * 16) == 0
