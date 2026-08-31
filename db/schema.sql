-- StudyHelp provenance and word-study schema (SQLite).
--
-- Design rule: nothing the app displays may exist without a source_id. Every
-- text, tag, gloss and sense row carries provenance back to the `source` table,
-- so any claim on screen can be attributed. This is what makes the "unbiased"
-- requirement enforceable rather than aspirational.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Provenance
-- ---------------------------------------------------------------------------

-- One row per dataset we draw on, mirroring data/sources/sources.json.
CREATE TABLE IF NOT EXISTS source (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL,   -- translation | original_text_tagged | lexicon | ancient_version | aggregator | index
    language      TEXT,            -- ISO 639-3, comma-separated where a source spans languages
    year          INTEGER,         -- publication year of the edition, where meaningful
    era           TEXT,            -- middle_english | early_modern | modern_early | contemporary | ancient
    description   TEXT,
    license       TEXT NOT NULL,
    attribution   TEXT,            -- the exact credit line the licence requires
    homepage      TEXT,
    repository    TEXT,
    formats       TEXT,            -- JSON array
    tier          TEXT,            -- 1 = usable now, 2 = open with conditions, 3 = licensed/commercial
    priority      TEXT,
    verified      TEXT,            -- ISO date the licence was confirmed, or 'unverified'
    notes         TEXT
);

-- One row per actual retrieval. This is the audit trail: what we fetched, from
-- where, when, and the checksum of what came back. Re-fetching the same source
-- later produces a new row, so upstream changes are visible rather than silent.
CREATE TABLE IF NOT EXISTS fetch_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id      TEXT NOT NULL REFERENCES source(id),
    url            TEXT NOT NULL,   -- the exact URL retrieved, not the homepage
    fetched_at     TEXT NOT NULL,   -- ISO 8601 UTC
    http_status    INTEGER,
    bytes          INTEGER,
    sha256         TEXT,            -- checksum of the retrieved payload
    local_path     TEXT,            -- where it landed on disk
    upstream_ref   TEXT,            -- commit sha / release tag / edition, when the source exposes one
    ok             INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);

CREATE INDEX IF NOT EXISTS idx_fetch_log_source ON fetch_log(source_id, fetched_at);

-- ---------------------------------------------------------------------------
-- Canon and text
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS book (
    id          INTEGER PRIMARY KEY,   -- canonical order
    name        TEXT NOT NULL UNIQUE,
    abbr        TEXT NOT NULL,
    chapters    INTEGER NOT NULL,
    testament   TEXT NOT NULL CHECK (testament IN ('OT', 'NT')),
    -- Composition date is contested and source-dependent; it drives the
    -- chronology view, so it is stored as a range with its own attribution.
    composed_earliest INTEGER,
    composed_latest   INTEGER,
    composition_source_id TEXT REFERENCES source(id)
);

-- Version-independent verse address. Verse divisions themselves vary between
-- traditions; `versification` records which scheme this address belongs to.
CREATE TABLE IF NOT EXISTS verse (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id       INTEGER NOT NULL REFERENCES book(id),
    chapter       INTEGER NOT NULL,
    verse         INTEGER NOT NULL,
    versification TEXT NOT NULL DEFAULT 'kjv',
    UNIQUE (book_id, chapter, verse, versification)
);

-- A translation or edition. Distinct from `source`: one source may supply
-- several versions, and one version may be available from several sources.
CREATE TABLE IF NOT EXISTS version (
    id             TEXT PRIMARY KEY,
    source_id      TEXT NOT NULL REFERENCES source(id),
    name           TEXT NOT NULL,
    language       TEXT NOT NULL,
    year           INTEGER,
    era            TEXT,
    -- Which text a version was translated FROM. Wycliffe rendering the Vulgate
    -- rather than the Greek is a fact the drift view must not hide.
    translated_from TEXT,
    textual_family  TEXT,           -- e.g. textus_receptus | alexandrian | byzantine | masoretic
    license         TEXT
);

CREATE TABLE IF NOT EXISTS rendering (
    verse_id   INTEGER NOT NULL REFERENCES verse(id),
    version_id TEXT NOT NULL REFERENCES version(id),
    text       TEXT NOT NULL,
    PRIMARY KEY (verse_id, version_id)
);

-- ---------------------------------------------------------------------------
-- Lemma layer -- the spine of the word study
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lemma (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma          TEXT NOT NULL,       -- dictionary form in the original script
    transliteration TEXT,
    language       TEXT NOT NULL CHECK (language IN ('hbo', 'arc', 'grc')),
    strongs        TEXT,                -- interchange key across datasets (H430, G26, ...)
    source_id      TEXT NOT NULL REFERENCES source(id),
    UNIQUE (lemma, language, strongs)
);

CREATE INDEX IF NOT EXISTS idx_lemma_strongs ON lemma(strongs);

-- A single word occurrence in the original-language text. This table is what
-- makes "where did it first appear" and "show me every other usage" answerable.
CREATE TABLE IF NOT EXISTS token (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_id   INTEGER NOT NULL REFERENCES verse(id),
    position   INTEGER NOT NULL,     -- word order within the verse
    surface    TEXT NOT NULL,        -- inflected form as it stands in the text
    lemma_id   INTEGER REFERENCES lemma(id),
    morphology TEXT,                 -- parsing code, as given by the tagging source
    source_id  TEXT NOT NULL REFERENCES source(id),
    UNIQUE (verse_id, position, source_id)
);

CREATE INDEX IF NOT EXISTS idx_token_lemma ON token(lemma_id);
CREATE INDEX IF NOT EXISTS idx_token_verse ON token(verse_id);

-- One attested meaning of a lemma, per lexicon. Multiple rows per lemma is the
-- normal case and the point: disagreement between lexicons is displayed, not
-- resolved. `attested` separates evidence from synthesis.
CREATE TABLE IF NOT EXISTS sense (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id     INTEGER NOT NULL REFERENCES lemma(id),
    gloss        TEXT NOT NULL,
    definition   TEXT,
    period_start INTEGER,   -- approximate years; negative for BCE
    period_end   INTEGER,
    register     TEXT,      -- cultic | legal | poetic | everyday | ...
    source_id    TEXT NOT NULL REFERENCES source(id),
    attested     INTEGER NOT NULL DEFAULT 1,  -- 1 = in a lexicon/corpus, 0 = inferred synthesis
    ordering     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sense_lemma ON sense(lemma_id);

-- How a given version rendered a given original-language token. One lemma x
-- many versions, ordered by version year, is the translation-drift view.
CREATE TABLE IF NOT EXISTS gloss (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id   INTEGER NOT NULL REFERENCES token(id),
    version_id TEXT NOT NULL REFERENCES version(id),
    text       TEXT NOT NULL,      -- the actual word(s) used in that version
    source_id  TEXT NOT NULL REFERENCES source(id),
    UNIQUE (token_id, version_id)
);

CREATE INDEX IF NOT EXISTS idx_gloss_version ON gloss(version_id);

-- An interpretive reading attributed to a tradition or school. Never merged,
-- never ranked; `ordering` is declared (by source date) rather than editorial.
CREATE TABLE IF NOT EXISTS perspective (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id    INTEGER REFERENCES lemma(id),
    verse_id    INTEGER REFERENCES verse(id),
    tradition   TEXT NOT NULL,
    position    TEXT NOT NULL,
    source_id   TEXT NOT NULL REFERENCES source(id),
    source_year INTEGER,
    ordering    INTEGER
);
