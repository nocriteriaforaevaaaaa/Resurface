# Running This Project on Google Colab (3-person shared setup)

**Who this is for:** you've already (1) finished reviewing `data/candidate_videos.xlsx`
as a team, (2) created a shared Neon Postgres project, and (3) set up a shared Google
Drive folder — per `docs/TEAM_REVIEW_WORKFLOW.md` and the main `README.md`'s "Team
setup" section. This doc is the next step: actually running the download +
feature-extraction pipeline from three separate Colab notebooks so you all work
against the *same* dataset, not three diverging copies.

If you haven't done the Neon/Drive setup yet, stop and do that first — this doc
assumes it already exists.

---

## 0. The one thing that makes Colab different from a laptop

A Colab notebook is a **brand-new, empty virtual machine every time you open it**
(or after it disconnects from inactivity). Nothing you installed or configured
last session is still there. So every session needs to redo: cloning the repo,
installing dependencies, and recreating `.env` + your `rclone` config.

The fix is to do the slow/interactive parts (installing, authenticating rclone)
**once**, save the results, and then just *restore* those saved results at the
start of every future session instead of repeating the slow steps.

The same concurrency rule from `docs/TEAM_REVIEW_WORKFLOW.md` still applies here —
it's the whole reason this doc exists:

> **Database writes (different videos) = always safe, do in parallel on all 3 Colabs.**
> **FAISS search-index writes = one person's Colab at a time.**

---

## 1. Per-person one-time setup (each of you does this once, on your own Google account)

Run this in a Colab cell:

```python
# --- Runtime: Runtime menu -> Change runtime type -> GPU (T4 is fine) ---

!git clone https://github.com/nocriteriaforaevaaaaa/Resurface.git
%cd Resurface

# openai-whisper's setup.py needs this installed first (see requirements.txt comment)
!pip install -q "setuptools<81"
!pip install -q --no-build-isolation openai-whisper
!pip install -q -r requirements.txt
```

### 1a. Set up `.env` using Colab Secrets (don't paste secrets into a cell)

Click the **key icon (🔑)** in the left sidebar of Colab → add these as secrets
(name on the left, value on the right), using the values the team already agreed
on for the shared Neon DB:

| Secret name | Value |
|---|---|
| `DATABASE_URL` | the shared Neon connection string (ask whoever created it — see `README.md` "Team setup") |
| `YOUTUBE_DATA_API_KEY` | only needed if you're also running discovery, not required for processing |

Then, in a cell, write them into a real `.env` file (notebook access to a secret
must be explicitly granted the first time you run this — Colab will prompt you):

```python
from google.colab import userdata

env_contents = f"""
DATABASE_URL={userdata.get('DATABASE_URL')}
USE_REMOTE_STORAGE=true
RCLONE_REMOTE=gdrive
RCLONE_REMOTE_ROOT=
TORCH_DEVICE=auto
"""
with open(".env", "w") as f:
    f.write(env_contents)
```

Note `RCLONE_REMOTE_ROOT=` is **empty** here, not `EvidenceProject` — because (per
step 2 below) your rclone remote's root *is already* the shared folder, so there's
no extra subfolder to add on top. This matches the README's "Team setup → Shared
Drive folder" instructions.

### 1b. Set up `rclone`, authenticated as *your own* Google account, pointed at the *shared* folder

```bash
!curl https://rclone.org/install.sh | sudo bash
!rclone config
```

Colab has no browser that can receive an OAuth redirect, so when `rclone config`
asks `Use auto config?`, answer **no**. It will print a link — open it in a new
browser tab on your own computer (not inside Colab), log in with your own Google
account, and paste the verification code it gives you back into the Colab prompt.

When it asks for `root_folder_id`, enter the **shared folder's ID** (the long id
in the shared `EvidenceProject` folder's URL — whoever owns the Drive folder can
get this from Drive's "Get link" option), not your own Drive root. Name the remote
`gdrive` so it matches `RCLONE_REMOTE=gdrive` in `.env`.

Verify it worked:

```bash
!rclone lsd gdrive:
```

### 1c. Save your rclone config so you don't have to redo step 1b every session

```python
# run this once, right after 1b succeeds
from google.colab import drive
drive.mount('/content/drive')
!mkdir -p "/content/drive/MyDrive/rclone_backup"
!cp /root/.config/rclone/rclone.conf "/content/drive/MyDrive/rclone_backup/rclone.conf"
```

This saves it to *your own* personal Drive (not the shared project folder) — it's
just a private backup of your own auth token so future sessions can restore it
instead of repeating the interactive login.

---

## 2. Every new session after that (fast — do this every time you reopen Colab)

