"""Unit tests for claim extraction and the decision gate.

These tests construct SQLAlchemy model instances without a session, so they do
not touch the shared Postgres database or the FAISS index.
"""
from datetime import datetime, timedelta, timezone
import uuid

from src.db.models import DecisionLabel, EventCategory, RetrievalCandidate, Source, Video
from src.verification.claim_extraction import StructuredClaim, extract_claim
from src.verification.decision_logic import decide, effective_evidence_quality


def _video(
    *,
    tier: int = 1,
    verified: bool = True,
    evidence_quality: float | None = None,
    publication: datetime | None = None,
    category: EventCategory = EventCategory.earthquake,
) -> Video:
    source = Source(
        source_id=uuid.uuid4(),
        name="Test source",
        reliability_tier=tier,
        is_verified=verified,
    )
    return Video(
        video_id=uuid.uuid4(),
        source=source,
        title="Historical clip",
        source_url="https://example.com/video",
        is_verified_subset=verified,
        evidence_quality_score=evidence_quality,
        publication_ts=publication or datetime(2015, 1, 1, tzinfo=timezone.utc),
        event_category=category,
    )


def _candidate(video: Video, score: float = 0.9) -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_id=uuid.uuid4(),
        video_id=video.video_id,
        final_score=score,
    )


def test_naive_claim_date_does_not_raise_and_is_old():
    video = _video(category=EventCategory.earthquake)
    claim = StructuredClaim(
        claimed_date=datetime(2026, 11, 8),  # deliberately naive
        claimed_location=None,
        claimed_event_category=EventCategory.earthquake,
    )

    report = decide(_candidate(video), video, claim)

    assert report.label == DecisionLabel.old_video_reposted_as_recent
    assert report.matched_video_id == str(video.video_id)


def test_category_mismatch_is_old_even_without_a_date():
    video = _video(category=EventCategory.earthquake)
    claim = StructuredClaim(
        claimed_date=None,
        claimed_location=None,
        claimed_event_category=EventCategory.flood,
    )

    report = decide(_candidate(video), video, claim)

    assert report.label == DecisionLabel.old_video_reposted_as_recent


def test_consistent_context_is_recent_or_contextualised():
    publication = datetime(2026, 11, 1, tzinfo=timezone.utc)
    video = _video(category=EventCategory.flood, publication=publication)
    claim = StructuredClaim(
        claimed_date=publication + timedelta(hours=2),
        claimed_location="Kathmandu",
        claimed_event_category=EventCategory.flood,
    )

    report = decide(_candidate(video), video, claim)

    assert report.label == DecisionLabel.recent_or_correctly_contextualised


def test_below_score_threshold_is_insufficient():
    video = _video()
    claim = StructuredClaim(None, None, None)

    report = decide(_candidate(video, score=0.1), video, claim)

    assert report.label == DecisionLabel.insufficient_evidence
    assert report.matched_video_id is None


def test_missing_evidence_quality_uses_verified_fallback():
    video = _video(tier=5, verified=True, evidence_quality=None)

    assert effective_evidence_quality(video) >= 0.6

    report = decide(
        _candidate(video),
        video,
        StructuredClaim(None, None, EventCategory.flood),
    )
    assert report.label == DecisionLabel.old_video_reposted_as_recent
    assert any("evidence_quality_score" in warning for warning in report.warnings)


def test_unverified_low_tier_source_is_insufficient():
    video = _video(tier=5, verified=False, evidence_quality=None)

    report = decide(
        _candidate(video),
        video,
        StructuredClaim(None, None, EventCategory.flood),
    )

    assert report.label == DecisionLabel.insufficient_evidence


def test_explicit_evidence_quality_overrides_fallback():
    video = _video(tier=5, verified=True, evidence_quality=0.1)

    assert effective_evidence_quality(video) == 0.1


def test_extract_claim_normalises_dates_and_prioritises_caption():
    reference = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)

    claim = extract_claim(
        caption_text="Flood in Kathmandu today",
        ocr_text="earthquake in Nepal",
        transcript_text="an unrelated earthquake report",
        post_timestamp=reference,
    )

    assert claim.claimed_date is not None
    assert claim.claimed_date.tzinfo is not None
    assert claim.claimed_event_category == EventCategory.flood
    assert claim.claimed_location == "Kathmandu"


def test_extract_claim_does_not_match_now_inside_know():
    reference = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)

    claim = extract_claim(
        caption_text="I know this video",
        ocr_text="",
        transcript_text="",
        post_timestamp=reference,
    )

    assert claim.claimed_date is None


def test_extract_claim_parses_embedded_date_as_aware_utc():
    reference = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)

    claim = extract_claim(
        caption_text="Earthquake in Nepal on 1 January 2015",
        ocr_text="",
        transcript_text="",
        post_timestamp=reference,
    )

    assert claim.claimed_date is not None
    assert claim.claimed_date.tzinfo is not None
    assert claim.claimed_date.year == 2015
