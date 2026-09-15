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


def first_gloss(grouped):
    """The headline gloss, taken from whichever authority comes first."""
    if not grouped:
        return ""
    for entries in grouped.values():
        if entries:
            return entries[0].get("gloss") or ""
    return ""


def build(conn, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    lemma_dir = out_dir / "lemma"
    if lemma_dir.exists():
        shutil.rmtree(lemma_dir)
    lemma_dir.mkdir()

    sources = {
        row[0]: {"id": row[0], "name": row[1], "license": row[2],
                 "attribution": row[3], "url": row[4] or row[5],
                 "witness": row[6], "tradition": row[7], "verified": row[8]}
        for row in conn.execute(
            "SELECT id, name, license, attribution, repository, homepage, "
            "witness, tradition, verified FROM source"
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

    genres = dict(conn.execute("SELECT name, genre FROM book"))
    distribution, by_genre = {}, {}
    for lemma_id, book, count in conn.execute(
        "SELECT t.lemma_id, b.name, COUNT(*) FROM token t "
        "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "WHERE t.lemma_id IS NOT NULL GROUP BY t.lemma_id, b.id ORDER BY t.lemma_id, b.id"
    ):
        distribution.setdefault(lemma_id, []).append([book, count])
        genre = genres.get(book) or "other"
        totals = by_genre.setdefault(lemma_id, {})
        totals[genre] = totals.get(genre, 0) + count

    # "Earliest" has two defensible answers. Canonical order is the order books
    # are printed in; composition order is when they were probably written, and
    # the two differ. Both are shown rather than one being chosen silently.
    composed = {}
    for book, tradition, earliest in conn.execute(
        "SELECT b.name, d.tradition, d.earliest FROM composition_date d "
        "JOIN book b ON b.id = d.book_id"
    ):
        composed.setdefault(tradition, {})[book] = earliest

    earliest_written = {}
    for tradition, book_dates in composed.items():
        for lemma_id, books in distribution.items():
            best = min(
                (b for b, _ in books if b in book_dates),
                key=lambda b: book_dates[b], default=None,
            )
            if best is not None:
                earliest_written.setdefault(lemma_id, {})[tradition] = [best, book_dates[best]]

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
         "from": translated_from, "tradition": tradition, "caution": cautions.get(vid)}
        for vid, name, language, year, era, translated_from, tradition in conn.execute(
            "SELECT id, name, language, year, era, translated_from, tradition FROM version "
            "ORDER BY CASE WHEN year IS NULL THEN 9999 ELSE year END"
        )
    ]

    # How each word has actually been rendered, per gloss source. This is the
    # translation-drift view in miniature: one original word, the spread of words
    # it became, and how often each was chosen.
    renderings_by_lemma = {}
    for lemma_id, version_id, text, count in conn.execute(
        "SELECT t.lemma_id, g.version_id, g.text, COUNT(*) c FROM gloss g "
        "JOIN token t ON t.id = g.token_id WHERE t.lemma_id IS NOT NULL "
        "AND g.version_id NOT LIKE 'interlinear-%' "
        "GROUP BY t.lemma_id, g.version_id, g.text ORDER BY t.lemma_id, g.version_id, c DESC"
    ):
        renderings_by_lemma.setdefault(lemma_id, {}).setdefault(version_id, []).append([text, count])

    # Senses are grouped by the authority that gives them. Two authorities saying
    # different things is the point, so they are never merged into one list.
    senses = {}
    for lemma_id, gloss, definition, source_id, attested in conn.execute(
        "SELECT lemma_id, gloss, definition, source_id, attested FROM sense "
        "ORDER BY lemma_id, source_id, ordering, id"
    ):
        senses.setdefault(lemma_id, {}).setdefault(source_id, []).append(
            {"gloss": gloss, "definition": definition, "attested": bool(attested)}
        )

    # The transmission chain: which Greek words the Septuagint used for a Hebrew
    # word, and which Hebrew words a Greek word stands for.
    to_greek, from_hebrew = {}, {}
    for lemma_id, greek_text, count in conn.execute(
        "SELECT t.lemma_id, e.greek_text, COUNT(*) c FROM lxx_equivalent e "
        "JOIN token t ON t.id = e.token_id WHERE t.lemma_id IS NOT NULL "
        "GROUP BY t.lemma_id, e.greek_text ORDER BY t.lemma_id, c DESC"
    ):
        to_greek.setdefault(lemma_id, []).append([greek_text, count])

    for greek_lemma_id, hebrew, xlit, count in conn.execute(
        "SELECT e.greek_lemma_id, l.lemma, l.transliteration, COUNT(*) c "
        "FROM lxx_equivalent e JOIN token t ON t.id = e.token_id "
        "JOIN lemma l ON l.id = t.lemma_id "
        "WHERE e.greek_lemma_id IS NOT NULL GROUP BY e.greek_lemma_id, l.id "
        "ORDER BY e.greek_lemma_id, c DESC"
    ):
        from_hebrew.setdefault(greek_lemma_id, []).append([hebrew, xlit, count])

    # Words worth comparing are the ones English collapses into the same word.
    # That collapse is the app's whole thesis, so it is also the best possible
    # basis for "set this against another word".
    same_english = {}
    for lemma_id, entries in renderings_by_lemma.items():
        english = entries.get("cherith-en") or entries.get("berean-interlinear") or []
        if english:
            key = english[0][0].strip().lower()
            if key and len(key) > 2:
                same_english.setdefault(key, []).append(lemma_id)

    neighbours = {}
    for key, ids in same_english.items():
        if len(ids) < 2:
            continue
        ranked = sorted(ids, key=lambda i: -counts.get(i, 0))
        for lemma_id in ids:
            neighbours[lemma_id] = [i for i in ranked if i != lemma_id][:4]

    lemma_slug_for, lemma_text, lemma_xlit = {}, {}, {}
    for lemma_id, lemma, xlit, strongs in conn.execute(
        "SELECT id, lemma, transliteration, strongs FROM lemma"
    ):
        lemma_slug_for[lemma_id] = strongs or f"L{lemma_id}"
        lemma_text[lemma_id] = lemma
        lemma_xlit[lemma_id] = xlit

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
            "gloss": (first_gloss(senses.get(lemma_id)) or "")[:120],
            # Every recorded meaning is searchable, not just the first. A reader
            # arriving with "propitiation" must reach the words behind it, and
            # that term appears in a later sense than the headline gloss.
            "terms": " ".join(
                x["gloss"] for group in senses.get(lemma_id, {}).values() for x in group
            )[:220],
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
            "senses": senses.get(lemma_id, {}),
            "by_genre": sorted(by_genre.get(lemma_id, {}).items(), key=lambda kv: -kv[1]),
            "earliest_written": earliest_written.get(lemma_id, {}),
            "hapax": count == 1,
            "compare_with": [
                {"slug": lemma_slug_for.get(other), "lemma": lemma_text.get(other),
                 "xlit": lemma_xlit.get(other), "n": counts.get(other, 0)}
                for other in neighbours.get(lemma_id, [])
                if lemma_slug_for.get(other)
            ],
            "to_greek": to_greek.get(lemma_id, [])[:12],
            "from_hebrew": from_hebrew.get(lemma_id, [])[:12],
            "renderings": {
                version: entries[:12]
                for version, entries in renderings_by_lemma.get(lemma_id, {}).items()
            },
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

    # Chapter files power the verse view -- the entry point for a reader who
    # arrives with a reference rather than a word. One file per chapter keeps the
    # request count sane; one file per verse would mean 31,000 of them.
    chapter_dir = out_dir / "chapter"
    if chapter_dir.exists():
        shutil.rmtree(chapter_dir)
    chapter_dir.mkdir()

    lemma_slug = {}
    for lemma_id, strongs in conn.execute("SELECT id, strongs FROM lemma"):
        lemma_slug[lemma_id] = strongs or f"L{lemma_id}"

    words_by_verse = {}
    for book, chapter, verse, position, surface, lemma_id, language in conn.execute(
        "SELECT b.name, v.chapter, v.verse, t.position, t.surface, t.lemma_id, l.language "
        "FROM token t JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "LEFT JOIN lemma l ON l.id = t.lemma_id "
        "WHERE v.versification = 'kjv' ORDER BY b.id, v.chapter, v.verse, t.position"
    ):
        words_by_verse.setdefault((book, chapter), {}).setdefault(verse, []).append(
            {"s": surface, "k": lemma_slug.get(lemma_id), "l": language}
        )

    # One English gloss per word, so the verse view can show what each original
    # word means without a second request.
    word_gloss = {}
    for version_id in ("cherith-en", "interlinear-en"):
        for book, chapter, verse, position, text in conn.execute(
            "SELECT b.name, v.chapter, v.verse, t.position, g.text FROM gloss g "
            "JOIN token t ON t.id = g.token_id JOIN verse v ON v.id = t.verse_id "
            "JOIN book b ON b.id = v.book_id WHERE g.version_id = ?", (version_id,)
        ):
            word_gloss[(book, chapter, verse, position)] = text

    text_by_chapter = {}
    for book, chapter, verse, version_id, text in conn.execute(
        "SELECT b.name, v.chapter, v.verse, r.version_id, r.text FROM rendering r "
        "JOIN verse v ON v.id = r.verse_id JOIN book b ON b.id = v.book_id"
    ):
        text_by_chapter.setdefault((book, chapter), {}).setdefault(verse, {})[version_id] = text

    chapters_written = 0
    for key in sorted(set(words_by_verse) | set(text_by_chapter)):
        book, chapter = key
        words = words_by_verse.get(key, {})
        texts = text_by_chapter.get(key, {})
        verses = []
        for number in sorted(set(words) | set(texts)):
            entries = words.get(number, [])
            for position, entry in enumerate(entries, start=1):
                gloss = word_gloss.get((book, chapter, number, position))
                if gloss and gloss.strip("*").strip():
                    entry["g"] = gloss
            verses.append({"v": number, "w": entries, "t": texts.get(number, {})})

        slug = f"{book}.{chapter}".replace(" ", "_")
        (chapter_dir / f"{slug}.json").write_text(
            json.dumps({"book": book, "chapter": chapter, "verses": verses},
                       ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        chapters_written += 1

    books = [
        {"name": name, "abbr": abbr, "chapters": chapters, "testament": testament,
         "genre": genre}
        for name, abbr, chapters, testament, genre in conn.execute(
            "SELECT name, abbr, chapters, testament, genre FROM book ORDER BY id"
        )
    ]
    (out_dir / "books.json").write_text(
        json.dumps({"books": books, "genres": dict(conn.execute(
            "SELECT DISTINCT genre, genre FROM book WHERE genre IS NOT NULL"))},
            ensure_ascii=False, separators=(",", ":")),
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
        "renderings": conn.execute("SELECT COUNT(*) FROM rendering").fetchone()[0],
        "versions": len(versions),
        "canons": {name: len(books) for name, books in canons.items()},
        "glosses": conn.execute("SELECT COUNT(*) FROM gloss").fetchone()[0],
        "septuagint_links": conn.execute("SELECT COUNT(*) FROM lxx_equivalent").fetchone()[0],
        "chapters": chapters_written,
    }
    (out_dir / "stats.json").write_text(json.dumps(stats), encoding="utf-8")

    for asset in WEB.iterdir():
        shutil.copy2(asset, out_dir / asset.name)

    # The reference parser is shared with the tests rather than duplicated.
    shutil.copy2(ROOT / "bible-study" / "js" / "books.js", out_dir / "books.js")

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
