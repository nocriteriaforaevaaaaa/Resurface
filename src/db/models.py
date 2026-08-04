"""SQLAlchemy ORM models mirroring src/db/schema.sql.

Table/column layout follows Table 5.1 (dataset fields) and Sections 5.9-5.13
of the project proposal (docs/proposal.pdf).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class EventCategory(str, enum.Enum):
    flood = "flood"
    landslide = "landslide"
    earthquake = "earthquake"
    fire = "fire"
    severe_weather = "severe_weather"
    protest = "protest"
    rally = "rally"
    strike = "strike"
    political_incident = "political_incident"
    road_accident = "road_accident"
    aviation_incident = "aviation_incident"
    infrastructure_failure = "infrastructure_failure"
    public_disorder = "public_disorder"
    security_incident = "security_incident"
    emergency_response = "emergency_response"
    cultural_event = "cultural_event"
    social_event = "social_event"
    national_event = "national_event"
    other = "other"


class DecisionLabel(str, enum.Enum):
    old_video_reposted_as_recent = "old_video_reposted_as_recent"
    recent_or_correctly_contextualised = "recent_or_correctly_contextualised"
    insufficient_evidence = "insufficient_evidence"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    downloading = "downloading"
    normalising = "normalising"
    extracting_features = "extracting_features"
    indexed = "indexed"
    failed = "failed"
    excluded = "excluded"


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    platform: Mapped[str | None] = mapped_column(Text)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    reliability_tier: Mapped[int] = mapped_column(Integer, default=3)
    is_verified: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    videos: Mapped[list["Video"]] = relationship(back_populates="source")

    __table_args__ = (CheckConstraint("reliability_tier BETWEEN 1 AND 5"),)


class Video(Base):
    __tablename__ = "videos"

    video_id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.source_id", ondelete="RESTRICT"))
    source_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    publication_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    event_category: Mapped[EventCategory] = mapped_column(
        Enum(EventCategory, name="event_category"), default=EventCategory.other
    )
    location_text: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    municipality: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2))
    video_format: Mapped[str | None] = mapped_column(Text)
    raw_file_path: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, unique=True)
    evidence_quality_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"), default=ProcessingStatus.pending
    )
    is_verified_subset: Mapped[bool] = mapped_column(default=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped["Source"] = relationship(back_populates="videos")
    keyframes: Mapped[list["Keyframe"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    transcript: Mapped["Transcript | None"] = relationship(back_populates="video", cascade="all, delete-orphan")
    ocr_results: Mapped[list["OcrResult"]] = relationship(back_populates="video", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("evidence_quality_score BETWEEN 0 AND 1"),)


class Keyframe(Base):
    __tablename__ = "keyframes"

    keyframe_id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.video_id", ondelete="CASCADE"))
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    scene_index: Mapped[int | None] = mapped_column(Integer)
    frame_path: Mapped[str] = mapped_column(Text, nullable=False)
    phash: Mapped[str | None] = mapped_column(String(16))
    faiss_vector_id: Mapped[int | None] = mapped_column(unique=True)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="keyframes")

    __table_args__ = (UniqueConstraint("video_id", "frame_index"),)


class Transcript(Base):
    __tablename__ = "transcripts"

    transcript_id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.video_id", ondelete="CASCADE"), unique=True
    )
    full_text: Mapped[str | None] = mapped_column(Text)
    segments: Mapped[list | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(Text)
    asr_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="transcript")


class OcrResult(Base):
    __tablename__ = "ocr_results"

    ocr_id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.video_id", ondelete="CASCADE"))
    keyframe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("keyframes.keyframe_id", ondelete="CASCADE")
    )
    raw_text: Mapped[str | None] = mapped_column(Text)
    cleaned_text: Mapped[str | None] = mapped_column(Text)
    ocr_engine: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="ocr_results")


class QueryPost(Base):
    __tablename__ = "query_posts"

    query_id: Mapped[uuid.UUID] = _uuid_pk()
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_by: Mapped[str | None] = mapped_column(Text)
    caption_text: Mapped[str | None] = mapped_column(Text)
    post_url: Mapped[str | None] = mapped_column(Text)
    post_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    video_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_location: Mapped[str | None] = mapped_column(Text)
    claimed_event_category: Mapped[EventCategory | None] = mapped_column(
        Enum(EventCategory, name="event_category")
    )
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"), default=ProcessingStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidates: Mapped[list["RetrievalCandidate"]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )
    decision: Mapped["Decision | None"] = relationship(back_populates="query", cascade="all, delete-orphan")


class RetrievalCandidate(Base):
    __tablename__ = "retrieval_candidates"

    candidate_id: Mapped[uuid.UUID] = _uuid_pk()
    query_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_posts.query_id", ondelete="CASCADE"))
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.video_id", ondelete="CASCADE"))
    hash_matches: Mapped[int] = mapped_column(Integer, default=0)
    visual_frame_matches: Mapped[int] = mapped_column(Integer, default=0)
    visual_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    hash_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    transcript_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    ocr_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    metadata_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    final_score: Mapped[float | None] = mapped_column(Numeric(6, 5))
    temporal_consistent: Mapped[bool | None] = mapped_column()
    rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    query: Mapped["QueryPost"] = relationship(back_populates="candidates")
    video: Mapped["Video"] = relationship()

    __table_args__ = (UniqueConstraint("query_id", "video_id"),)


class Decision(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[uuid.UUID] = _uuid_pk()
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("query_posts.query_id", ondelete="CASCADE"), unique=True
    )
    matched_video_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("videos.video_id", ondelete="SET NULL")
    )
    matched_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("retrieval_candidates.candidate_id", ondelete="SET NULL")
    )
    label: Mapped[DecisionLabel] = mapped_column(Enum(DecisionLabel, name="decision_label"), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    explanation: Mapped[str | None] = mapped_column(Text)
    evidence_report: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    query: Mapped["QueryPost"] = relationship(back_populates="decision")

    __table_args__ = (CheckConstraint("confidence_score BETWEEN 0 AND 1"),)


class RerankingWeightSet(Base):
    __tablename__ = "reranking_weight_sets"

    weight_set_id: Mapped[uuid.UUID] = _uuid_pk()
    label: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    w_visual: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    w_hash: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    w_transcript: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    w_ocr: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    w_metadata: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
