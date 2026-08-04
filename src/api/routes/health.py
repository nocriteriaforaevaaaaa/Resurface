from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.schemas import HealthResponse
from src.db.session import get_db
from src.indexing.faiss_index import load_or_create_index

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    index = load_or_create_index()
    return HealthResponse(status="ok", database=db_status, faiss_index_size=index.ntotal)
