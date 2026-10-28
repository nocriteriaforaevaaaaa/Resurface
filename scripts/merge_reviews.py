"""Merge the per-reviewer candidate sheets into one master list and report what's left.

Reads data/candidate_videos_reviewer*.xlsx (never modifies them) and writes
data/candidate_videos_merged.xlsx, plus a printed summary of approved / rejected /
undecided rows so the group knows exactly what still needs a decision before import.

Usage: python scripts/merge_reviews.py
"""
from __future__ import annotations

import glob
import sys
from collections import Counter
from pathlib import Path

import openpyxl

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "candidate_videos_merged.xlsx"

# Must match src.db.models.EventCategory; disaster_type values outside it map to "other".
VALID_CATEGORIES = {
    "flood", "landslide", "earthquake", "fire", "severe_weather", "protest", "rally",
    "strike", "political_incident", "road_accident", "aviation_incident",
    "infrastructure_failure", "public_disorder", "security_incident",
    "emergency_response", "cultural_event", "social_event", "national_event", "other",
}


def _flag(value) -> str:
    """Normalise a TRUE/FALSE cell: 'true' | 'false' | 'undecided' (blank, NOT SURE, ...)."""
    if value is True or str(value).strip().lower() == "true":
        return "true"
    if value is False or str(value).strip().lower() == "false":
        return "false"
    return "undecided"


def main() -> int:
    files = sorted(glob.glob(str(DATA / "candidate_videos_reviewer*.xlsx")))
    if not files:
        print("No reviewer files found in data/", file=sys.stderr)
        return 1

    header: list[str] | None = None
    merged: dict[str, dict] = {}
    duplicates: list[str] = []

    for f in files:
        reviewer = Path(f).stem.replace("candidate_videos_", "")
        rows = list(openpyxl.load_workbook(f, read_only=True).active.iter_rows(values_only=True))
        cols = [c for c in rows[0] if c]
        if header is None:
            header = cols
        for values in rows[1:]:
            rec = dict(zip(cols, values))
            url = rec.get("video_url")
            if not url:
                continue  # trailing blank rows
            if url in merged:
                duplicates.append(url)
                continue
            rec["reviewer"] = reviewer
            cat = rec.get("event_category_db") or rec.get("disaster_type")
            rec["event_category_db"] = cat if cat in VALID_CATEGORIES else "other"
            rec["approved_status"] = _flag(rec.get("approved_for_dataset"))
            rec["verified_status"] = _flag(rec.get("verified_real"))
            merged[url] = rec

    out_cols = [c for c in (header or []) if c != "event_category_db"] + [
        "event_category_db", "reviewer", "verified_status", "approved_status",
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(out_cols)
    for rec in merged.values():
        ws.append([rec.get(c) for c in out_cols])
    wb.save(OUT)

    status = Counter(r["approved_status"] for r in merged.values())
    print(f"Merged {len(merged)} unique videos from {len(files)} files -> {OUT.name}")
    print(f"  approved: {status['true']}   rejected: {status['false']}   undecided: {status['undecided']}")
    if duplicates:
        print(f"  DUPLICATE video_urls skipped ({len(duplicates)}): {duplicates}")
    for rec in merged.values():
        if rec["approved_status"] == "undecided":
            print(f"  undecided [{rec['reviewer']}] approved={rec.get('approved_for_dataset')!r} "
                  f"verified={rec.get('verified_real')!r} {rec['video_url']}")
        elif rec["approved_status"] == "true" and rec["verified_status"] != "true":
            print(f"  CHECK approved but verified_real={rec.get('verified_real')!r} "
                  f"[{rec['reviewer']}] {rec['video_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
