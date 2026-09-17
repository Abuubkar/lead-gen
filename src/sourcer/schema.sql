-- sourcer schema.
--
-- Five tables, matching the vocabulary in CONTEXT.md: a Search Run holds the
-- Businesses discovered under it, each Business holds Contacts and Signals, and
-- a Review State records what the Searcher decided.
--
-- Applied with executescript() every time the database is opened. Every
-- statement is idempotent, so there is no migration tool and no schema version.
-- Tables are STRICT: SQLite enforces the declared column types.

-- One Searcher request for a trade in a city, and its progress.
CREATE TABLE IF NOT EXISTS search_run (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    trade             TEXT    NOT NULL,
    city              TEXT    NOT NULL,
    state             TEXT    NOT NULL,
    -- Run Status: pending | running | done | failed | cancelled
    run_status        TEXT    NOT NULL DEFAULT 'pending',
    -- Progress Note: the line shown while the Search Run is live,
    -- e.g. "enriching 12/30".
    progress_note     TEXT,
    started_at        TEXT,
    finished_at       TEXT,
    discovered_count  INTEGER NOT NULL DEFAULT 0,
    enriched_count    INTEGER NOT NULL DEFAULT 0,
    scored_count      INTEGER NOT NULL DEFAULT 0,
    -- JSON object keyed by Source name: its status, count and any block reason.
    -- An empty column must read as a Source problem, never as an absence of
    -- Businesses, so a blocked Source records itself here.
    source_outcomes   TEXT    NOT NULL DEFAULT '{}',
    error             TEXT,
    created_at        TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_search_run_created ON search_run (created_at DESC);

-- A single company that could be an acquisition target. Scoped to one Search
-- Run: see the spec for why cross-run identity is not attempted.
CREATE TABLE IF NOT EXISTS business (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL REFERENCES search_run (id) ON DELETE CASCADE,

    -- Strongest identity available, resolved in order: normalised website
    -- domain, then normalised phone digits, then normalised name plus street.
    dedup_key          TEXT    NOT NULL,

    name               TEXT    NOT NULL,
    website_url        TEXT,
    website_domain     TEXT,
    phone_display      TEXT,
    phone_digits       TEXT,
    -- Third and weakest dedup input: normalised name plus street.
    name_street_key    TEXT,
    street             TEXT,
    city               TEXT,
    state              TEXT,
    postal_code        TEXT,
    -- JSON array of trade categories as the Source reported them.
    categories         TEXT    NOT NULL DEFAULT '[]',

    -- Filled by Discovery or Enrichment, depending on the Source.
    years_in_business  INTEGER,
    founded_year       INTEGER,
    owner_name         TEXT,
    employee_estimate  TEXT,
    -- Reputation, as the Source reported it. Never part of the Score directly;
    -- it feeds the demand-proof Signals. Named to avoid colliding with Score,
    -- and with the review table, which holds the Searcher's own judgement.
    public_rating      REAL,
    public_review_count INTEGER,
    location_count     INTEGER,
    is_franchise       INTEGER,

    -- JSON array of Source names that contributed to this row.
    sources            TEXT    NOT NULL DEFAULT '[]',
    -- pending | ok | skipped | failed
    enrichment_status  TEXT    NOT NULL DEFAULT 'pending',
    -- Optional one-line outreach angle. Never influences the Score.
    outreach_angle     TEXT,

    score              REAL,
    confidence         REAL,

    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL,

    UNIQUE (run_id, dedup_key)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_business_run     ON business (run_id);
CREATE INDEX IF NOT EXISTS idx_business_domain  ON business (website_domain);
CREATE INDEX IF NOT EXISTS idx_business_phone   ON business (phone_digits);
CREATE INDEX IF NOT EXISTS idx_business_namest ON business (name_street_key);
CREATE INDEX IF NOT EXISTS idx_business_score   ON business (run_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_business_dedup   ON business (dedup_key);

-- A named person reachable at a Business, usually the owner.
CREATE TABLE IF NOT EXISTS contact (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id  INTEGER NOT NULL REFERENCES business (id) ON DELETE CASCADE,
    name         TEXT,
    role         TEXT,
    email        TEXT,
    phone        TEXT,
    source       TEXT    NOT NULL,
    source_url   TEXT,
    confidence   REAL,
    created_at   TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_contact_business ON contact (business_id);

-- One observed fact that moves a Business's Score.
--
-- A row exists even when the Signal could not be resolved: resolved = 0 with
-- points = 0. Confidence is then computable from this table alone, and missing
-- data never costs a Business points.
CREATE TABLE IF NOT EXISTS signal (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id  INTEGER NOT NULL REFERENCES business (id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    -- succession | underinvestment | acquirability | demand
    group_name   TEXT    NOT NULL,
    raw_value    TEXT,
    points       REAL    NOT NULL DEFAULT 0,
    max_points   REAL    NOT NULL,
    resolved     INTEGER NOT NULL DEFAULT 0,
    source       TEXT,
    source_url   TEXT,
    observed_at  TEXT    NOT NULL,

    -- Re-scoring updates a Signal rather than accumulating duplicates.
    UNIQUE (business_id, name)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_signal_business ON signal (business_id);

-- What the Searcher decided about a Business, and their notes.
--
-- Keyed on dedup_key rather than on a Business id, deliberately. Business rows
-- are scoped to a Search Run, so keying the Searcher's own judgement to a
-- Business id would discard it whenever the same search is re-run. There is
-- therefore no foreign key into business here.
CREATE TABLE IF NOT EXISTS review (
    dedup_key   TEXT PRIMARY KEY,
    -- new | contacted | passed
    state       TEXT NOT NULL DEFAULT 'new',
    notes       TEXT,
    updated_at  TEXT NOT NULL
) STRICT;
