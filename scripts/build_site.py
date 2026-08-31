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
            "book": book, "chapter": chapter, "verse": verse,
        }

    distribution = {}
    for lemma_id, book, count in conn.execute(
        "SELECT t.lemma_id, b.name, COUNT(*) FROM token t "
        "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "WHERE t.lemma_id IS NOT NULL GROUP BY t.lemma_id, b.id ORDER BY t.lemma_id, b.id"
    ):
        distribution.setdefault(lemma_id, []).append([book, count])

    # Composition-date ranges, one per tradition per book. These give a word's
    # first appearance a YEAR as well as a reference -- as a range, because the
    # date a book was written is contested.
    dates = {}
    for book, tradition, earliest, latest in conn.execute(
        "SELECT b.name, d.tradition, d.earliest, d.latest FROM composition_date d "
        "JOIN book b ON b.id = d.book_id"
    ):
        dates.setdefault(book, {})[tradition] = [earliest, latest]

    # A caution travels with the version rather than being left for the reader to
    # discover: LXX chapter and verse numbering genuinely differs from the Hebrew
    # and English, most visibly in the Psalms.
    cautions = {
        "lxx-swete": ("Septuagint numbering differs from the Hebrew and English in places, "
                      "the Psalms especially, so this verse may not correspond exactly."),
    }
    versions = [
        {"id": vid, "name": name, "language": language, "year": year, "era": era,
         "from": translated_from, "caution": cautions.get(vid)}
        for vid, name, language, year, era, translated_from in conn.execute(
            "SELECT id, name, language, year, era, translated_from FROM version "
            "ORDER BY CASE WHEN year IS NULL THEN 9999 ELSE year END"
        )
    ]

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

        first = first_ref.get(lemma_id)
        book_dates = dates.get(first["book"]) if first else None
        if first and book_dates:
            first["dates"] = book_dates

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
            # Every recorded meaning is searchable, not just the first. A reader
            # arriving with "propitiation" must reach the words behind it, and
            # that term appears in a later sense than the headline gloss.
            "terms": " ".join(x["gloss"] for x in senses.get(lemma_id, []))[:220],
            # Sort keys for "earliest first appearance". A range cannot be sorted
            # directly, so the declared rule is: sort by the EARLIEST bound of the
            # selected tradition. The rule is stated in the UI rather than hidden.
            "yt": book_dates["traditional"][0] if book_dates else None,
            "yc": book_dates["critical"][0] if book_dates else None,
        })

        detail = {
            "slug": slug,
            "lemma": lemma,
            "xlit": xlit,
            "strongs": strongs,
            "lang": language,
            "count": count,
            "lexicon_source": source_id,
            "first": first,
            "distribution": sorted(distribution.get(lemma_id, []), key=lambda r: -r[1]),
            "senses": senses.get(lemma_id, []),
        }
        (lemma_dir / f"{slug}.json").write_text(
            json.dumps(detail, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        written += 1

    (out_dir / "index.json").write_text(
        json.dumps({"lemmas": index, "sources": sources, "versions": versions},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    verse_dir = out_dir / "verse"
    if verse_dir.exists():
        shutil.rmtree(verse_dir)
    verse_dir.mkdir()

    wanted = {}
    for entry in index:
        pass
    for lemma_id, first in first_ref.items():
        wanted[(first["book"], first["chapter"], first["verse"])] = None

    renderings = {}
    for book, chapter, verse, version_id, text in conn.execute(
        "SELECT b.name, v.chapter, v.verse, r.version_id, r.text FROM rendering r "
        "JOIN verse v ON v.id = r.verse_id JOIN book b ON b.id = v.book_id"
    ):
        key = (book, chapter, verse)
        if key in wanted:
            renderings.setdefault(key, {})[version_id] = text

    for (book, chapter, verse), texts in renderings.items():
        slug = f"{book}.{chapter}.{verse}".replace(" ", "_")
        (verse_dir / f"{slug}.json").write_text(
            json.dumps(texts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    canons = {}
    for name, book, ordering in conn.execute(
        "SELECT m.canon, b.name, m.ordering FROM canon_membership m "
        "JOIN book b ON b.id = m.book_id ORDER BY m.canon, m.ordering"
    ):
        canons.setdefault(name, []).append(book)

    (out_dir / "canons.json").write_text(
        json.dumps(canons, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    stats = {
        "lemmas": len(index),
        "hebrew_tokens": conn.execute(
            "SELECT COUNT(*) FROM token WHERE source_id='oshb-morphhb'").fetchone()[0],
        "greek_tokens": conn.execute(
            "SELECT COUNT(*) FROM token WHERE source_id='morphgnt-sblgnt'").fetchone()[0],
        "senses": conn.execute("SELECT COUNT(*) FROM sense").fetchone()[0],
        "sources": len(sources),
        "renderings": conn.execute("SELECT COUNT(*) FROM rendering").fetchone()[0],
        "versions": len(versions),
        "canons": {name: len(books) for name, books in canons.items()},
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
