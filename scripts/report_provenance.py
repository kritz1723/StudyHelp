#!/usr/bin/env python3
"""Summarise what was fetched, for the CI log.

A script rather than inline YAML, for the same reason the stats reporter is one:
inline workflow scripting cannot be tested, and the one place it existed is the
one place a deploy broke.

    python3 scripts/report_provenance.py [--db data/studyhelp.db]
"""

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "studyhelp.db"


def summarise(conn):
    ok, failed = conn.execute(
        "SELECT COALESCE(SUM(ok), 0), COALESCE(SUM(1 - ok), 0) FROM fetch_log"
    ).fetchone()
    lines = [f"fetch_log: {ok} ok, {failed} failed"]
    for source_id, url, status, error in conn.execute(
        "SELECT source_id, url, http_status, error FROM fetch_log WHERE ok = 0"
    ):
        lines.append(f"  FAILED {source_id} {url} {status} {error}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        for line in summarise(conn):
            print(line)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
