# Evidence-Grounded Detection of Old Videos Reposted as Recent News

Nepal-focused multimodal system that detects whether a news video circulating today has
already appeared in a three-year historical repository under a different (older) context,
and produces an evidence-backed decision: **old video reposted as recent**, **recent or
correctly contextualised**, or **insufficient evidence**.

Full design: [`docs/proposal.pdf`](docs/proposal.pdf) (BE Major Project Proposal, Pulchowk
Campus, July 2026).

## Architecture

```
User Interface / REST API (src/api)
        |
Input Validation and Media Normalisation (src/preprocessing/ffmpeg_utils.py)
        |
Multimodal Extraction: Keyframes, Audio, OCR, Caption (src/preprocessing, src/features)
        |
Feature Generation: pHash, OpenCLIP, Transcript/OCR vectors (src/features)
        |
Historical Retrieval: Hash Search + FAISS + Candidate Grouping (src/indexing, src/retrieval)
        |
Multimodal Reranking and Temporal Consistency Check (src/retrieval/reranking.py)
        |
Context Comparison and Decision Logic (src/verification)
        |
Evidence Report and Retrieved Historical Sources (src/api/routes/query.py)
```

## Setup

```bash
# 1. Python environment (3.11 chosen for ML-library wheel compatibility)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Config
cp .env.example .env      # already done for local dev; adjust as needed

# 3. Database (PostgreSQL via Homebrew)
./scripts/setup_db.sh     # creates role/db and applies src/db/schema.sql

# --- OR, via Docker instead of steps 1/3 ---
docker compose up -d db   # Postgres only
docker compose up -d      # Postgres + API container
```

## Populating the historical repository

1. Fill in `config/sources.yaml` with verified Nepali news channels (Section 5.3 of the
   proposal). Each entry needs a real `channel_url`; placeholder rows are skipped.
2. `python scripts/collect_dataset.py` — downloads videos + metadata via yt-dlp, dedups by
   URL and file checksum, inserts `pending` rows into `videos`.
3. `python scripts/build_repository_index.py` — runs FFmpeg normalisation, PySceneDetect
   keyframing, pHash + OpenCLIP embeddings (indexed into FAISS), Whisper transcription, and
   OCR for every pending video.
4. Manually review event category / location / `is_verified_subset` per Section 5.4 steps
   4-6 — these are annotation decisions, not automated.

## Running a query

```bash
uvicorn src.api.main:app --reload
# POST /queries with multipart form: video=<file>, caption_text=..., post_url=...
# then run the pipeline for that query id:
python scripts/run_query_pipeline.py <query_id>
# GET /queries/<query_id>/report
```

## Project layout

```
src/
  api/            FastAPI app + routes + pydantic schemas
  db/             SQLAlchemy models, session, schema.sql (source of truth DDL)
  ingestion/      yt-dlp based data collection (Section 5.4)
  preprocessing/  FFmpeg normalisation, scene detection / keyframing
  features/       pHash, OpenCLIP embeddings, Whisper ASR, OCR
  indexing/       FAISS index management
  retrieval/      Stage 1 candidate generation + Stage 2 reranking (Eq. 5.3)
  verification/   Claim extraction (Eq. 5.4) + decision logic (Section 5.12)
config/
  sources.yaml    Verified news source list (fill in before collection)
data/             Local artefact storage (videos, keyframes, audio, transcripts, OCR,
                  embeddings, FAISS index) -- gitignored except directory placeholders
scripts/          CLI entry points for each pipeline stage
tests/            Smoke tests for the setup itself
docs/proposal.pdf The source project proposal
```

## Database schema

See `src/db/schema.sql` for the canonical DDL (12 tables: `sources`, `videos`,
`keyframes`, `transcripts`, `ocr_results`, `query_posts`, `query_keyframes`,
`query_transcripts`, `query_ocr_results`, `retrieval_candidates`, `decisions`,
`reranking_weight_sets`) and `src/db/models.py` for the mirrored SQLAlchemy ORM layer.

## Known limitations of this initial setup

- `config/sources.yaml` ships with a placeholder entry only -- real verified Nepali news
  channels must be added by the team before running data collection (Section 8.4: only
  publicly accessible, attributable sources).
- Transcript/OCR similarity scoring in `scripts/run_query_pipeline.py` is stubbed at 0.0
  pending a TF-IDF or multilingual sentence-embedding implementation (Section 5.7).
- No Nepali-specific NER model is wired in yet; `claim_extraction.py` uses rule-based
  keyword/regex extraction as an interim per Table 6.1 ("spaCy or rule-based extraction").
- `reranking_weight_sets` starts at an even default (0.4/0.2/0.2/0.1/0.1); Section 7.5's
  ablation study is expected to tune these on a validation set.
