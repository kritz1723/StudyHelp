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
python3 scripts/init_db.py            # create the DB, load the source registry + canon
python3 scripts/fetch_sources.py --all  # retrieve the corpora into data/raw/ (~47 MB)
python3 scripts/ingest.py --all       # parse them into the database
python3 scripts/word_study.py H430    # study a word
python3 scripts/build_site.py         # generate the static site into site/
```

Then, for example:

```
$ python3 scripts/word_study.py H2403

חַטָּאָה  (chaṭṭâʼâh)   H2403   [hbo]
299 occurrence(s) in the tagged text

First appearance (canonical order)
  Genesis 4:7   חַטָּ֣את      [source: oshb-morphhb]

Where it clusters
  Leviticus       82  ############################
  Numbers         43  ###############
  Ezekiel         26  #########
```

The concentration in Leviticus and Numbers is the kind of finding the app exists to
surface: a word clustered in the sacrificial legislation is a cultic term, and the
distribution says so before any commentary does.

Run the tests with `python3 -m unittest discover tests` and `node tests/books.test.js`.

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
| `scripts/ingest.py` | Parses Strong's, OSHB (Hebrew) and MorphGNT (Greek) into `lemma`/`sense`/`token`. |
| `scripts/word_study.py` | CLI: first appearance, distribution, attested meanings — with sources. |
| `scripts/build_site.py` | Generates the static site (search index + one JSON per lemma) from the DB. |
| `web/` | Front end: search, disambiguation, lemma detail. No framework, no backend. |
| `tests/` | Canon integrity, registry validity, schema provenance, corpus spot-checks, reference parser. |
| `docs/word-study-architecture.md` | Data model, the four views, source strategy, build order. |
| `bible-study/js/books.js` | Canon metadata and a loose reference parser (`John 3:16-18`, `1 cor 13`, `Jn`). |
| `BACKLOG.md` | Deferred work and best practices. |

## What is loaded

| | |
| --- | --- |
| Hebrew tokens (OSHB / WLC) | 306,785 |
| Greek tokens (MorphGNT / SBLGNT) | 137,554 |
| Lemmas with Strong's entries | 14,197 |
| Attested senses | 28,367 |
| Greek tokens linked to Strong's | 98.5% |

Spot-checked against independently known counts: *elohim* (H430) 2,600 occurrences
first at Genesis 1:1; *agape* (G26) 116 occurrences first at Matthew 24:12, clustering
in 1 John. These are asserted in the test suite so parser regressions surface fast.

## Deployment

GitHub Actions builds and publishes the site to GitHub Pages on every push to `main`
(`.github/workflows/deploy.yml`). The database is rebuilt from the source registry on
each run, so what ships always traces back to the registered sources rather than to a
checked-in snapshot. The corpus spot-checks run against the very database the site is
built from, so a parser regression fails the deploy instead of shipping.

The site is fully static — a search index plus one JSON file per lemma — so Pages can
serve it with no backend.

**One-time setup:** in the repository settings, under Pages, set the source to
**GitHub Actions**. Until that is done the deploy job will fail at the publish step.

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
