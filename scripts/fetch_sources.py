#!/usr/bin/env python3
"""Fetch registered open-source datasets and record the provenance of each retrieval.

Every attempt -- successful or not -- writes a fetch_log row: the exact URL, the
timestamp, the byte count and the sha256 of what came back. That log is the
answer to "where did this claim actually come from", and re-fetching later makes
upstream changes visible instead of silent.

    python3 scripts/fetch_sources.py --list
    python3 scripts/fetch_sources.py --source openscriptures-strongs
    python3 scripts/fetch_sources.py --all

Downloaded corpora are NOT committed to the repo; they land in data/raw/, which
is gitignored. The registry and this script are what we version.
"""

import argparse
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "data" / "sources" / "downloads.json"
DEFAULT_DB = ROOT / "data" / "studyhelp.db"
RAW_DIR = ROOT / "data" / "raw"

USER_AGENT = "StudyHelp/0.1 (open-source Bible word study; dataset ingest)"


def load_downloads():
    with open(DOWNLOADS, encoding="utf-8") as fh:
        return json.load(fh)["downloads"]


def log_fetch(conn, **fields):
    columns = ", ".join(fields)
    placeholders = ", ".join("?" * len(fields))
    conn.execute(
        f"INSERT INTO fetch_log ({columns}) VALUES ({placeholders})",
        list(fields.values()),
    )
    conn.commit()


def fetch_one(conn, source_id, url, rel_path, force=False):
    dest = RAW_DIR / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    if dest.exists() and not force:
        print(f"  skip (exists): {rel_path}")
        return True

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            status = response.status
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        status = getattr(exc, "code", None)
        log_fetch(
            conn, source_id=source_id, url=url, fetched_at=now,
            http_status=status, local_path=str(dest.relative_to(ROOT)),
            ok=0, error=str(exc),
        )
        print(f"  FAIL {rel_path}: {exc}")
        return False

    dest.write_bytes(payload)
    log_fetch(
        conn, source_id=source_id, url=url, fetched_at=now, http_status=status,
        bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
        local_path=str(dest.relative_to(ROOT)), ok=1,
    )
    print(f"  ok {rel_path} ({len(payload)} bytes)")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--source", help="fetch only this source id")
    parser.add_argument("--all", action="store_true", help="fetch every registered download")
    parser.add_argument("--list", action="store_true", help="show what is registered and exit")
    parser.add_argument("--force", action="store_true", help="re-download files already present")
    args = parser.parse_args()

    downloads = load_downloads()

    if args.list:
        for entry in downloads:
            files = entry.get("files", [])
            print(f"{entry['source_id']}: {len(files)} file(s)")
            if entry.get("note"):
                print(f"    note: {entry['note']}")
        return

    if not args.source and not args.all:
        parser.error("pass --source <id>, --all, or --list")

    conn = sqlite3.connect(args.db)
    try:
        known = {r[0] for r in conn.execute("SELECT id FROM source")}
        if not known:
            parser.error("no sources in the database -- run scripts/init_db.py first")

        succeeded = failed = 0
        for entry in downloads:
            source_id = entry["source_id"]
            if args.source and source_id != args.source:
                continue
            if source_id not in known:
                print(f"{source_id}: not in the source registry, skipping")
                continue

            files = entry.get("files", [])
            print(f"{source_id}: {len(files)} file(s)")
            for spec in files:
                if fetch_one(conn, source_id, spec["url"], spec["path"], args.force):
                    succeeded += 1
                else:
                    failed += 1

        print(f"\nDone: {succeeded} ok, {failed} failed. Provenance recorded in fetch_log.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
