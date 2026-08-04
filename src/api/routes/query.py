"""Query submission + evidence report endpoints (Figure 6.1: UI/API -> ... -> Evidence Report)."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.api.schemas import EvidenceReportResponse, QuerySubmitResponse
from src.config import settings
from src.db.models import Decision, ProcessingStatus, QueryPost
from src.db.session import get_db

router = APIRouter(prefix="/queries", tags=["queries"])


@router.post("", response_model=QuerySubmitResponse, status_code=202)
async def submit_query(
    caption_text: str = Form(""),
    post_url: str | None = Form(None),
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> QuerySubmitResponse:
    """Accepts a query video + caption; processing runs out-of-band (see scripts/run_query_pipeline.py)."""
    query_id = uuid.uuid4()
    dest = settings.query_uploads_dir / f"{query_id}_{video.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(video.file, f)

    query = QueryPost(
        query_id=query_id,
        caption_text=caption_text,
        post_url=post_url,
        post_timestamp=datetime.now(timezone.utc),
        video_file_path=str(dest),
        status=ProcessingStatus.pending,
    )
    db.add(query)
    db.commit()

    return QuerySubmitResponse(query_id=str(query_id), status=query.status.value)


@router.get("/{query_id}/report", response_model=EvidenceReportResponse)
def get_report(query_id: str, db: Session = Depends(get_db)) -> EvidenceReportResponse:
    decision = db.query(Decision).filter_by(query_id=query_id).one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="No decision yet for this query (still processing?).")

    matched_video = None
    if decision.matched_video_id:
        from src.db.models import Video

        matched_video = db.get(Video, decision.matched_video_id)

    return EvidenceReportResponse(
        query_id=str(decision.query_id),
        label=decision.label.value,
        confidence_score=float(decision.confidence_score or 0),
        matched_video_id=str(decision.matched_video_id) if decision.matched_video_id else None,
        matched_source_name=matched_video.source.name if matched_video else None,
        matched_publication_date=matched_video.publication_ts if matched_video else None,
        explanation=decision.explanation or "",
        warnings=(decision.evidence_report or {}).get("warnings", []),
    )
