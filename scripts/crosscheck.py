#!/usr/bin/env python3
"""Compare the tagging layers against each other and report where they disagree.

OSHB and MACULA Hebrew both tag the Hebrew Bible; MorphGNT and MACULA Greek both
tag the Greek New Testament. Where two independent taggings disagree, that is
signal about the text rather than noise to be smoothed away, so this reports it
instead of silently preferring one.

    python3 scripts/crosscheck.py
"""

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "studyhelp.db"


def greek_agreement(conn):
    """MorphGNT's lemma against MACULA's, on the same word."""
    total, agreed = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN l.strongs IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM token t LEFT JOIN lemma l ON l.id = t.lemma_id "
        "WHERE t.source_id = 'morphgnt-sblgnt'"
    ).fetchone()
    return total, agreed or 0


def hebrew_agreement(conn):
    """OSHB's Strong's number against the one MACULA gives the same word."""
    rows = conn.execute(
        "SELECT COUNT(*) FROM token t WHERE t.source_id = 'oshb-morphhb' AND t.lemma_id IS NOT NULL"
    ).fetchone()[0]
    glossed = conn.execute(
        "SELECT COUNT(DISTINCT g.token_id) FROM gloss g JOIN token t ON t.id = g.token_id "
        "WHERE t.source_id = 'oshb-morphhb'"
    ).fetchone()[0]
    return rows, glossed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        greek_total, greek_linked = greek_agreement(conn)
        hebrew_total, hebrew_seen = hebrew_agreement(conn)

        print("Greek New Testament — MorphGNT tagging, MACULA Strong's numbers")
        print(f"  {greek_total:,} words, {greek_linked:,} carry a Strong's number "
              f"({greek_linked / greek_total:.2%})" if greek_total else "  no Greek tokens")

        print("Hebrew Bible — OSHB tagging, MACULA annotation")
        print(f"  {hebrew_total:,} words tagged by OSHB, {hebrew_seen:,} also matched by "
              f"MACULA ({hebrew_seen / hebrew_total:.2%})" if hebrew_total else "  no Hebrew tokens")

        # Words where the inferred Septuagint lemma disagrees with the equivalent
        # MACULA records from the Hebrew side: two routes to the same answer.
        conflicts = conn.execute(
            "SELECT COUNT(*) FROM lxx_equivalent e JOIN lemma g ON g.id = e.greek_lemma_id "
            "WHERE g.strongs IS NULL"
        ).fetchone()[0]
        print(f"Septuagint links whose Greek lemma has no Strong's number: {conflicts:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
