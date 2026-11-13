"""Unit tests for the lexical transcript/OCR similarity scorer."""
from src.retrieval.text_similarity import normalize_text, text_similarity, token_set


def test_identical_text_scores_one():
    assert text_similarity("flood in nepal today", "flood in nepal today") == 1.0


def test_unrelated_text_scores_zero():
    assert text_similarity("flood in nepal", "earthquake in india") == 0.0


def test_short_query_contained_in_long_transcript_scores_high():
    query = "flood in kathmandu"
    candidate = (
        "Rescue teams continued work in Kathmandu after the flood destroyed "
        "several homes and blocked the main road."
    )
    assert text_similarity(query, candidate) >= 0.6


def test_stopwords_do_not_create_false_matches():
    assert text_similarity("the and of", "the and of") == 0.0


def test_empty_text_scores_zero():
    assert text_similarity("", "flood") == 0.0
    assert text_similarity(None, None) == 0.0


def test_normalize_and_tokens_keep_devanagari():
    text = "बाढी in Nepal!"
    assert "बाढी" in token_set(text)
    assert normalize_text(text) == "बाढी in nepal"
