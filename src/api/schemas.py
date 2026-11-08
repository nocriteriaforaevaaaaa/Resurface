"""Pydantic request/response models for the REST API (Figure 6.1)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class QuerySubmitResponse(BaseModel):
    query_id: str
    status: str


class QueryStatusResponse(BaseModel):
    query_id: str
    status: str
    label: str | None = None


class EvidenceReportResponse(BaseModel):
    query_id: str
    label: str
    confidence_score: float
    matched_video_id: str | None
    matched_source_name: str | None = None
    matched_source_url: str | None = None
    matched_title: str | None = None
    matched_publication_date: datetime | None = None
    explanation: str
    warnings: list[str] = []


class HealthResponse(BaseModel):
    status: str
    database: str
    faiss_index_size: int
