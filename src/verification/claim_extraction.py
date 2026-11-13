"""Structured claim extraction, C_q = {d_q, l_q, e_q} (Section 5.11, Eq. 5.4)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import dateparser
from dateparser.search import search_dates

from src.db.models import EventCategory

_RELATIVE_TERMS = {
    "today", "yesterday", "now", "currently", "just now", "this morning", "tonight",
}

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


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise dateparser/database datetimes to timezone-aware UTC.

    ``dateparser`` returns naive datetimes by default while Postgres
    ``TIMESTAMPTZ`` columns come back aware.  Mixing the two raises
    ``TypeError: can't subtract offset-naive and offset-aware datetimes`` in
    the decision logic, so normalise once here.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date_settings(reference_ts: datetime) -> dict:
    return {
        "RELATIVE_BASE": _as_utc(reference_ts),
        "PREFER_DATES_FROM": "past",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": "UTC",
    }


def _extract_date(
    text: str,
    reference_ts: datetime,
    *,
    search_embedded: bool = True,
) -> datetime | None:
    if not text or not text.strip():
        return None

    lowered = text.lower()
    for term in _RELATIVE_TERMS:
        # Word-boundary match so "know" does not accidentally match "now".
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered):
            parsed = dateparser.parse(term, settings=_date_settings(reference_ts))
            if parsed:
                return _as_utc(parsed)

    if search_embedded:
        # Captions/OCR often contain dates embedded in a sentence, e.g.
        # "Flood in Kathmandu on 1 January 2020".  search_dates handles that.
        try:
            found = search_dates(text, settings=_date_settings(reference_ts))
        except Exception:
            found = None
        if found:
            for _, parsed in found:
                if parsed:
                    return _as_utc(parsed)

    # Transcripts are noisier; only accept a date if the whole text parses.
    parsed = dateparser.parse(text, settings=_date_settings(reference_ts))
    return _as_utc(parsed)


def _extract_event_category(*texts: str) -> EventCategory | None:
    # Check caption first, then OCR, then transcript.  Within a single text the
    # keyword-table order is used as a deterministic tie-breaker.
    for text in texts:
        if not text:
            continue
        lowered = text.lower()
        for category, keywords in _EVENT_KEYWORDS.items():
            if any(kw.lower() in lowered for kw in keywords):
                return category
    return None


def _extract_location(*texts: str) -> str | None:
    # Lightweight rule-based fallback per Table 6.1 ("spaCy or rule-based extraction");
    # a proper Nepali NER model can replace this without changing the return type.
    for text in texts:
        if not text:
            continue
        match = re.search(
            r"\b(?:in|In) ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)*)", text
        )
        if match:
            return match.group(1)
    return None


def extract_claim(
    caption_text: str,
    ocr_text: str,
    transcript_text: str,
    post_timestamp: datetime,
) -> StructuredClaim:
    claimed_date = (
        _extract_date(caption_text, post_timestamp)
        or _extract_date(ocr_text, post_timestamp)
        or _extract_date(transcript_text, post_timestamp, search_embedded=False)
    )
    return StructuredClaim(
        claimed_date=claimed_date,
        claimed_location=_extract_location(caption_text, ocr_text, transcript_text),
        claimed_event_category=_extract_event_category(
            caption_text, ocr_text, transcript_text
        ),
    )
