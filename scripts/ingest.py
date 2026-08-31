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

    def verse_id(self, book_id, chapter, verse, versification="kjv"):
        key = (book_id, chapter, verse, versification)
        if key in self.verse_cache:
            return self.verse_cache[key]
        cur = self.conn.execute(
            "INSERT INTO verse (book_id, chapter, verse, versification) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (book_id, chapter, verse, versification) DO NOTHING",
            key,
        )
        if cur.lastrowid and cur.rowcount:
            vid = cur.lastrowid
        else:
            vid = self.conn.execute(
                "SELECT id FROM verse WHERE book_id=? AND chapter=? AND verse=? AND versification=?",
                key,
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


    def ingest_translations(self):
        """Load English (and Latin) translations from the scrollmapper JSON packaging.

        version.source_id names the upstream EDITION, which is the authority for
        the text; rendering.source_id names the aggregator the bytes actually came
        from. Aggregators can silently alter text, so the two are kept distinct.
        """
        aggregator = "scrollmapper-bible-databases"
        editions = {
            "Wycliffe.json": ("wycliffe-1395", "wycliffe", "Wycliffe Bible", "en", 1395,
                              "middle_english", "Latin Vulgate"),
            "Tyndale.json": ("tyndale-1526", "tyndale", "Tyndale Bible", "en", 1526,
                             "early_modern", "Greek and Hebrew"),
            "KJV.json": ("kjv-1769", "kjv", "King James Version", "en", 1769,
                         "early_modern", "Textus Receptus and Masoretic Text"),
            "YLT.json": ("ylt-1898", "ylt", "Young's Literal Translation", "en", 1898,
                         "modern_early", "Textus Receptus and Masoretic Text"),
            "ASV.json": ("asv-1901", "asv", "American Standard Version", "en", 1901,
                         "modern_early", "Critical text and Masoretic Text"),
            "BSB.json": ("bsb", "bsb", "Berean Standard Bible", "en", 2023,
                         "contemporary", "Critical text and Masoretic Text"),
            "Vulgate.json": ("clementine-vulgate", "vulgate", "Clementine Vulgate", "la", 1592,
                             "early_modern", "Hebrew and Greek"),
            "AKJV.json": ("akjv", "akjv", "American King James Version", "en", 1999,
                          "contemporary", "Textus Receptus and Masoretic Text"),
            "NHEB.json": ("nheb", "nheb", "New Heart English Bible", "en", None,
                          "contemporary", "Critical text and Masoretic Text"),
        }

        books = {name: bid for bid, name in self.conn.execute("SELECT id, name FROM book")}
        # Packaged files use a few name spellings that differ from our canon.
        aliases = {
            "Psalm": "Psalms", "Song of Songs": "Song of Solomon",
            "Canticles": "Song of Solomon", "Revelation of John": "Revelation",
            "The Revelation": "Revelation", "Acts of the Apostles": "Acts",
        }
        # Numbered books are packaged with Roman numerals ("I Corinthians").
        romans = {"I": "1", "II": "2", "III": "3"}

        def canon_name(raw):
            name = aliases.get(raw, raw)
            head, _, tail = name.partition(" ")
            if head in romans and tail:
                name = f"{romans[head]} {tail}"
            return aliases.get(name, name)

        loaded = 0
        for filename, meta in editions.items():
            path = RAW / "translations" / filename
            if not path.exists():
                continue
            source_id, version_id, name, language, year, era, translated_from = meta

            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)

            self.conn.execute(
                "INSERT INTO version (id, source_id, name, language, year, era, translated_from) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, year=excluded.year, era=excluded.era, "
                "translated_from=excluded.translated_from",
                (version_id, source_id, name, language, year, era, translated_from),
            )

            rows = []
            skipped = set()
            for book in doc.get("books", []):
                book_id = books.get(canon_name(book["name"]))
                if book_id is None:
                    skipped.add(book["name"])
                    continue
                for chapter in book.get("chapters", []):
                    ch = chapter["chapter"]
                    for verse in chapter.get("verses", []):
                        vid = self.verse_id(book_id, ch, verse["verse"])
                        rows.append((vid, version_id, verse["text"].strip(), aggregator))

            self.conn.executemany(
                "INSERT INTO rendering (verse_id, version_id, text, source_id) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (verse_id, version_id) DO UPDATE SET "
                "text=excluded.text, source_id=excluded.source_id",
                rows,
            )
            loaded += len(rows)
            note = f", skipped {sorted(skipped)}" if skipped else ""
            print(f"  {version_id}: {len(rows)} verses{note}")

        print(f"  translations: {loaded} renderings")


    def ingest_lxx(self):
        """Load Swete's Septuagint as a Greek text layer.

        The LXX is the hinge of the transmission chain: it is the only witness to
        how Hebrew vocabulary was already being rendered into Greek before the New
        Testament was written.

        Two honest limits are encoded here rather than papered over:

        1. Swete's published files carry no lemma or morphology tagging, so this
           gives the LXX *text* but not lemma-level bridging. The tagged edition
           that would give us that (Rahlfs via CATSS/CCAT) is NonCommercial and
           gated behind a signed declaration, so it is not fetched at all.
        2. LXX versification genuinely differs from the Hebrew and English (the
           Psalms most visibly), so these verses are stored under their own
           `versification` value instead of being forced onto English numbering.
        """
        source_id = "lxx-swete-1930"
        version_id = "lxx-swete"

        vers_path = RAW / "lxx" / "00-Swete_versification.csv"
        words_path = RAW / "lxx" / "01-Swete_word_with_punctuations.csv"
        if not (vers_path.exists() and words_path.exists()):
            print("  missing Swete files -- run fetch_sources.py first")
            return

        # Swete's three-letter codes for the books that exist in our canon. The
        # deuterocanonical books it also carries (Judith, Tobit, Sirach, Wisdom,
        # Baruch, Maccabees) have no home in a 66-book canon and are skipped.
        codes = {
            "Gen": "Genesis", "Exo": "Exodus", "Lev": "Leviticus", "Num": "Numbers",
            "Deu": "Deuteronomy", "Jos": "Joshua", "Jdg": "Judges", "Rut": "Ruth",
            "1Sa": "1 Samuel", "2Sa": "2 Samuel", "1Ki": "1 Kings", "2Ki": "2 Kings",
            "1Ch": "1 Chronicles", "2Ch": "2 Chronicles", "Ezr": "Ezra", "Neh": "Nehemiah",
            "Est": "Esther", "Job": "Job", "Psa": "Psalms", "Pro": "Proverbs",
            "Ecc": "Ecclesiastes", "Sol": "Song of Solomon", "Isa": "Isaiah",
            "Jer": "Jeremiah", "Lam": "Lamentations", "Eze": "Ezekiel", "Dan": "Daniel",
            "Hos": "Hosea", "Joe": "Joel", "Amo": "Amos", "Oba": "Obadiah", "Jon": "Jonah",
            "Mic": "Micah", "Nah": "Nahum", "Hab": "Habakkuk", "Zep": "Zephaniah",
            "Hag": "Haggai", "Zec": "Zechariah", "Mal": "Malachi",
        }
        books = {name: bid for bid, name in self.conn.execute("SELECT id, name FROM book")}

        words = {}
        with open(words_path, encoding="utf-8") as fh:
            for line in fh:
                index, _, word = line.rstrip("\n").partition("\t")
                if index.isdigit():
                    words[int(index)] = word

        starts = []
        with open(vers_path, encoding="utf-8") as fh:
            for line in fh:
                index, _, ref = line.rstrip("\n").partition("\t")
                if index.isdigit() and ref:
                    starts.append((int(index), ref))
        starts.sort()

        self.conn.execute(
            "INSERT INTO version (id, source_id, name, language, year, era, translated_from) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name",
            (version_id, source_id, "Septuagint (Swete)", "grc", -200, "ancient", "Hebrew"),
        )

        last_index = max(words) if words else 0
        rows = []
        skipped = set()
        for position, (start, ref) in enumerate(starts):
            end = starts[position + 1][0] - 1 if position + 1 < len(starts) else last_index
            code, _, coords = ref.partition(".")
            name = codes.get(code)
            if not name:
                skipped.add(code)
                continue
            chapter_text, _, verse_text = coords.partition(":")
            if not (chapter_text.isdigit() and verse_text.isdigit()):
                continue

            text = " ".join(
                words[i] for i in range(start, end + 1) if i in words
            ).strip()
            if not text:
                continue

            vid = self.verse_id(books[name], int(chapter_text), int(verse_text),
                                versification="lxx")
            rows.append((vid, version_id, text, source_id))

        self.conn.executemany(
            "INSERT INTO rendering (verse_id, version_id, text, source_id) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (verse_id, version_id) DO UPDATE SET "
            "text=excluded.text",
            rows,
        )
        print(f"  lxx: {len(rows)} verses"
              f"{f', skipped {len(skipped)} non-canonical books' if skipped else ''}")


DATASETS = {
    "strongs": "ingest_strongs",
    "oshb": "ingest_oshb",
    "morphgnt": "ingest_morphgnt",
    "translations": "ingest_translations",
    "lxx": "ingest_lxx",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dataset", choices=sorted(DATASETS))
    parser.add_argument("--all", action="store_true", help="run every loader in order")
    args = parser.parse_args()

    if not args.dataset and not args.all:
        parser.error("pass --dataset <name> or --all")

    order = (["strongs", "oshb", "morphgnt", "translations", "lxx"]
             if args.all else [args.dataset])

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
