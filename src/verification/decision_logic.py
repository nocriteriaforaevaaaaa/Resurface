"""Evidence comparison and 3-class decision (Section 5.12, 5.13)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def effective_evidence_quality(video: Video) -> float:
    """Return the evidence-quality score used by the decision gate.

    ``videos.evidence_quality_score`` is an optional manual annotation.  When it
    is missing (the current repository state), fall back to the source
    reliability tier.  Videos in the manually verified subset receive a
    conservative floor so that a strong match from a low-tier re-upload channel
    can still be reported as old/reposted; the source tier continues to
    influence the metadata component of the reranking score.
    """
    if video.evidence_quality_score is not None:
        return float(video.evidence_quality_score)

    tier = video.source.reliability_tier if video.source is not None else 3
    tier_score = 1.0 - (tier - 1) / 4.0  # tier 1 -> 1.0, tier 5 -> 0.0

    if video.is_verified_subset:
        return max(0.6, tier_score)
    return tier_score


def _contexts_conflict(claim: StructuredClaim, matched_video: Video) -> bool:
    conflicts = []
    if (
        claim.claimed_event_category
        and matched_video.event_category
        and claim.claimed_event_category != matched_video.event_category
    ):
        conflicts.append("event_category_mismatch")

    claim_date = _as_utc(claim.claimed_date)
    publication_date = _as_utc(matched_video.publication_ts)
    if claim_date and publication_date:
        delta = abs(claim_date - publication_date)
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
        or effective_evidence_quality(matched_video) < settings.min_source_reliability_for_decision
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

    warnings = []
    if matched_video.evidence_quality_score is None:
        warnings.append(
            "evidence_quality_score missing; used the verified-source fallback"
        )

    if _contexts_conflict(claim, matched_video):
        published = (
            matched_video.publication_ts.date()
            if matched_video.publication_ts is not None
            else "an unknown date"
        )
        source_name = (
            matched_video.source.name
            if matched_video.source is not None
            else "an unknown source"
        )
        return EvidenceReport(
            label=DecisionLabel.old_video_reposted_as_recent,
            confidence_score=float(best_candidate.final_score),
            matched_video_id=str(matched_video.video_id),
            explanation=(
                f"Matched an earlier video published {published} by {source_name}, "
                "whose recorded context conflicts with the claim made in the new post."
            ),
            warnings=warnings,
        )

    return EvidenceReport(
        label=DecisionLabel.recent_or_correctly_contextualised,
        confidence_score=float(best_candidate.final_score),
        matched_video_id=str(matched_video.video_id),
        explanation="Matched historical context is consistent with the claim in the new post.",
        warnings=warnings,
    )
