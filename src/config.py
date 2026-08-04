"""Central configuration, loaded from environment variables / .env.

See .env.example for the full list of supported settings.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg2://evidence_user:evidence_pass@localhost:5432/evidence_db"

    # --- Storage paths ---
    data_dir: Path = DATA_DIR
    raw_videos_dir: Path = DATA_DIR / "raw_videos"
    audio_dir: Path = DATA_DIR / "audio"
    keyframes_dir: Path = DATA_DIR / "keyframes"
    ocr_frames_dir: Path = DATA_DIR / "ocr_frames"
    transcripts_dir: Path = DATA_DIR / "transcripts"
    ocr_dir: Path = DATA_DIR / "ocr"
    embeddings_dir: Path = DATA_DIR / "embeddings"
    faiss_index_dir: Path = DATA_DIR / "faiss_index"
    query_uploads_dir: Path = DATA_DIR / "query_uploads"
    models_dir: Path = DATA_DIR / "models"

    # --- Collection window (Sec 1.3 Scope) ---
    collection_window_years: int = 3

    # --- Preprocessing ---
    ffmpeg_target_fps: int = 25
    keyframes_per_scene: int = 1
    fallback_interval_seconds: float = 4.0  # Sec 5.5 fallback interval-based keyframing

    # --- Models ---
    whisper_model_name: str = "small"          # tiny|base|small|medium|large-v3
    open_clip_model_name: str = "ViT-B-32"
    open_clip_pretrained: str = "laion2b_s34b_b79k"
    ocr_engine: str = "easyocr"
    ocr_languages: list[str] = ["en", "ne"]

    # --- Retrieval / reranking (Eq. 5.3 default weights, tuned via reranking_weight_sets table) ---
    faiss_top_k: int = 50
    phash_hamming_threshold: int = 10

    # --- Decision thresholds (Sec 5.12) ---
    min_final_score_for_match: float = 0.55
    min_source_reliability_for_decision: float = 0.4

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Device ---
    torch_device: str = "auto"  # 'auto' resolves to mps/cuda/cpu at runtime


settings = Settings()

for _dir in (
    settings.raw_videos_dir,
    settings.audio_dir,
    settings.keyframes_dir,
    settings.ocr_frames_dir,
    settings.transcripts_dir,
    settings.ocr_dir,
    settings.embeddings_dir,
    settings.faiss_index_dir,
    settings.query_uploads_dir,
    settings.models_dir,
):
    _dir.mkdir(parents=True, exist_ok=True)
