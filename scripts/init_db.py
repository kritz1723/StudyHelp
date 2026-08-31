#!/usr/bin/env python3
"""Create the StudyHelp database and load the source registry into it.

The registry in data/sources/sources.json is the source of truth; this script
mirrors it into the `source` table so that ingestion can reference sources by
foreign key. Safe to re-run: sources are upserted, nothing else is touched.

    python3 scripts/init_db.py [--db data/studyhelp.db]
"""

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
REGISTRY = ROOT / "data" / "sources" / "sources.json"
CANON = ROOT / "data" / "canon.json"
DATES = ROOT / "data" / "composition_dates.json"
DEFAULT_DB = ROOT / "data" / "studyhelp.db"

SOURCE_FIELDS = [
    "id", "name", "kind", "language", "year", "era", "description", "license",
    "attribution", "homepage", "repository", "formats", "tier", "priority",
    "verified", "notes",
]


def load_registry(path=REGISTRY):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["sources"]


def upsert_sources(conn, sources):
    rows = []
    for src in sources:
        row = []
        for field in SOURCE_FIELDS:
            value = src.get(field)
            if field == "formats" and value is not None:
                value = json.dumps(value)
            elif field == "tier" and value is not None:
                value = str(value)
            row.append(value)
        rows.append(row)

    placeholders = ", ".join("?" * len(SOURCE_FIELDS))
    columns = ", ".join(SOURCE_FIELDS)
    updates = ", ".join(f"{f}=excluded.{f}" for f in SOURCE_FIELDS if f != "id")
    conn.executemany(
        f"INSERT INTO source ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        rows,
    )
    return len(rows)


def upsert_canon(conn):
    with open(CANON, encoding="utf-8") as fh:
        books = json.load(fh)["books"]
    conn.executemany(
        "INSERT INTO book (id, name, abbr, chapters, testament) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, abbr=excluded.abbr, "
        "chapters=excluded.chapters, testament=excluded.testament",
        [(b["id"], b["name"], b["abbr"], b["chapters"], b["testament"]) for b in books],
    )
    return len(books)


def upsert_composition_dates(conn):
    """Load one date range per book per scholarly tradition.

    Several rows per book is the design: the spread between traditions is the
    honest answer to "when was this written", and a single value would adopt one
    school's position silently.
    """
    with open(DATES, encoding="utf-8") as fh:
        doc = json.load(fh)

    books = {name: bid for bid, name in conn.execute("SELECT id, name FROM book")}
    rows = []
    for entry in doc["books"]:
        book_id = books[entry["book"]]
        for tradition in doc["traditions"]:
            span = entry[tradition]
            rows.append((book_id, tradition, span["earliest"], span["latest"],
                         f"dating-{tradition}"))

    conn.executemany(
        "INSERT INTO composition_date (book_id, tradition, earliest, latest, source_id) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (book_id, tradition) DO UPDATE SET "
        "earliest=excluded.earliest, latest=excluded.latest, source_id=excluded.source_id",
        rows,
    )
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the SQLite database")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        count = upsert_sources(conn, load_registry())
        books = upsert_canon(conn)
        dates = upsert_composition_dates(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Initialised {db_path} with {count} sources, {books} books, {dates} date ranges.")


if __name__ == "__main__":
    main()
