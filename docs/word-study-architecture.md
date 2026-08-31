# StudyHelp — Word Study Architecture (draft)

Status: draft, pending whiteboard review. Written from the stated intent, not yet
validated against the ideation board.

## Goal

A user reads a verse and asks "what does this actually mean?" StudyHelp answers by
tracing the *word*, not by handing over one commentator's opinion:

1. Where the word first appears in Scripture.
2. Every other place it is used.
3. What it meant in the original language at each point.
4. How that meaning shifted chronologically.
5. Which perspectives (traditions, eras, translators) read it differently, presented
   side by side rather than resolved into one answer.

The non-negotiable constraint is **unbiased**: the app shows the spread of evidence and
attributes every claim to a source. It does not adjudicate.

## The core problem

English words are the wrong unit of study. "Love" in a 1611 KJV and "love" in a modern
translation may render different Greek lemmas (agape / phileo / eros / storge), and one
Greek lemma may be rendered by a dozen different English words across versions and eras.

So the spine of the data model is the **lemma** (dictionary form in Hebrew / Aramaic /
Greek), not the English surface form. Everything else hangs off it.

## Data model

```
Verse        (canonical address: book, chapter, verse — version-independent)
Version      (translation: name, language, year, textual family, era)
Rendering    (Verse x Version -> the actual text in that version)
Token        (a word occurrence in the original-language text, tied to a Verse)
Lemma        (dictionary form + language + Strong's / lexicon ids)
Sense        (one attested meaning of a Lemma, with date range and source)
Gloss        (how a given Version renders a given Lemma at a given Token)
Source       (lexicon, manuscript family, commentary — everything is cited)
```

Key relationships:

- `Token -> Lemma` is the morphological tagging layer. This is what makes
  "first occurrence" and "other usages" answerable at all.
- `Lemma -> Sense[]` with date ranges is what makes the *chronological* view possible.
- `Token -> Gloss -> Version` is what makes the *translation drift* view possible:
  one lemma, one verse, N versions, N English words, ordered by version year.

## The four views

**Origin.** First attested occurrence of the lemma in the canon, in canonical order and,
separately, in likely composition order (the two differ, and the difference is itself
interesting). Show the verse, the morphology, and the earliest lexical attestation.

**Usage map.** All occurrences, grouped by book and by genre (law, narrative, prophecy,
wisdom, epistle). Frequency by book is often the fastest route to a real insight —
a word that appears 40 times in Leviticus and twice elsewhere is a cultic term.

**Chronology.** A timeline with two tracks laid over each other:
- *Text track*: occurrences positioned by the composition date of the containing book.
- *Reception track*: how lexicons and translations across eras glossed the lemma —
  LXX, Vulgate, Wycliffe, Tyndale, Geneva, KJV, RV, ASV, RSV, NASB, NIV, ESV, NRSV, CSB.
Reading the two tracks together is the "how it changed over time" answer.

**Perspectives.** For a contested lemma, a panel per tradition/school, each stating its
reading with citation. Presented as a comparison, never merged, never ranked.

## Source acquisition (the hard part)

Copyright, not engineering, is the binding constraint. Plan by tier:

- **Tier 1 — public domain, ship immediately.** KJV (1611/1769), ASV, WEB, YLT, Darby,
  Douay-Rheims, Wycliffe, Tyndale, Geneva; Westcott-Hort, Tischendorf, Textus Receptus,
  Byzantine; Leningrad Codex (WLC); LXX (Rahlfs/Swete); Vulgate. Strong's, Thayer's,
  BDB, Gesenius, Liddell-Scott. This tier alone covers origin, usage, chronology, and
  most of the era-drift story.
- **Tier 2 — freely licensed with attribution.** NET Bible notes, SBLGNT, various
  open-licensed lexica. Check each licence individually; record it in `Source`.
- **Tier 3 — commercial (NIV, ESV, NASB, CSB).** API access under licence, or omit.
  Never scrape. Design the UI so a missing Tier 3 version degrades gracefully rather
  than leaving a hole.

Morphological tagging (the `Token -> Lemma` layer) is available in open datasets:
OpenScriptures Hebrew Bible (OSHB) for the OT, and open morphology-tagged GNT editions
for the NT. This is the single most valuable dataset to land first — without it, none
of the four views work.

## Build order

1. Canon metadata + reference parsing. (done — `bible-study/js/books.js`)
2. Ingest one public-domain English version end to end; get verses on screen.
3. Ingest the tagged original-language text; build the `Token -> Lemma` index.
4. Origin + usage map views. These are pure index queries and prove the model.
5. Add versions across eras; build the gloss table and the drift view.
6. Layer lexicon senses with date ranges; build the chronology view.
7. Perspectives panel last — it depends on everything above being citable.

## Bias controls

These are product requirements, not nice-to-haves:

- Every meaning claim renders with its source and that source's date and tradition.
- Where sources disagree, disagreement is the display — no default winner, no
  "most scholars" phrasing without a citation that says so.
- Ordering of perspectives is stable and declared (e.g. chronological by source date),
  never by editorial preference.
- The app distinguishes *attested* (in a lexicon/corpus) from *inferred* (a synthesis),
  and labels the latter.

## Implemented so far

The source-acquisition plan above is now backed by working infrastructure:

- `data/sources/sources.json` — the registry. Every dataset with its licence,
  attribution and a `verified` date (or `unverified`, meaning the licence claim still
  needs confirming against the licence text).
- `db/schema.sql` — the schema described above, plus a `source` table and a `fetch_log`
  audit table. Every text, tag, gloss, sense and perspective row carries a `source_id`;
  the "unbiased" requirement is enforced by foreign key, not by convention.
- `scripts/init_db.py` / `scripts/fetch_sources.py` — build and populate.

Corpora are fetched on demand into `data/raw/` (gitignored) rather than committed.
Committing multi-megabyte corpora would bloat the repo and, for share-alike and
EULA-bound sources, redistribute them under terms we have not confirmed. The registry
plus the checksummed fetch log reproduces any dataset without either problem.


## Reconciliation with the ideation whiteboard

The board confirmed the lemma-centred spine and added one thing this design had
underweighted: a word study should follow the word **down the transmission chain**,
showing the count and form at each layer, rather than treating each corpus separately.

```
Hebrew OT  ->  Septuagint (Alexandria, c. 200 BC, Greek)  ->  Greek NT  ->  English
```

The worked example on the board was PROPITIATION: an English word, reached through
Greek (hilasmos / hilasterion), which the LXX had already used to render Hebrew
sacrificial vocabulary (kipper / kapporeth). The meaning did not arrive in English
directly from Hebrew -- it travelled, and each stage left a mark.

Consequences for the build:

- **The LXX is the hinge, not a nice-to-have.** It is the only witness to how Hebrew
  vocabulary was being rendered into Greek before the NT was written, so without it
  the chain is broken exactly in the middle. Ingesting it is now the critical path.
- **Per-layer counts are a first-class view.** For a word, show occurrences in the
  Hebrew, in the LXX, in the Greek NT and in each English version -- the shape of
  those four numbers is itself the finding.
- **The board distinguishes PRIMARY sources from the rest.** The registry should mark
  which sources are primary witnesses (tagged original-language texts, manuscripts)
  and which are derivative (translations, aggregators), because the distinction
  changes how much weight a claim carries.
