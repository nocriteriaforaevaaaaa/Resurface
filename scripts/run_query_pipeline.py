#!/usr/bin/env python
"""Run the full Figure 5.1 pipeline for one pending query post.

Usage:
    python scripts/run_query_pipeline.py <query_id>

The implementation lives in :mod:`src.query.pipeline` so the same code powers
both this CLI and the FastAPI background task used by the web UI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `import src...` work when the script is invoked from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.query.pipeline import run_query_pipeline


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query_id")
    args = parser.parse_args()
    run_query_pipeline(args.query_id)
