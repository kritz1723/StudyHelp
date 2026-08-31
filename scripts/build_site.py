#!/usr/bin/env python3
"""Generate the static word-study site from the database.

    python3 scripts/build_site.py [--out site]

Produces a search index plus one JSON file per lemma, so the site is a static
bundle that GitHub Pages can serve with no backend. Every lemma page carries the
source of each claim, exactly as the CLI does.
"""

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "studyhelp.db"
WEB = ROOT / "web"


def build(conn, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    lemma_dir = out_dir / "lemma"
    if lemma_dir.exists():
        shutil.rmtree(lemma_dir)
    lemma_dir.mkdir()

    sources = {
        row[0]: {"id": row[0], "name": row[1], "license": row[2],
                 "attribution": row[3], "url": row[4] or row[5]}
        for row in conn.execute(
            "SELECT id, name, license, attribution, repository, homepage FROM source"
        )
    }

    # Occurrence counts and first appearance in one pass each, rather than a
    # query per lemma -- 14k round trips is the difference between a 2-second
    # build and a 5-minute one.
    counts = dict(
        conn.execute("SELECT lemma_id, COUNT(*) FROM token WHERE lemma_id IS NOT NULL GROUP BY lemma_id")
    )

    first_ref = {}
    for lemma_id, book, chapter, verse, surface, token_source in conn.execute(
        "SELECT t.lemma_id, b.name, v.chapter, v.verse, t.surface, t.source_id FROM token t "
        "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "WHERE t.lemma_id IS NOT NULL "
        "ORDER BY t.lemma_id, b.id DESC, v.chapter DESC, v.verse DESC, t.position DESC"
    ):
        # Descending order means the last row written per lemma is the earliest.
        # The source recorded here is the TAGGED TEXT the occurrence comes from,
        # not the lexicon that supplied the lemma -- attributing a first
        # appearance to a dictionary would be a straightforward misattribution.
        first_ref[lemma_id] = {
            "ref": f"{book} {chapter}:{verse}", "surface": surface, "source": token_source,
        }

    distribution = {}
    for lemma_id, book, count in conn.execute(
        "SELECT t.lemma_id, b.name, COUNT(*) FROM token t "
        "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "WHERE t.lemma_id IS NOT NULL GROUP BY t.lemma_id, b.id ORDER BY t.lemma_id, b.id"
    ):
        distribution.setdefault(lemma_id, []).append([book, count])

    senses = {}
    for lemma_id, gloss, definition, source_id, attested in conn.execute(
        "SELECT lemma_id, gloss, definition, source_id, attested FROM sense ORDER BY lemma_id, ordering, id"
    ):
        senses.setdefault(lemma_id, []).append(
            {"gloss": gloss, "definition": definition, "source": source_id, "attested": bool(attested)}
        )

    index = []
    written = 0
    for lemma_id, lemma, xlit, strongs, language, source_id in conn.execute(
        "SELECT id, lemma, transliteration, strongs, language, source_id FROM lemma ORDER BY id"
    ):
        count = counts.get(lemma_id, 0)
        slug = strongs or f"L{lemma_id}"

        index.append({
            "slug": slug,
            "lemma": lemma,
            "xlit": xlit,
            "strongs": strongs,
            "lang": language,
            "n": count,
            # The first gloss doubles as the English search target: users arrive
            # with an English word, not a Strong's number.
            "gloss": (senses.get(lemma_id, [{}])[0].get("gloss") or "")[:120],
        })

        detail = {
            "slug": slug,
            "lemma": lemma,
            "xlit": xlit,
            "strongs": strongs,
            "lang": language,
            "count": count,
            "lexicon_source": source_id,
            "first": first_ref.get(lemma_id),
            "distribution": sorted(distribution.get(lemma_id, []), key=lambda r: -r[1]),
            "senses": senses.get(lemma_id, []),
        }
        (lemma_dir / f"{slug}.json").write_text(
            json.dumps(detail, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        written += 1

    (out_dir / "index.json").write_text(
        json.dumps({"lemmas": index, "sources": sources}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    stats = {
        "lemmas": len(index),
        "hebrew_tokens": conn.execute(
            "SELECT COUNT(*) FROM token WHERE source_id='oshb-morphhb'").fetchone()[0],
        "greek_tokens": conn.execute(
            "SELECT COUNT(*) FROM token WHERE source_id='morphgnt-sblgnt'").fetchone()[0],
        "senses": conn.execute("SELECT COUNT(*) FROM sense").fetchone()[0],
        "sources": len(sources),
    }
    (out_dir / "stats.json").write_text(json.dumps(stats), encoding="utf-8")

    for asset in WEB.iterdir():
        shutil.copy2(asset, out_dir / asset.name)

    print(f"Built {out_dir}: {written} lemma files, {stats['lemmas']} indexed.")
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(ROOT / "site"))
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        build(conn, Path(args.out))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
