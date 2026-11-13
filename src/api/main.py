"""FastAPI application entry point (Figure 6.1: User Interface / REST API).

Run with: uvicorn src.api.main:app --reload
Then open http://localhost:8000 for the upload-and-verify web UI.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from src.api.routes import health, query

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Evidence-Grounded Detection of Old Videos Reposted as Recent News",
    description="Nepal-focused multimodal retrieval and verification API.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(query.router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