```python
!git clone https://github.com/nocriteriaforaevaaaaa/Resurface.git
%cd Resurface
!pip install -q "setuptools<81"
!pip install -q --no-build-isolation openai-whisper
!pip install -q -r requirements.txt

from google.colab import userdata, drive
env_contents = f"""
DATABASE_URL={userdata.get('DATABASE_URL')}
USE_REMOTE_STORAGE=true
RCLONE_REMOTE=gdrive
RCLONE_REMOTE_ROOT=
TORCH_DEVICE=auto
"""
with open(".env", "w") as f:
    f.write(env_contents)

drive.mount('/content/drive')
!mkdir -p /root/.config/rclone
!cp "/content/drive/MyDrive/rclone_backup/rclone.conf" /root/.config/rclone/rclone.conf
!rclone lsd gdrive:   # sanity check — should list the shared folder's contents
```

If that last line errors, your saved config is stale or wrong — redo step 1b.

---

## 3. Importing your team's approved videos (safe to do on all 3 Colabs at once)

This is the script sketched in `docs/TEAM_REVIEW_WORKFLOW.md` §4 — it doesn't
exist yet as a ready-made file, so for now run it inline, once per person, using
only *your own assigned, approved* rows:

```python
from src.db.models import EventCategory
from src.db.session import SessionLocal
from src.ingestion.downloader import SeedVideo, collect_specific_videos

my_batch = [
    SeedVideo(source_name="Kantipur TV HD", video_url="https://www.youtube.com/watch?v=...",
              event_category=EventCategory.flood),
    # ... one entry per row YOU marked approved_for_dataset = TRUE
]

db = SessionLocal()
collect_specific_videos(db, my_batch)
db.close()
```

This downloads each video and inserts a `pending` row into the **shared** Neon
database. Each of you is writing different video rows, so all three can run this
at the same moment with no conflict — this is the "database writes = parallel-safe"
case.

---

## 4. Processing — the one step that must run on only ONE Colab at a time

```bash
!python scripts/build_repository_index.py
```

This single command automatically picks up **every** `pending` video sitting in
the shared database right now — meaning once all three of you have finished step 3,
**only one person needs to run this, one time**, not three separate runs.

Coordinate in your group chat exactly like `docs/TEAM_REVIEW_WORKFLOW.md` §5 says:
announce "running it now," wait, confirm "done." Running it from two Colabs at the
same moment risks one person's upload to the shared FAISS index file silently
overwriting the other's — a real, documented limitation of the Drive-sync method
this project uses (last-write-wins, not a real lock), not a hypothetical risk.

If the batch is large and your Colab session times out partway through: that's
fine, just don't start a second run elsewhere while the first might still be
retryable — confirm in chat that the first attempt is fully stopped before anyone
tries again.

---

## 5. How "one person's changes show up for everyone else" actually works

- **Database rows** (`videos`, `keyframes`, `transcripts`, etc.): instant — Neon is
  one live shared database, so the moment anyone's script commits a row, it's
  there for everyone's next query, no sync step needed.
- **Media files** (raw video, audio, keyframes): archived to the shared Drive
  folder automatically right after processing (`src/storage/remote.py::archive()`),
  visible to the other two as soon as their own `rclone` is pointed at the same
  shared folder.
- **The FAISS search index**: this is the one piece that needs an explicit sync —
  the pipeline code already calls `pull()` before searching/adding and `push()`
  after, so as long as your `rclone` is correctly configured (step 1b/2), you
  don't need to do anything extra — just don't run the index-writing step
  (`build_repository_index.py` or a live query) on two Colabs at the exact same
  moment (step 4).

---

## 6. Common Colab-specific problems

| Symptom | Cause | Fix |
|---|---|---|
| `rclone lsd gdrive:` fails after reopening Colab | Saved config wasn't restored, or went stale | Redo step 1b, then re-save per 1c |
| Everything "disappeared" after a disconnect | Colab's local disk is wiped on disconnect — this is expected | Nothing lost *if* rclone/`.env` were set up before you ran anything — DB rows live on Neon, media archives to Drive; only unsaved local-only work is at risk |
| `openai-whisper` fails to install | `setuptools>=81` removed something it needs | Make sure the `setuptools<81` pip install runs **before** installing `openai-whisper`, exactly as shown above |
| Two people's `build_repository_index.py` runs collide | No real lock on the Drive-synced FAISS file | Always announce in chat first — see §4 |
| GPU not being used / things running slowly | Runtime not set to GPU | Runtime menu → Change runtime type → GPU, *before* running any cells |

---

## See also

- [`docs/TEAM_REVIEW_WORKFLOW.md`](docs/TEAM_REVIEW_WORKFLOW.md) — how to split and
  review `data/candidate_videos.xlsx` as a team of three (the step before this one).
- `README.md` → "Remote storage" and "Team setup" sections — the full non-Colab-specific
  explanation of the Neon + Drive setup this doc builds on.
