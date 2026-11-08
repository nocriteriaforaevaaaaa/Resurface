"""Query submission + evidence report endpoints (Figure 6.1: UI/API -> ... -> Evidence Report)."""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from src.api.schemas import (
    EvidenceReportResponse,
    QueryStatusResponse,
    QuerySubmitResponse,
)
from src.config import settings
from src.db.models import Decision, ProcessingStatus, QueryPost
from src.db.session import get_db
from src.query.pipeline import run_query_pipeline

router = APIRouter(prefix="/queries", tags=["queries"])

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MiB; the demo is not a file host


def _parse_query_id(query_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(query_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="query_id must be a UUID") from exc


@router.post("", response_model=QuerySubmitResponse, status_code=202)
async def submit_query(
    background_tasks: BackgroundTasks,
    caption_text: str = Form(""),
    post_url: str | None = Form(None),
    auto_process: bool = Form(True),
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> QuerySubmitResponse:
    """Accept a query video + caption and (by default) process it in the background.

    Set ``auto_process=false`` to create the row only and run
    ``scripts/run_query_pipeline.py <query_id>`` manually, which is useful for
    debugging or for running the pipeline on a different machine.
    """
    upload_size = getattr(video, "size", None)
    if upload_size is not None and upload_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Video is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB",
        )

    query_id = uuid.uuid4()
    safe_name = Path(video.filename or "upload.mp4").name
    dest = settings.query_uploads_dir / f"{query_id}_{safe_name}"
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

    if auto_process:
        background_tasks.add_task(run_query_pipeline, str(query_id))

    return QuerySubmitResponse(query_id=str(query_id), status=query.status.value)


@router.get("/{query_id}/status", response_model=QueryStatusResponse)
def get_status(query_id: str, db: Session = Depends(get_db)) -> QueryStatusResponse:
    """Lightweight polling endpoint for the web UI."""
    query = db.get(QueryPost, _parse_query_id(query_id))
    if query is None:
        raise HTTPException(status_code=404, detail="Query not found")

    decision = db.query(Decision).filter_by(query_id=query.query_id).one_or_none()
    return QueryStatusResponse(
        query_id=str(query.query_id),
        status=query.status.value,
        label=decision.label.value if decision is not None else None,
    )


@router.get("/{query_id}/report", response_model=EvidenceReportResponse)
def get_report(query_id: str, db: Session = Depends(get_db)) -> EvidenceReportResponse:
    query_uuid = _parse_query_id(query_id)
    decision = db.query(Decision).filter_by(query_id=query_uuid).one_or_none()
    if decision is None:
        raise HTTPException(
            status_code=404,
            detail="No decision yet for this query (still processing?).",
        )

    matched_video = None
    if decision.matched_video_id:
        from src.db.models import Video

        matched_video = db.get(Video, decision.matched_video_id)

    return EvidenceReportResponse(
        query_id=str(decision.query_id),
        label=decision.label.value,
        confidence_score=float(decision.confidence_score or 0),
        matched_video_id=str(decision.matched_video_id) if decision.matched_video_id else None,
        matched_source_name=(
            matched_video.source.name
            if matched_video is not None and matched_video.source is not None
            else None
        ),
        matched_source_url=matched_video.source_url if matched_video else None,
        matched_title=matched_video.title if matched_video else None,
        matched_publication_date=matched_video.publication_ts if matched_video else None,
        explanation=decision.explanation or "",
        warnings=(decision.evidence_report or {}).get("warnings", []),
    )
