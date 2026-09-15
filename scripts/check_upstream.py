#!/usr/bin/env python3
"""Re-fetch registered files and report what changed upstream.

`fetch_log` records a sha256 per retrieval, which is only useful if something
actually compares against it. This does: it re-downloads each registered file,
hashes it, and reports drift against the last successful fetch.

    python3 scripts/check_upstream.py            # every source
    python3 scripts/check_upstream.py --source macula-greek
"""

import argparse
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "data" / "sources" / "downloads.json"
DEFAULT_DB = ROOT / "data" / "studyhelp.db"
USER_AGENT = "StudyHelp/0.1 (upstream drift check)"


def last_hashes(conn):
    """The most recent successful sha256 per URL."""
    # max() in the SELECT list is the form SQLite guarantees will pick the
    # matching row's other columns; the same test in HAVING does not.
    return {
        url: sha
        for url, sha, _ in conn.execute(
            "SELECT url, sha256, MAX(fetched_at) FROM fetch_log "
            "WHERE ok = 1 AND sha256 IS NOT NULL GROUP BY url"
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--source", help="check only this source id")
    args = parser.parse_args()

    downloads = json.loads(DOWNLOADS.read_text(encoding="utf-8"))["downloads"]
    conn = sqlite3.connect(args.db)
    try:
        known = last_hashes(conn)
    finally:
        conn.close()

    unchanged = changed = unknown = failed = 0
    for entry in downloads:
        if args.source and entry["source_id"] != args.source:
            continue
        for spec in entry.get("files", []):
            url = spec["url"]
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=120) as response:
                    digest = hashlib.sha256(response.read()).hexdigest()
            except (urllib.error.URLError, OSError) as exc:
                print(f"FAILED   {url}: {exc}")
                failed += 1
                continue

            recorded = known.get(url)
            if recorded is None:
                print(f"NEW      {url}")
                unknown += 1
            elif recorded == digest:
                unchanged += 1
            else:
                print(f"CHANGED  {url}\n         recorded {recorded[:12]}  now {digest[:12]}")
                changed += 1

    print(f"\n{unchanged} unchanged, {changed} changed, {unknown} not previously fetched, "
          f"{failed} unreachable.")
    return 1 if changed or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
