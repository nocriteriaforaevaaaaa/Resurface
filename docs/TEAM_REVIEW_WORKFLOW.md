# Team Guide: Reviewing Videos & Processing Them Without Stepping on Each Other

**Who this is for:** the three of you, working from your own computers/Google
Colab notebooks, with no special tools required beyond a browser, Python, and
Google Colab. You do **not** need Claude Code or any AI assistant to follow
this — it's a plain step-by-step guide.

**Goal of this document:** stop duplicate work, and make sure the shared
"brain" of this project (a database + a search index) ends up clean and
correct even though three different people are feeding it.

---

## 0. Five-minute mental model (read this first)

This project is **not** an AI you train. Think of it like building a shared
photo library with a search bar, not teaching a student:

- Each video gets "fingerprinted" automatically by code that's already
  written: a text transcript (Whisper), on-screen text (OCR), a rough visual
  fingerprint (pHash), and a detailed visual "fingerprint vector" (OpenCLIP).
- Those fingerprints get filed into two places:
  - **A database (Neon Postgres)** — like a spreadsheet in the cloud, safe
    for all three of you to write to *at the same time*, as long as you're
    each writing information about *different* videos.
  - **A search index (FAISS, a single file synced via Google Drive)** — like
    a card catalog. Unlike the database, **only one person should be
    updating this file at a time**, or updates can overwrite each other.
- Your job as reviewers is to decide *which videos are real and trustworthy
  enough* to go into this library. The code then does the fingerprinting and
  filing automatically once you tell it "this one's approved."

Keep this one rule in your head for everything below:

> **Database writes (different videos) = always safe, do in parallel.**
> **Search-index writes (the one shared file) = one person at a time.**

---

## 1. Roles & avoiding duplicate review work

1. Open `data/candidate_videos.xlsx` together (Google Sheets or a shared
   Excel file — not three separate copies).
2. Add a column called `assigned_to`.
3. Split the rows three ways by `matched_event` (keep every video from the
   same disaster event with the same reviewer, so nobody needs to
   re-research the same event twice).
4. Each person filters to their own name and **only edits their own rows**.
5. If you finish early, don't touch a teammate's rows — instead grab rows
   from a clearly marked "unclaimed" pool, or ask the group.

**Rule of thumb:** one row, one owner, ever. If two of you review the same
video, you've wasted a third of that step's time for nothing.

---

## 2. What to fill in while reviewing a video

For every row you're assigned, watch the video and fill in:

