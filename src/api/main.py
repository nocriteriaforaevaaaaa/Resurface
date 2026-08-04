"""FastAPI application entry point (Figure 6.1: User Interface / REST API).

Run with: uvicorn src.api.main:app --reload
"""
from fastapi import FastAPI

from src.api.routes import health, query

app = FastAPI(
    title="Evidence-Grounded Detection of Old Videos Reposted as Recent News",
    description="Nepal-focused multimodal retrieval and verification API.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(query.router)
