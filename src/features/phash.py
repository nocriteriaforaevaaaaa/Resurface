"""Perceptual hashing (Section 5.6.1)."""
from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image


def compute_phash(image_path: Path, hash_size: int = 8) -> str:
    """Returns a hex-encoded perceptual hash (64 bits for hash_size=8)."""
    with Image.open(image_path) as img:
        return str(imagehash.phash(img, hash_size=hash_size))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def is_near_duplicate(hash_a: str, hash_b: str, threshold: int) -> bool:
    return hamming_distance(hash_a, hash_b) <= threshold
