"""Structured claim extraction, C_q = {d_q, l_q, e_q} (Section 5.11, Eq. 5.4)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import dateparser

from src.db.models import EventCategory

_RELATIVE_TERMS = {"today", "yesterday", "now", "currently", "just now", "this morning", "tonight"}

_EVENT_KEYWORDS: dict[EventCategory, list[str]] = {
    EventCategory.flood: ["flood", "बाढी"],
    EventCategory.landslide: ["landslide", "पहिरो"],
    EventCategory.earthquake: ["earthquake", "भूकम्प"],
    EventCategory.fire: ["fire", "आगलागी"],
    EventCategory.protest: ["protest", "rally", "आन्दोलन", "प्रदर्शन"],
    EventCategory.road_accident: ["accident", "crash", "दुर्घटना"],
    EventCategory.political_incident: ["political", "election", "राजनीतिक"],
}


@dataclass
class StructuredClaim:
    claimed_date: datetime | None
    claimed_location: str | None
    claimed_event_category: EventCategory | None


def _extract_date(text: str, reference_ts: datetime) -> datetime | None:
    lowered = text.lower()
    for term in _RELATIVE_TERMS:
        if term in lowered:
            parsed = dateparser.parse(
                term, settings={"RELATIVE_BASE": reference_ts, "PREFER_DATES_FROM": "past"}
            )
            if parsed:
                return parsed
    # fall back to any absolute date mentioned in the caption
    parsed = dateparser.parse(text, settings={"RELATIVE_BASE": reference_ts})
    return parsed


def _extract_event_category(text: str) -> EventCategory | None:
    lowered = text.lower()
    for category, keywords in _EVENT_KEYWORDS.items():
        if any(kw.lower() in lowered for kw in keywords):
            return category
    return None


def _extract_location(text: str) -> str | None:
    # Lightweight rule-based fallback per Table 6.1 ("spaCy or rule-based extraction");
    # a proper Nepali NER model can replace this without changing the return type.
    match = re.search(r"\bin ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)*)", text)
    return match.group(1) if match else None


def extract_claim(
    caption_text: str,
    ocr_text: str,
    transcript_text: str,
    post_timestamp: datetime,
) -> StructuredClaim:
    combined = " ".join(filter(None, [caption_text, ocr_text, transcript_text]))
    return StructuredClaim(
        claimed_date=_extract_date(combined, post_timestamp),
        claimed_location=_extract_location(combined),
        claimed_event_category=_extract_event_category(combined),
    )