| Column | What to put |
|---|---|
| `verified_real` | `TRUE` / `FALSE` — is this genuinely real footage of the claimed disaster (not staged, not AI-generated, not footage of a *different* event)? |
| `confidence_note` | **Why** you believe that — e.g. "matches Reuters' footage of the same event," "caption claims a date that doesn't match what's visible." Never leave blank if you marked FALSE. |
| `approved_for_dataset` | `TRUE` / `FALSE` — should this video actually be added to the library? (A real video can still be rejected — e.g. it's a duplicate, or too low quality.) |
| `reviewer_notes` | Anything uncertain, or "need a second opinion." |
| `province` / `district` / `municipality` | Split the existing `location` text into these three separate columns — the database stores them separately, so do the splitting now while you're already looking at the context. |

**One extra thing to flag, don't skip it:** the database only accepts these
disaster categories: `flood`, `landslide`, `earthquake`, `fire`,
`severe_weather`, `protest`, `rally`, `strike`, `political_incident`,
`road_accident`, `aviation_incident`, `infrastructure_failure`,
`public_disorder`, `security_incident`, `emergency_response`,
`cultural_event`, `social_event`, `national_event`, `other`.

`avalanche` is **not** on that list (the Himlung Himal rows use it). For now,
write `other` in a new `event_category_db` column for those rows, and note
in `reviewer_notes` that it was an avalanche — someone can upgrade the
database to support `avalanche` properly later.

---

## 3. Merging reviews into one clean master list

Because you're all editing **one shared sheet**, there's very little to
"merge" — but before anything gets imported into the database:

1. Check no `video_url` was accidentally duplicated or edited. (`video_url`
   is the permanent ID for a video — never retype it.)
2. If two reviewers ever disagree on the same video (shouldn't happen if §1
   is followed), leave `approved_for_dataset` blank until the group looks at
   it together, then write who made the final call and why in
   `reviewer_notes`.
3. Keep `channel_name`, `channel_url`, `published_at` exactly as pulled from
   YouTube — don't "clean up" or guess at these; they feed directly into how
   much the system trusts a source later.

---

## 4. Turning approved rows into real entries (the import step)

**Heads up:** right now, there is no ready-made button for this — someone
needs to write a short script that reads the approved rows from the
spreadsheet and feeds them in, following the exact pattern already used for
a small hand-picked list in `scripts/collect_seed_videos.py`. This is the one
genuine gap in the current project; everything else below already works.

The shape of that script, once written, looks like this:

```python
from src.db.models import EventCategory
from src.db.session import SessionLocal
from src.ingestion.downloader import SeedVideo, collect_specific_videos

my_batch = [
    SeedVideo(source_name="The Independent", video_url="https://www.youtube.com/watch?v=...",
              event_category=EventCategory.flood),
    # ... one entry per approved row assigned to you
]

db = SessionLocal()
collect_specific_videos(db, my_batch)   # downloads the video, checks for duplicates, saves a row
db.close()
```

This step **downloads the video and records it in the shared database as
"pending."** It does **not** touch the search index yet, so:

> **All three of you can run this step at the same time, each on your own
> assigned batch of approved videos.** This is the "database writes to
> different rows" case from §0 — completely safe in parallel.

---

## 5. The one step that must NOT run on all three computers at once

The next step is what actually runs OCR, Whisper, pHash, and OpenCLIP, and
files the results away:

```bash
python scripts/build_repository_index.py
```

This command automatically picks up **every** "pending" video sitting in the
shared database — meaning it will process all three of your approved
batches in one go, regardless of who clicks run. That's intentional and
convenient: **you only need to run this once, by one person, not three
times.**

**Why it must be one person at a time:** this step adds new entries to the
shared search-index file (on Google Drive) after processing each video. If
two people run it simultaneously, the second person's upload can silently
erase the first person's work from that shared file — even though both
people's videos are safely sitting in the database. This is a known,
documented limitation of the syncing method this project uses (last save
wins, not a real "lock").

**How to do it safely, step by step:**

1. Everyone finishes Step 4 (adding their approved batch to the database) —
   this part can happen whenever, in parallel.
2. In your group chat, one person says **"running the processing step now —
   please don't start it too."**
3. That person runs `python scripts/build_repository_index.py` and waits for
   it to finish.
4. They confirm in chat: **"done, all clear."**
5. If the batch is too big to finish in one Colab session, that's fine —
   stop, confirm you're stopped, and resume later. Just never have it running
   in two places simultaneously.

---

## 6. One-time setup so everyone points at the *same* shared place

Do this once as a team (not per-person, except where noted):

1. **One person** creates a free database at [neon.tech](https://neon.tech)
   and copies the connection string shown there.
2. **One person** runs, once:
   ```bash
   ./scripts/apply_schema.sh "postgresql://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require"
   ```
3. **Everyone**, individually, creates a file called `.env` in the project
   folder (copy `.env.example` as a starting point) and puts the **same**
   connection string in it:
   ```
   DATABASE_URL=postgresql+psycopg2://<user>:<password>@<endpoint>.neon.tech/<dbname>?sslmode=require
   ```
   Share this string over a private chat/DM — **never** paste it into a
   public place or commit it to GitHub.
4. **One person** shares a Google Drive folder (named e.g. `EvidenceProject`)
   with the other two, giving them edit access.
5. **Everyone**, individually, runs `rclone config` once to connect their own
   Google account to that *shared* folder (not their own personal Drive
   root). Full click-by-click prompts are in the main `README.md` under
   "Remote storage."

Once this is done, all three of you are reading and writing the same
database and the same shared folder — no code changes needed after this,
the scripts above already use whatever `.env` says.

---

## 7. Keeping things safe if your Colab session disconnects

- Colab's local disk is temporary — anything only saved there vanishes when
  the session ends. This project automatically uploads a finished video's
  files to Google Drive and clears them off local disk as soon as it's
  processed — **but only if your `rclone` is set up (step 6.5 above)**, so do
  that before running anything.
- Your database rows are **never** at risk from a Colab disconnect — they
  live on Neon, not on the Colab machine.
- Don't let the only copy of your spreadsheet progress sit in a Colab
  session. Keep it in Google Sheets (auto-saves) or re-save/commit it after
  every work session.

---

## 8. Sharing your work without leaking secrets or huge files

- **Never share or upload your `.env` file.** It has the database password
  and API keys in it.
- The spreadsheet `data/candidate_videos.xlsx` is small and safe to share/commit
  — it has no video content in it, just text and links.
- Raw videos, audio, keyframe images, and the search-index file are already
  set up to be *excluded* from GitHub (they're too big and disposable, since
  they can always be re-downloaded or re-generated) — don't try to force
  them in.

---

## 9. What to do, in order (quick-reference)

1. **Split** the spreadsheet by event, one owner per row (§1).
2. **Review independently**, in parallel, no special tools needed — just
   watch videos and fill columns (§2).
3. **Briefly sync as a group**, resolve disagreements, lock in final
   `approved_for_dataset` values (§3).
4. **Each person imports their own approved batch** into the shared database
   — safe to do at the same time (§4).
5. **One person, announced in chat, runs the processing step once** — this
   picks up everyone's approved videos together (§5).
6. **Anyone, anytime afterward**, can test the system with a new video and
   get a report back (ask whoever set up the API if you want to try this).

---

## Checklist — print this, or keep it pinned in your group chat

- [ ] I only review/edit rows assigned to me, in the one shared spreadsheet.
- [ ] For every row: watched the video, set `verified_real` with a real
  reason in `confidence_note`, set `approved_for_dataset`, split `location`
  into province/district/municipality.
- [ ] I never changed an existing `video_url`.
- [ ] Anything uncertain went into `reviewer_notes`, not a guess.
- [ ] My `.env` points at the shared Neon database and shared Drive folder.
- [ ] Before running `build_repository_index.py`, I posted in the group
  chat and got a "go ahead" — and confirmed "done" when finished.
- [ ] I never uploaded `.env`, raw videos, or the search-index file to
  GitHub or any public place.

## Known gap (not yet built, don't assume it exists)

There is currently no ready-made script that reads
`data/candidate_videos.xlsx` directly and loads approved rows into the
database — someone needs to write the short script sketched in §4 first.
Everything else in this guide (the database, the processing pipeline, the
Drive sync, the query/search step) already exists and works as described.
