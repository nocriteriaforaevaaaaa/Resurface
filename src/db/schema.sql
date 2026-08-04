-- Evidence-Grounded Detection of Old Videos Reposted as Recent News
-- PostgreSQL schema (Section 5.9 "Indexing and Storage", Table 5.1 "Dataset fields")
--
-- Design notes:
--   * Raw video/audio/keyframe files live on disk (data/) or object storage; this schema
--     stores paths and metadata, not binary content.
--   * Dense visual embeddings live in the FAISS index (data/faiss_index/); faiss_vectors
--     below is the join table that maps a FAISS row id back to a video/keyframe.
--   * perceptual hashes are stored directly (fixed-width hex string) since Hamming-distance
--     lookups over a repository of this size do not require a separate ANN structure.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Enumerated types
-- ---------------------------------------------------------------------------

CREATE TYPE event_category AS ENUM (
    'flood', 'landslide', 'earthquake', 'fire', 'severe_weather',
    'protest', 'rally', 'strike', 'political_incident',
    'road_accident', 'aviation_incident', 'infrastructure_failure',
    'public_disorder', 'security_incident', 'emergency_response',
    'cultural_event', 'social_event', 'national_event', 'other'
);

CREATE TYPE decision_label AS ENUM (
    'old_video_reposted_as_recent',
    'recent_or_correctly_contextualised',
    'insufficient_evidence'
);

CREATE TYPE processing_status AS ENUM (
    'pending', 'downloading', 'normalising', 'extracting_features',
    'indexed', 'failed', 'excluded'
);

-- ---------------------------------------------------------------------------
-- Historical repository (Section 5.3, Table 5.1)
-- ---------------------------------------------------------------------------

CREATE TABLE sources (
    source_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                TEXT NOT NULL UNIQUE,
    platform            TEXT,                       -- e.g. 'youtube', 'news_site'
    homepage_url         TEXT,
    reliability_tier     SMALLINT NOT NULL DEFAULT 3 CHECK (reliability_tier BETWEEN 1 AND 5),
    is_verified          BOOLEAN NOT NULL DEFAULT FALSE,
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE videos (
    video_id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id            UUID NOT NULL REFERENCES sources(source_id) ON DELETE RESTRICT,
    source_url           TEXT NOT NULL UNIQUE,
    publication_ts        TIMESTAMPTZ NOT NULL,
    title                 TEXT,
    caption               TEXT,
    event_category        event_category NOT NULL DEFAULT 'other',
    location_text         TEXT,                     -- free-text place name as annotated
    province              TEXT,
    district              TEXT,
    municipality          TEXT,
    duration_seconds       NUMERIC(10, 2),
    video_format           TEXT,                      -- container/codec, e.g. 'mp4/h264'
    raw_file_path          TEXT,                      -- normalised local/object storage path
    checksum_sha256         TEXT UNIQUE,               -- exact-duplicate detection (Sec 5.4 step 2)
    evidence_quality_score  NUMERIC(4, 3) CHECK (evidence_quality_score BETWEEN 0 AND 1),
    status                 processing_status NOT NULL DEFAULT 'pending',
    is_verified_subset      BOOLEAN NOT NULL DEFAULT FALSE, -- Sec 5.4 step 6
    collected_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_videos_publication_ts ON videos (publication_ts);
CREATE INDEX idx_videos_event_category ON videos (event_category);
CREATE INDEX idx_videos_source_id ON videos (source_id);
CREATE INDEX idx_videos_status ON videos (status);

-- One row per scene-detected / interval-based representative frame (Sec 5.5, 5.6).
CREATE TABLE keyframes (
    keyframe_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id              UUID NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    frame_index            INT NOT NULL,               -- ordinal position within the video
    timestamp_seconds        NUMERIC(10, 3) NOT NULL,
    scene_index             INT,                        -- PySceneDetect scene number, if used
    frame_path              TEXT NOT NULL,
    phash                   CHAR(16),                    -- 64-bit perceptual hash, hex-encoded
    faiss_vector_id          BIGINT UNIQUE,               -- row id inside the FAISS index (Sec 5.9)
    embedding_model          TEXT,                        -- e.g. 'ViT-B-32/laion2b_s34b_b79k'
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id, frame_index)
);

CREATE INDEX idx_keyframes_video_id ON keyframes (video_id);
CREATE INDEX idx_keyframes_phash ON keyframes (phash);

CREATE TABLE transcripts (
    transcript_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id              UUID NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    full_text              TEXT,
    segments               JSONB,                       -- [{start, end, text}, ...] Whisper output
    language                TEXT,                        -- detected/dominant language, e.g. 'ne', 'en'
    asr_model                TEXT,                        -- e.g. 'whisper-small'
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id)
);

