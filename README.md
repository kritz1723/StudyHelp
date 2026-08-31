# StudyHelp

A Bible study tool for decoding what a verse actually means — by tracing the word,
not by handing over one commentator's opinion.

For a given word, StudyHelp aims to show where it first appears, every other place it
is used, what it meant in the original language, how that meaning shifted over time,
and how different traditions and eras have read it — each claim attributed to a source,
with disagreement shown rather than resolved.

Built on **open-source and public-domain data only**. Anything needing a commercial
licence is recorded in [`BACKLOG.md`](BACKLOG.md) rather than quietly dropped.

## Why the lemma, not the English word

English surface forms are the wrong unit of study. "Love" in the KJV and "love" in a
modern translation may render different Greek lemmas (*agape*, *phileo*, *eros*,
*storge*), and one Greek lemma may be rendered by a dozen different English words across
versions and eras. So an English search is only the *entry point*: it resolves to one or
more lemmas, and every view runs off the lemma.

## Getting started

```bash
python3 scripts/init_db.py          # create the DB, load the source registry + canon
python3 scripts/fetch_sources.py --list
python3 scripts/fetch_sources.py --all   # retrieve datasets into data/raw/
```

Fetched corpora and the generated database are gitignored — the *registry* and the
*fetch log* are what we version, so any dataset can be reproduced and any claim traced.

## Layout

| Path | What it is |
| --- | --- |
| `data/sources/sources.json` | Source registry — every dataset, its licence, attribution and verification status. The single source of truth for provenance. |
| `data/sources/downloads.json` | Concrete retrieval URLs per source, kept separate because URLs rot faster than licences. |
| `data/canon.json` | 66-book canon, 1189 chapters. |
| `db/schema.sql` | SQLite schema. Every text, tag, gloss and sense row carries a `source_id`. |
| `scripts/init_db.py` | Builds the DB and loads the registry and canon. Re-runnable. |
| `scripts/fetch_sources.py` | Fetches datasets and writes a `fetch_log` row (URL, timestamp, bytes, sha256) for every attempt. |
| `docs/word-study-architecture.md` | Data model, the four views, source strategy, build order. |
| `bible-study/js/books.js` | Canon metadata and a loose reference parser (`John 3:16-18`, `1 cor 13`, `Jn`). |
| `BACKLOG.md` | Deferred work and best practices. |

## Provenance

Nothing displayed may exist without a `source_id`. `fetch_log` records the exact URL,
timestamp, byte count and sha256 of every retrieval, so re-fetching later makes upstream
changes visible instead of silent — and any claim on screen can be traced to the precise
bytes it came from.

## Sources

Registered and licence-confirmed:

- [OpenScriptures Hebrew Bible (morphhb)](https://github.com/openscriptures/morphhb) — WLC with morphology, CC BY 4.0
- [STEPBible-Data](https://github.com/STEPBible/STEPBible-Data) — TAHOT/TAGNT tagging and lexicons, CC BY 4.0
- [MorphGNT / SBLGNT](https://github.com/morphgnt/sblgnt) — tagging CC BY-SA 3.0; base text under the SBLGNT EULA
- [Strong's Dictionaries](https://github.com/openscriptures/strongs) — public domain
- [OpenScriptures HebrewLexicon (BDB)](https://github.com/openscriptures/HebrewLexicon) — public domain text
- [Berean Standard Bible](https://berean.bible/downloads.htm) — public domain (2023)
- [LXX Rahlfs 1935](https://github.com/eliranwong/LXX-Rahlfs-1935) / [Swete 1930](https://github.com/eliranwong/LXX-Swete-1930)

The full registry, including candidates still pending a licence check, is in
`data/sources/sources.json`.
