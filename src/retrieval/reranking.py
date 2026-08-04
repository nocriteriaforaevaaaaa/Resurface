"""Stage 2 multimodal reranking (Section 5.10.2, Eq. 5.3)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.db.models import RerankingWeightSet, Source, Video


@dataclass
class RerankScores:
    visual_score: float
    hash_score: float
    transcript_score: float
    ocr_score: float
    metadata_score: float

    def final_score(self, weights: RerankingWeightSet) -> float:
        return (
            float(weights.w_visual) * self.visual_score
            + float(weights.w_hash) * self.hash_score
            + float(weights.w_transcript) * self.transcript_score
            + float(weights.w_ocr) * self.ocr_score
            + float(weights.w_metadata) * self.metadata_score
        )


def get_active_weights(db: Session) -> RerankingWeightSet:
    weights = db.query(RerankingWeightSet).filter_by(is_active=True).one_or_none()
    if weights is None:
        raise RuntimeError("No active reranking_weight_sets row; see src/db/schema.sql seed data.")
    return weights


def metadata_score(db: Session, video: Video) -> float:
    """Source-reliability component of Eq. 5.3, derived from sources.reliability_tier
    and videos.evidence_quality_score (Table 5.1)."""
    source: Source = video.source
    tier_score = 1.0 - (source.reliability_tier - 1) / 4.0  # tier 1 -> 1.0, tier 5 -> 0.0
    quality = float(video.evidence_quality_score) if video.evidence_quality_score is not None else tier_score
    return (tier_score + quality) / 2.0


def check_temporal_consistency(matched_frame_timestamps: list[float]) -> bool:
    """Matched frames should appear in non-decreasing order for a genuine reused clip
    (Section 5.10.2): a scrambled ordering suggests visually similar but unrelated scenes.
    """
    if len(matched_frame_timestamps) < 2:
        return True
    return all(
        a <= b for a, b in zip(matched_frame_timestamps, matched_frame_timestamps[1:])
    )
