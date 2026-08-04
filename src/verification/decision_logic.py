"""Evidence comparison and 3-class decision (Section 5.12, 5.13)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from src.config import settings
from src.db.models import DecisionLabel, RetrievalCandidate, Video
from src.verification.claim_extraction import StructuredClaim

SAME_EVENT_DATE_TOLERANCE = timedelta(days=2)


@dataclass
class EvidenceReport:
    label: DecisionLabel
    confidence_score: float
    matched_video_id: str | None
    explanation: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label.value,
            "confidence_score": self.confidence_score,
            "matched_video_id": self.matched_video_id,
            "explanation": self.explanation,
            "warnings": self.warnings,
        }


def _contexts_conflict(claim: StructuredClaim, matched_video: Video) -> bool:
    conflicts = []
    if claim.claimed_event_category and claim.claimed_event_category != matched_video.event_category:
        conflicts.append("event_category_mismatch")
    if claim.claimed_date:
        delta = abs(claim.claimed_date - matched_video.publication_ts)
        if delta > SAME_EVENT_DATE_TOLERANCE:
            conflicts.append("date_mismatch")
    return bool(conflicts)


def decide(
    best_candidate: RetrievalCandidate | None,
    matched_video: Video | None,
    claim: StructuredClaim,
) -> EvidenceReport:
    """Implements the decision diamond in Figure 5.1."""
    if (
        best_candidate is None
        or matched_video is None
        or float(best_candidate.final_score or 0) < settings.min_final_score_for_match
        or float(matched_video.evidence_quality_score or 0) < settings.min_source_reliability_for_decision
    ):
        return EvidenceReport(
            label=DecisionLabel.insufficient_evidence,
            confidence_score=float(best_candidate.final_score) if best_candidate else 0.0,
            matched_video_id=None,
            explanation=(
                "No sufficiently reliable historical match was found. This does not prove "
                "the video is new -- only that no confident match exists in the repository."
            ),
        )

    if _contexts_conflict(claim, matched_video):
        return EvidenceReport(
            label=DecisionLabel.old_video_reposted_as_recent,
            confidence_score=float(best_candidate.final_score),
            matched_video_id=str(matched_video.video_id),
            explanation=(
                f"Matched an earlier video published {matched_video.publication_ts.date()} by "
                f"{matched_video.source.name}, whose recorded context conflicts with the claim "
                "made in the new post."
            ),
        )

    return EvidenceReport(
        label=DecisionLabel.recent_or_correctly_contextualised,
        confidence_score=float(best_candidate.final_score),
        matched_video_id=str(matched_video.video_id),
        explanation="Matched historical context is consistent with the claim in the new post.",
    )
