#!/usr/bin/env python3
"""Load fetched datasets into the StudyHelp database.

    python3 scripts/ingest.py --dataset strongs
    python3 scripts/ingest.py --dataset oshb
    python3 scripts/ingest.py --dataset morphgnt
    python3 scripts/ingest.py --all

Order matters: `strongs` first, because it establishes the lemma rows that the
tagged-text loaders link their tokens to.

Every row written carries the source_id of the dataset it came from, so a claim
displayed later can be traced back through `source` to a licence and a fetch_log
entry recording the exact bytes it was parsed from.
"""

import argparse
import json
import re
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DEFAULT_DB = ROOT / "data" / "studyhelp.db"

OSIS_NS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"

# MorphGNT ships one file per NT book, numbered 61-87 in canonical order.
# Matthew is book 40 in our canon, so canon_id = 39 + (file_number - 60).
MORPHGNT_FIRST_FILE = 61
MORPHGNT_FIRST_CANON_ID = 40


def normalize_greek(text):
    """Fold a Greek word to a comparison key: no diacritics, lowercase, no final-sigma split.

    MorphGNT gives lemmas with accents; Strong's gives them with a different
    accentuation convention. Comparing the folded forms is what lets NT tokens
    link to Strong's entries at all.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower().replace("ς", "σ").strip()


def strongs_json(path):
    """Extract the JSON object embedded in an openscriptures strongs-*.js file."""
    text = path.read_text(encoding="utf-8")
    start = text.index("{", text.index("="))
    end = text.rindex("}", 0, text.rindex("module.exports"))
    return json.loads(text[start:end + 1])


class Ingestor:
    def __init__(self, conn):
        self.conn = conn
        self.verse_cache = {}
        self.book_by_abbr = {
            abbr: bid for bid, abbr in conn.execute("SELECT id, abbr FROM book")
        }

    # -- shared helpers ----------------------------------------------------

    def verse_id(self, book_id, chapter, verse):
        key = (book_id, chapter, verse)
        if key in self.verse_cache:
            return self.verse_cache[key]
        cur = self.conn.execute(
            "INSERT INTO verse (book_id, chapter, verse) VALUES (?, ?, ?) "
            "ON CONFLICT (book_id, chapter, verse, versification) DO NOTHING",
            key,
        )
        if cur.lastrowid and cur.rowcount:
            vid = cur.lastrowid
        else:
            vid = self.conn.execute(
                "SELECT id FROM verse WHERE book_id=? AND chapter=? AND verse=?", key
            ).fetchone()[0]
        self.verse_cache[key] = vid
        return vid

    def lemma_id(self, lemma, language, strongs, source_id):
        row = self.conn.execute(
            "SELECT id FROM lemma WHERE lemma=? AND language=? AND strongs IS ?",
            (lemma, language, strongs),
        ).fetchone()
        if row:
            return row[0]
        return self.conn.execute(
            "INSERT INTO lemma (lemma, language, strongs, source_id) VALUES (?, ?, ?, ?)",
            (lemma, language, strongs, source_id),
        ).lastrowid

    # -- datasets ----------------------------------------------------------

    def ingest_strongs(self):
        """Load Strong's Hebrew and Greek dictionaries as lemma + sense rows."""
        source_id = "openscriptures-strongs"
        lemmas = senses = 0

        for filename, language in (
            ("strongs-hebrew-dictionary.js", "hbo"),
            ("strongs-greek-dictionary.js", "grc"),
        ):
            path = RAW / "strongs" / filename
            if not path.exists():
                print(f"  missing {path.relative_to(ROOT)} -- run fetch_sources.py first")
                continue

            for strongs, entry in strongs_json(path).items():
                word = entry.get("lemma") or strongs
                # The Hebrew file spells the field "xlit", the Greek one "translit".
                xlit = entry.get("xlit") or entry.get("translit")
                lid = self.lemma_id(word, language, strongs, source_id)
                self.conn.execute(
                    "UPDATE lemma SET transliteration=? WHERE id=? AND transliteration IS NULL",
                    (xlit, lid),
                )
                lemmas += 1

                # Strong's own definition and its KJV rendering range are two
                # different kinds of claim, so they are stored as separate senses.
                for ordering, field in enumerate(("strongs_def", "kjv_def")):
                    gloss = (entry.get(field) or "").strip()
                    if not gloss:
                        continue
                    self.conn.execute(
                        "INSERT INTO sense (lemma_id, gloss, definition, source_id, attested, ordering) "
                        "VALUES (?, ?, ?, ?, 1, ?)",
                        (lid, gloss[:200], entry.get("derivation"), source_id, ordering),
                    )
                    senses += 1

        print(f"  strongs: {lemmas} lemmas, {senses} senses")

    def ingest_oshb(self):
        """Load the Hebrew Bible with morphology from OSIS XML (one file per book)."""
        source_id = "oshb-morphhb"
        tokens = 0

        # Strong's numbers in OSHB lemma attributes may carry prefix segments
        # ("b/7225") and homonym letters ("1254 a"). The final segment is the word.
        for path in sorted((RAW / "oshb").glob("*.xml")):
            book_id = self.book_by_abbr.get(path.stem)
            if book_id is None:
                print(f"  skip {path.name}: no canon book for abbr {path.stem!r}")
                continue

            tree = ET.parse(path)
            for verse_el in tree.iter(f"{OSIS_NS}verse"):
                osis_id = verse_el.get("osisID")
                if not osis_id:
                    continue
                parts = osis_id.split(".")
                if len(parts) != 3:
                    continue
                vid = self.verse_id(book_id, int(parts[1]), int(parts[2]))

                for position, w in enumerate(verse_el.iter(f"{OSIS_NS}w"), start=1):
                    surface = (w.text or "").strip()
                    if not surface:
                        continue
                    raw_lemma = (w.get("lemma") or "").strip()
                    final = raw_lemma.split("/")[-1].strip()
                    digits = re.match(r"(\d+)", final)
                    strongs = f"H{int(digits.group(1))}" if digits else None
                    morph = w.get("morph")

                    lid = None
                    if strongs:
                        row = self.conn.execute(
                            "SELECT id FROM lemma WHERE strongs=? AND language='hbo'", (strongs,)
                        ).fetchone()
                        lid = row[0] if row else self.lemma_id(final, "hbo", strongs, source_id)

                    self.conn.execute(
                        "INSERT INTO token (verse_id, position, surface, lemma_id, morphology, source_id) "
                        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        (vid, position, surface, lid, morph, source_id),
                    )
                    tokens += 1

        print(f"  oshb: {tokens} tokens")

    def ingest_morphgnt(self):
        """Load the Greek NT with morphology from MorphGNT's space-delimited files.

        Columns: bcv, part-of-speech, parsing code, text, word, normalised, lemma.
        MorphGNT carries no Strong's numbers, so lemmas are matched to Strong's
        Greek entries on a diacritic-folded key; unmatched lemmas are still
        recorded, with strongs left NULL rather than guessed.
        """
        source_id = "morphgnt-sblgnt"
        tokens = 0
        matched = 0

        greek_by_key = {}
        for lid, word in self.conn.execute(
            "SELECT id, lemma FROM lemma WHERE language='grc' AND strongs IS NOT NULL"
        ):
            greek_by_key.setdefault(normalize_greek(word), lid)

        unmatched_cache = {}

        for path in sorted((RAW / "morphgnt").glob("*-morphgnt.txt")):
            file_number = int(path.name.split("-")[0])
            book_id = MORPHGNT_FIRST_CANON_ID + (file_number - MORPHGNT_FIRST_FILE)

            position = 0
            current = None
            for line in path.read_text(encoding="utf-8").splitlines():
                fields = line.split()
                if len(fields) < 7:
                    continue
                bcv, _pos_tag, parsing, _text, _word, _norm, lemma = fields[:7]
                chapter, verse = int(bcv[2:4]), int(bcv[4:6])

                if (chapter, verse) != current:
                    current, position = (chapter, verse), 0
                position += 1
                vid = self.verse_id(book_id, chapter, verse)

                key = normalize_greek(lemma)
                lid = greek_by_key.get(key)
                if lid is not None:
                    matched += 1
                elif key in unmatched_cache:
                    lid = unmatched_cache[key]
                else:
                    lid = self.lemma_id(lemma, "grc", None, source_id)
                    unmatched_cache[key] = lid

                self.conn.execute(
                    "INSERT INTO token (verse_id, position, surface, lemma_id, morphology, source_id) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (vid, position, _text, lid, parsing, source_id),
                )
                tokens += 1

        rate = (matched / tokens * 100) if tokens else 0
        print(f"  morphgnt: {tokens} tokens, {matched} linked to Strong's ({rate:.1f}%)")


DATASETS = {
    "strongs": "ingest_strongs",
    "oshb": "ingest_oshb",
    "morphgnt": "ingest_morphgnt",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dataset", choices=sorted(DATASETS))
    parser.add_argument("--all", action="store_true", help="run every loader in order")
    args = parser.parse_args()

    if not args.dataset and not args.all:
        parser.error("pass --dataset <name> or --all")

    order = ["strongs", "oshb", "morphgnt"] if args.all else [args.dataset]

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ingestor = Ingestor(conn)
        for name in order:
            print(f"{name}:")
            getattr(ingestor, DATASETS[name])()
            conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
