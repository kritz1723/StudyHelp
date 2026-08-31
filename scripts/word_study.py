#!/usr/bin/env python3
"""Query the word-study database from the command line.

    python3 scripts/word_study.py H430
    python3 scripts/word_study.py --search agape
    python3 scripts/word_study.py G26 --usage

Answers the four questions the app exists to answer -- where the word first
appears, everywhere else it is used, what it meant, and who says so -- with the
source named for every claim.
"""

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "studyhelp.db"


def resolve(conn, term):
    """Find candidate lemmas for a Strong's number, an original-language word or a transliteration."""
    rows = conn.execute(
        "SELECT id, lemma, transliteration, strongs, language FROM lemma "
        "WHERE strongs = ? COLLATE NOCASE OR lemma = ? "
        "   OR transliteration = ? COLLATE NOCASE "
        "ORDER BY CASE WHEN strongs IS NULL THEN 1 ELSE 0 END, id",
        (term, term, term),
    ).fetchall()
    if rows:
        return rows
    return conn.execute(
        "SELECT id, lemma, transliteration, strongs, language FROM lemma "
        "WHERE transliteration LIKE ? COLLATE NOCASE ORDER BY id LIMIT 25",
        (f"%{term}%",),
    ).fetchall()


def report(conn, lemma_row, show_usage=False, limit=15):
    lid, lemma, xlit, strongs, language = lemma_row

    total = conn.execute("SELECT COUNT(*) FROM token WHERE lemma_id=?", (lid,)).fetchone()[0]
    print(f"\n{lemma}  ({xlit or '?'})   {strongs or 'no Strong’s number'}   [{language}]")
    print(f"{total} occurrence(s) in the tagged text")

    if not total:
        print("  No tagged occurrences -- the lemma is known to a lexicon but unlinked in the corpus.")

    # Origin: first appearance in canonical order. Composition order is a
    # separate, contested question -- see BACKLOG.md.
    first = conn.execute(
        "SELECT b.name, v.chapter, v.verse, t.surface, t.source_id FROM token t "
        "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "WHERE t.lemma_id = ? ORDER BY b.id, v.chapter, v.verse, t.position LIMIT 1",
        (lid,),
    ).fetchone()
    if first:
        print(f"\nFirst appearance (canonical order)")
        print(f"  {first[0]} {first[1]}:{first[2]}   {first[3]}      [source: {first[4]}]")

    dist = conn.execute(
        "SELECT b.name, COUNT(*) c FROM token t "
        "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
        "WHERE t.lemma_id = ? GROUP BY b.id ORDER BY c DESC, b.id LIMIT ?",
        (lid, limit),
    ).fetchall()
    if dist:
        print(f"\nWhere it clusters")
        width = max(len(b) for b, _ in dist)
        peak = dist[0][1]
        for book, count in dist:
            bar = "#" * max(1, round(count / peak * 28))
            print(f"  {book:<{width}}  {count:>4}  {bar}")

    senses = conn.execute(
        "SELECT s.gloss, s.source_id, s.attested, src.name FROM sense s "
        "JOIN source src ON src.id = s.source_id "
        "WHERE s.lemma_id = ? ORDER BY s.ordering, s.id",
        (lid,),
    ).fetchall()
    if senses:
        print(f"\nAttested meanings")
        for gloss, source_id, attested, source_name in senses:
            mark = "" if attested else "  (inferred, not attested)"
            print(f"  - {gloss}{mark}")
            print(f"      source: {source_name} [{source_id}]")

    if show_usage:
        print(f"\nOccurrences")
        for book, ch, vs, surface in conn.execute(
            "SELECT b.name, v.chapter, v.verse, t.surface FROM token t "
            "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
            "WHERE t.lemma_id = ? ORDER BY b.id, v.chapter, v.verse, t.position",
            (lid,),
        ):
            print(f"  {book} {ch}:{vs}   {surface}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("term", nargs="?", help="Strong's number, original-language word, or transliteration")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--search", help="find lemmas whose transliteration contains this text")
    parser.add_argument("--usage", action="store_true", help="list every occurrence")
    args = parser.parse_args()

    term = args.search or args.term
    if not term:
        parser.error("give a term to look up, or use --search")

    conn = sqlite3.connect(args.db)
    try:
        matches = resolve(conn, term)
        if not matches:
            print(f"No lemma matches {term!r}.")
            return

        # An English or transliterated search legitimately lands on several
        # lemmas. Showing the choice is the point -- collapsing it would put us
        # back to studying English surface forms.
        if len(matches) > 1 and not args.search:
            matches = matches[:1] if matches[0][3] else matches

        if len(matches) > 1:
            print(f"{len(matches)} lemmas match {term!r}:")
            for lid, lemma, xlit, strongs, language in matches:
                count = conn.execute("SELECT COUNT(*) FROM token WHERE lemma_id=?", (lid,)).fetchone()[0]
                print(f"  {strongs or '-':<8} {lemma:<20} {xlit or '':<18} {count:>5} occurrences  [{language}]")
            print("\nRe-run with a Strong's number for the full study.")
            return

        report(conn, matches[0], show_usage=args.usage)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
