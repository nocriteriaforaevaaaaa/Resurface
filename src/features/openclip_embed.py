"""OpenCLIP frame embeddings (Section 5.6.2, Eq. 5.1-5.2)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from src.config import settings
from src.storage.remote import ensure_local


def resolve_device(preferred: str = "auto") -> str:
    if preferred != "auto":
        return preferred
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@lru_cache(maxsize=1)
def _load_model():
    import open_clip

    device = resolve_device(settings.torch_device)
    model, _, preprocess = open_clip.create_model_and_transforms(
        settings.open_clip_model_name, pretrained=settings.open_clip_pretrained
    )
    model = model.to(device).eval()
    return model, preprocess, device


@torch.no_grad()
def embed_images(image_paths: list[Path]) -> np.ndarray:
    """Returns an (N, D) float32 array of L2-normalised OpenCLIP embeddings."""
    model, preprocess, device = _load_model()
    image_paths = [ensure_local(p) for p in image_paths]
    batch = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in image_paths]).to(device)
    features = model.encode_image(batch)
    features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype("float32")


def video_level_similarity(query_embeddings: np.ndarray, candidate_embeddings: np.ndarray) -> float:
    """S_visual = mean over query frames of the best cosine similarity to any candidate frame (Eq. 5.2).

    Embeddings are assumed to already be L2-normalised, so cosine similarity reduces to a dot product.
    """
    sims = query_embeddings @ candidate_embeddings.T  # (Nq, Nc), Eq. 5.1
    best_per_query_frame = sims.max(axis=1)
    return float(best_per_query_frame.mean())