CREATE TABLE ocr_results (
    ocr_id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id               UUID NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    keyframe_id             UUID REFERENCES keyframes(keyframe_id) ON DELETE CASCADE,
    raw_text                 TEXT,
    cleaned_text              TEXT,
    ocr_engine                TEXT,                        -- 'easyocr' | 'paddleocr'
    confidence                 NUMERIC(4, 3),
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ocr_video_id ON ocr_results (video_id);

-- ---------------------------------------------------------------------------
-- Query-side: incoming posts to be checked against the historical repository
-- ---------------------------------------------------------------------------

CREATE TABLE query_posts (
    query_id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    submitted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_by              TEXT,
    caption_text              TEXT,
    post_url                  TEXT,
    post_timestamp             TIMESTAMPTZ,               -- claimed/observed publication time of the post
    video_file_path             TEXT NOT NULL,
    -- extracted structured claim C_q = {d_q, l_q, e_q} (Eq. 5.4)
    claimed_date               TIMESTAMPTZ,
    claimed_location             TEXT,
    claimed_event_category       event_category,
    status                       processing_status NOT NULL DEFAULT 'pending',
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE query_transcripts (
    query_id      UUID PRIMARY KEY REFERENCES query_posts(query_id) ON DELETE CASCADE,
    full_text      TEXT,
    segments        JSONB,
    language         TEXT,
    asr_model         TEXT
);

CREATE TABLE query_ocr_results (
    query_id      UUID NOT NULL REFERENCES query_posts(query_id) ON DELETE CASCADE,
    frame_index    INT NOT NULL,
    raw_text        TEXT,
    cleaned_text     TEXT,
    PRIMARY KEY (query_id, frame_index)
);

CREATE TABLE query_keyframes (
    query_keyframe_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id            UUID NOT NULL REFERENCES query_posts(query_id) ON DELETE CASCADE,
    frame_index          INT NOT NULL,
    timestamp_seconds     NUMERIC(10, 3) NOT NULL,
    frame_path            TEXT NOT NULL,
    phash                 CHAR(16),
    UNIQUE (query_id, frame_index)
);

-- ---------------------------------------------------------------------------
-- Retrieval + reranking results (Sec 5.10) and final decision (Sec 5.12, 5.13)
-- ---------------------------------------------------------------------------

CREATE TABLE retrieval_candidates (
    candidate_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id              UUID NOT NULL REFERENCES query_posts(query_id) ON DELETE CASCADE,
    video_id               UUID NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    -- Stage 1 fast candidate generation signals
    hash_matches            INT NOT NULL DEFAULT 0,
    visual_frame_matches      INT NOT NULL DEFAULT 0,
    -- Stage 2 multimodal reranking component scores (Eq. 5.3)
    visual_score              NUMERIC(6, 5),
    hash_score                 NUMERIC(6, 5),
    transcript_score            NUMERIC(6, 5),
    ocr_score                    NUMERIC(6, 5),
    metadata_score                NUMERIC(6, 5),
    final_score                    NUMERIC(6, 5),
    temporal_consistent             BOOLEAN,
    rank                             INT,
    created_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (query_id, video_id)
);

CREATE INDEX idx_retrieval_candidates_query_id ON retrieval_candidates (query_id, rank);

CREATE TABLE decisions (
    decision_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id                UUID NOT NULL REFERENCES query_posts(query_id) ON DELETE CASCADE,
    matched_video_id          UUID REFERENCES videos(video_id) ON DELETE SET NULL,
    matched_candidate_id        UUID REFERENCES retrieval_candidates(candidate_id) ON DELETE SET NULL,
    label                        decision_label NOT NULL,
    confidence_score               NUMERIC(4, 3) CHECK (confidence_score BETWEEN 0 AND 1),
    explanation                     TEXT,
    evidence_report                  JSONB,             -- full structured report (Sec 5.13)
    created_at                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (query_id)
);

-- ---------------------------------------------------------------------------
-- Reranking weight configuration (Eq. 5.3), versioned so ablations (Sec 7.5)
-- can reference exactly which weight set produced a given decision.
-- ---------------------------------------------------------------------------

CREATE TABLE reranking_weight_sets (
    weight_set_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    label              TEXT NOT NULL UNIQUE,
    w_visual            NUMERIC(4, 3) NOT NULL,
    w_hash                NUMERIC(4, 3) NOT NULL,
    w_transcript            NUMERIC(4, 3) NOT NULL,
    w_ocr                     NUMERIC(4, 3) NOT NULL,
    w_metadata                  NUMERIC(4, 3) NOT NULL,
    is_active                     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (w_visual + w_hash + w_transcript + w_ocr + w_metadata = 1.000)
);

-- default, evenly-weighted starting point until tuned on a validation set
INSERT INTO reranking_weight_sets (label, w_visual, w_hash, w_transcript, w_ocr, w_metadata, is_active)
VALUES ('default_v0', 0.400, 0.200, 0.200, 0.100, 0.100, TRUE);

-- ---------------------------------------------------------------------------
-- updated_at trigger for videos
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_videos_updated_at
BEFORE UPDATE ON videos
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
