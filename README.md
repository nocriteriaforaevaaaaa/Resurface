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

# 3. Database (PostgreSQL via Homebrew) -- solo/local dev
./scripts/setup_db.sh     # creates role/db and applies src/db/schema.sql

# --- OR, via Docker instead of steps 1/3 ---
docker compose up -d db   # Postgres only
docker compose up -d      # Postgres + API container

# --- OR, for a team sharing one dataset: see "Team setup" below instead of step 3 ---
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

## Remote storage (Google Drive)

Raw videos, normalised copies, audio, and keyframes are bulky and disposable (they can
always be regenerated from the raw video, or re-downloaded from the source URL). To keep
local disk usage small, they are archived to Google Drive and deleted from local disk
immediately after each video finishes processing. Postgres always stays local (see "Team
setup" below for sharing it across machines). The FAISS index also stays local for fast
reads, but -- unlike media files -- it is actively read *and* written by every pipeline
run, so it is kept in sync with Drive rather than archived-and-forgotten (see below).

**One-time setup (interactive -- this step needs you, not me):**

```bash
rclone config
# n) New remote
# name> gdrive
# Storage> drive          (search/select "Google Drive")
# client_id> <enter>       (blank is fine)
# client_secret> <enter>   (blank is fine)
# scope> 1                 (full access)
# root_folder_id> <enter>  (blank = My Drive root)
# service_account_file> <enter>
# Edit advanced config? n
# Use auto config? y       (opens your browser -- log in to the Google account that
#                            owns the 5TB Drive and grant access)
# Configure as team drive? n
# yes this is OK> y
```

Verify it worked:
```bash
rclone lsd gdrive:          # should list your Drive's top-level folders without error
```

That's it -- `settings.rclone_remote` (default `gdrive`) must match the remote name you
picked above. Everything else is automatic:

- `src/storage/remote.py::archive()` uploads a finished video's media to
  `gdrive:EvidenceProject/<same relative path as under data/>` and deletes the local copy
  once the upload is verified. Wired into `src/preprocessing/pipeline.py` right after a
  video reaches `indexed` status.
- `src/storage/remote.py::ensure_local()` transparently re-downloads a file from Drive if
  something later needs it again (reprocessing, human review, ablation studies) --
  wired into every low-level file-reading function (`ffmpeg_utils`, `keyframes`, `phash`,
  `openclip_embed`, `whisper_asr`, `ocr`), so callers never need to know where a file
  currently lives.
- `python scripts/archive_existing.py` backfills already-processed videos that predate
  this feature.
- Set `USE_REMOTE_STORAGE=false` in `.env` to disable archival entirely (e.g. for local
  development without Drive configured) -- `archive()`/`ensure_local()` become no-ops.

If `rclone config` hasn't been run yet, `is_configured()` returns `False` and the pipeline
just leaves files on local disk with a warning logged -- it never blocks or fails
processing because Drive isn't set up.

**FAISS index sync:** `src/storage/remote.py::pull()` downloads the latest shared index
from Drive before a run starts (`build_repository_index.py` and `run_query_pipeline.py`
both call it); `push()` uploads it again after new vectors are added, *without* deleting
the local copy (unlike `archive()`). This is last-write-wins, not a real distributed
lock -- see the caveat in `src/storage/remote.py` and "Team setup" below.

## Team setup (shared dataset across multiple machines)

**Reviewing videos as a team of three? Start with
[`docs/TEAM_REVIEW_WORKFLOW.md`](docs/TEAM_REVIEW_WORKFLOW.md)** — a
step-by-step guide (no Claude Code or AI assistant needed) covering how to
split up video review, avoid duplicate work, and run the processing steps
below without overwriting each other's results.

**Doing that processing step from Google Colab? See [`COLAB.md`](COLAB.md)** —
per-person setup (repo clone, `.env` via Colab Secrets, `rclone` auth saved
across sessions) plus the same one-person-at-a-time rule applied to Colab
specifically.

Two things need to be shared for everyone to work against the *same* dataset, not
diverging local copies: the Postgres database (metadata) and the FAISS index (search
vectors, synced via Drive as described above). Media files are already shared via the
Drive archival described above once everyone points `rclone` at the same folder.

### 1. Shared Postgres (Neon)

Local-only Postgres (`scripts/setup_db.sh`) is fine solo, but for a team, everyone needs
to point at the *same* running instance instead of their own local one. Any managed
Postgres works here (`apply_schema.sh`/`migrate_local_to_remote.sh` are host-agnostic) --
this project uses [Neon](https://neon.tech).

1. One team member creates a free project at [neon.tech](https://neon.tech) and copies
   the connection string shown on the project dashboard ("Connection Details" /
   "Connect" widget). It looks like:
   ```
   postgresql://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require
   ```
   Neon requires `?sslmode=require` -- keep it in the string everywhere below.
2. Apply the schema to it once:
   ```bash
   ./scripts/apply_schema.sh "postgresql://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require"
   ```
3. If you already have local data worth keeping (e.g. an existing test repository),
   migrate it once, after step 2:
   ```bash
   ./scripts/migrate_local_to_remote.sh "postgresql://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require"
   ```
4. **Everyone** (including whoever created the project) sets the same value in their own
   `.env` (never commit this -- share it over a private channel like Slack/DM, not git):
   ```
   DATABASE_URL=postgresql+psycopg2://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require
   ```

From here, every teammate's `videos`/`decisions`/etc. rows land in the same database
automatically -- no code changes, since the app only ever reads `DATABASE_URL`. Note
Neon's free tier auto-suspends the compute after a few minutes idle and wakes on the
next query (~1s cold start) -- normal, not a problem.

### 2. Shared Drive folder

The project owner shares the `EvidenceProject` Drive folder (Editor access) with
teammates. Each teammate authenticates `rclone` with **their own** Google account but
points `root_folder_id` at the *shared* folder's ID instead of their own Drive root, and
sets `RCLONE_REMOTE_ROOT=` (empty) in their `.env` since the remote's root already *is*
that folder. Full walkthrough: see the project's setup notes for the exact `rclone
config` prompts, or ask whoever set up the first Drive connection.

### Concurrency caveat

Both the FAISS sync and Drive archival are last-write-wins, not real distributed locks.
For a small team, the practical rule is operational: **don't run
`scripts/collect_dataset.py` / `build_repository_index.py` at the same moment as a
teammate.** Coordinate in chat ("running the pipeline now") before a collection run.
If this becomes a real bottleneck later, the proper fix is moving vector search from a
local FAISS file to Postgres itself via the `pgvector` extension (Supabase supports it
natively) -- worth considering once the dataset and team are bigger.

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
  storage/        Google Drive archival via rclone (see "Remote storage" above)
config/
  sources.yaml    Verified news source list (fill in before collection)
data/             Local artefact storage (videos, keyframes, audio, transcripts, OCR,
                  embeddings, FAISS index) -- gitignored except directory placeholders
scripts/          CLI entry points for each pipeline stage, incl. apply_schema.sh and
                  migrate_local_to_remote.sh for team Postgres setup
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
