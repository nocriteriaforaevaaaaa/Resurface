"""Lightweight lexical similarity for transcript and OCR evidence.

The proposal calls for a multilingual text-similarity component in the reranking
stage.  A full sentence-embedding model is intentionally optional here: the
repository is small enough that token-overlap similarity is fast, deterministic,
and works without downloading another model during a demo.

The score is the fraction of query tokens that also occur in the candidate text
(containment), with a Jaccard fallback.  Query-side containment is important
because a short query transcript is often only a fragment of a longer historical
clip.
"""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)

# Small stop-word list for English and romanised/Nepali particles.  This is not
# meant to be exhaustive; it removes the high-frequency tokens that would make
# unrelated news transcripts look artificially similar.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for",
    "from", "had", "has", "have", "he", "her", "his", "i", "in", "is", "it",
    "its", "of", "on", "or", "our", "she", "that", "the", "their", "them",
    "there", "they", "this", "to", "was", "we", "were", "will", "with",
    "you", "your", "को", "का", "मा", "र", "हो", "छ", "छन्", "गर्न", "भएको",
    "एक", "यो", "त्यो", "पनि", "लाई", "बाट", "सँग", "हुन", "गरेको",
}


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(_WORD_RE.findall(text.lower()))


def token_set(text: str | None) -> set[str]:
    return {tok for tok in normalize_text(text).split() if tok not in _STOPWORDS}


def text_similarity(query_text: str | None, candidate_text: str | None) -> float:
    """Return a 0..1 lexical similarity score.

    ``0.0`` means no shared informative tokens; ``1.0`` means every query token
    is present in the candidate.  The score is deliberately asymmetric: a short
    query that is fully contained in a long candidate transcript should score
    highly.
    """
    query_tokens = token_set(query_text)
    candidate_tokens = token_set(candidate_text)
    if not query_tokens or not candidate_tokens:
        return 0.0

    shared = query_tokens & candidate_tokens
    if not shared:
        return 0.0

    containment = len(shared) / len(query_tokens)
    jaccard = len(shared) / len(query_tokens | candidate_tokens)
    return float(min(1.0, max(containment, jaccard)))
