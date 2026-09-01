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
import csv
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


def word_key(text):
    """Comparison key for matching the same word across editions.

    MorphGNT keeps punctuation attached to the word ("Ἀβραάμ."), MACULA strips it
    ("Ἀβραάμ"), so a literal comparison rejects most real matches. Folding away
    everything that is not a letter, on top of the diacritic fold, compares the
    word itself.
    """
    folded = normalize_greek(text)
    return "".join(c for c in folded if c.isalpha())


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
        # Senses have no natural key to conflict on, so a re-run replaces this
        # source's rows rather than stacking a second copy of every definition.
        self.conn.execute("DELETE FROM sense WHERE source_id = ?", (source_id,))
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
            # Deuterocanonical books, carried by Wycliffe and the Vulgate.
            "Prayer of Manasses": "Prayer of Manasseh",
            "Additional Psalm": "Psalm 151",
            "Ecclesiasticus": "Sirach",
            "Wisdom of Solomon": "Wisdom",
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

        # Swete's three-letter codes. What is deliberately NOT mapped: alternate
        # textual traditions of books already loaded (Dat, Bet, Sut, Tbs), which
        # would double-count, and texts outside all three canons StudyHelp knows
        # (Odes, Psalms of Solomon, 1 Enoch).
        codes = {
            # Deuterocanonical books the Septuagint carries.
            "Tob": "Tobit", "Jdt": "Judith", "Wis": "Wisdom", "Sir": "Sirach",
            "Bar": "Baruch", "1Ma": "1 Maccabees", "2Ma": "2 Maccabees",
            "3Ma": "3 Maccabees", "4Ma": "4 Maccabees", "1Es": "1 Esdras",
            "Sus": "Susanna", "Bel": "Bel and the Dragon",
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


    def ingest_macula(self):
        """Enrich the Greek New Testament with MACULA's word-level annotation.

        Two things this fixes:

        1. MorphGNT carries no Strong's numbers, so Greek tokens were linked to
           lexicon entries by folding diacritics off the lemma -- a heuristic that
           reached 98.5%. MACULA carries an explicit Strong's number for every
           word, so the guesswork is replaced with the real tag.
        2. The gloss table was empty. MACULA supplies per-word English and
           Mandarin glosses, which is what a translation-drift view is built on,
           and the Mandarin is this project's first non-European-language data.

        Rows are applied only where the word actually matches the token already
        loaded, so a versification or word-order difference between editions
        cannot silently overwrite the wrong word.
        """
        source_id = "macula-greek"
        path = RAW / "macula" / "macula-greek-SBLGNT.tsv"
        if not path.exists():
            print("  missing MACULA file -- run fetch_sources.py first")
            return

        codes = {
            "MAT": 40, "MRK": 41, "LUK": 42, "JHN": 43, "ACT": 44, "ROM": 45,
            "1CO": 46, "2CO": 47, "GAL": 48, "EPH": 49, "PHP": 50, "COL": 51,
            "1TH": 52, "2TH": 53, "1TI": 54, "2TI": 55, "TIT": 56, "PHM": 57,
            "HEB": 58, "JAS": 59, "1PE": 60, "2PE": 61, "1JN": 62, "2JN": 63,
            "3JN": 64, "JUD": 65, "REV": 66,
        }

        # The gloss columns come from three different works, so they are recorded
        # as three sources rather than merged into one anonymous "English".
        gloss_versions = [
            ("gloss", "berean-interlinear", "berean-interlinear",
             "Berean Interlinear Bible", "en"),
            ("english", "cherith-en", "cherith-glosses",
             "Cherith Glosses (English)", "en"),
            ("mandarin", "cherith-zh", "cherith-glosses",
             "Cherith Glosses (Mandarin)", "zh"),
        ]
        for _, version_id, gloss_source, name, language in gloss_versions:
            self.conn.execute(
                "INSERT INTO version (id, source_id, name, language, year, era, translated_from) "
                "VALUES (?, ?, ?, ?, 2023, 'contemporary', 'Greek') "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                (version_id, gloss_source, name, language),
            )

        tokens = {}
        for token_id, book_id, chapter, verse, position, surface in self.conn.execute(
            "SELECT t.id, v.book_id, v.chapter, v.verse, t.position, t.surface FROM token t "
            "JOIN verse v ON v.id = t.verse_id WHERE t.source_id = 'morphgnt-sblgnt'"
        ):
            tokens[(book_id, chapter, verse, position)] = (token_id, surface)

        greek_lemma = {}
        for lemma_id, strongs in self.conn.execute(
            "SELECT id, strongs FROM lemma WHERE language='grc' AND strongs IS NOT NULL"
        ):
            greek_lemma[strongs] = lemma_id

        matched = missed = relinked = 0
        gloss_rows = []
        with open(path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                ref = row.get("ref") or ""
                head, _, index = ref.partition("!")
                code, _, coords = head.partition(" ")
                chapter_text, _, verse_text = coords.partition(":")
                book_id = codes.get(code)
                if not (book_id and index.isdigit()
                        and chapter_text.isdigit() and verse_text.isdigit()):
                    continue

                key = (book_id, int(chapter_text), int(verse_text), int(index))
                entry = tokens.get(key)
                if not entry:
                    missed += 1
                    continue

                token_id, surface = entry
                # Guard: only trust the row if it describes the same word.
                if word_key(surface) != word_key(row.get("text") or ""):
                    missed += 1
                    continue
                matched += 1

                strongs = (row.get("strong") or "").strip()
                if strongs.isdigit():
                    key_strongs = f"G{int(strongs)}"
                    lemma_id = greek_lemma.get(key_strongs)
                    if lemma_id is None:
                        lemma_id = self.lemma_id(
                            row.get("lemma") or key_strongs, "grc", key_strongs, source_id
                        )
                        greek_lemma[key_strongs] = lemma_id
                    self.conn.execute(
                        "UPDATE token SET lemma_id = ? WHERE id = ?", (lemma_id, token_id)
                    )
                    relinked += 1

                for column, version_id, gloss_source, _, _ in gloss_versions:
                    text = (row.get(column) or "").strip()
                    if text:
                        gloss_rows.append((token_id, version_id, text, gloss_source))

        self.conn.executemany(
            "INSERT INTO gloss (token_id, version_id, text, source_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (token_id, version_id) DO UPDATE SET text=excluded.text",
            gloss_rows,
        )

        total = matched + missed
        rate = (matched / total * 100) if total else 0
        print(f"  macula: {matched} words matched ({rate:.1f}%), {relinked} tokens "
              f"re-linked by explicit Strong's, {len(gloss_rows)} glosses")


    def ingest_macula_hebrew(self):
        """Annotate the Hebrew Bible, and record how the Septuagint rendered it.

        The Septuagint equivalent per Hebrew word is the important part. It
        supplies the Hebrew-to-Greek link the transmission chain needs, without
        the tagged Septuagint edition that licensing puts out of reach.

        MACULA counts morphemes where OSHB counts words, so a Hebrew word with
        prefixes appears here as several rows sharing one word index. They are
        grouped back into the word, and the LAST segment is treated as the head:
        Hebrew prefixes precede the stem, so the final segment carries the sense,
        which is also how the OSHB lemma was read.
        """
        source_id = "macula-hebrew"
        path = RAW / "macula" / "macula-hebrew.tsv"
        if not path.exists():
            print("  missing MACULA Hebrew file -- run fetch_sources.py first")
            return

        codes = {
            "GEN": 1, "EXO": 2, "LEV": 3, "NUM": 4, "DEU": 5, "JOS": 6, "JDG": 7,
            "RUT": 8, "1SA": 9, "2SA": 10, "1KI": 11, "2KI": 12, "1CH": 13,
            "2CH": 14, "EZR": 15, "NEH": 16, "EST": 17, "JOB": 18, "PSA": 19,
            "PRO": 20, "ECC": 21, "SNG": 22, "ISA": 23, "JER": 24, "LAM": 25,
            "EZK": 26, "DAN": 27, "HOS": 28, "JOL": 29, "AMO": 30, "OBA": 31,
            "JON": 32, "MIC": 33, "NAM": 34, "HAB": 35, "ZEP": 36, "HAG": 37,
            "ZEC": 38, "MAL": 39,
        }

        for version_id, gloss_source, name, language in (
            ("cherith-en", "cherith-glosses", "Cherith Glosses (English)", "en"),
            ("cherith-zh", "cherith-glosses", "Cherith Glosses (Mandarin)", "zh"),
        ):
            self.conn.execute(
                "INSERT INTO version (id, source_id, name, language, year, era, translated_from) "
                "VALUES (?, ?, ?, ?, 2023, 'contemporary', 'Hebrew and Greek') "
                "ON CONFLICT(id) DO NOTHING",
                (version_id, gloss_source, name, language),
            )

        tokens = {}
        for token_id, book_id, chapter, verse, position in self.conn.execute(
            "SELECT t.id, v.book_id, v.chapter, v.verse, t.position FROM token t "
            "JOIN verse v ON v.id = t.verse_id WHERE t.source_id = 'oshb-morphhb'"
        ):
            tokens[(book_id, chapter, verse, position)] = token_id

        greek_lemma = {
            strongs: lemma_id
            for lemma_id, strongs in self.conn.execute(
                "SELECT id, strongs FROM lemma WHERE language='grc' AND strongs IS NOT NULL"
            )
        }

        groups = {}
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                head, _, index = (row.get("ref") or "").partition("!")
                code, _, coords = head.partition(" ")
                chapter_text, _, verse_text = coords.partition(":")
                book_id = codes.get(code)
                if not (book_id and index.isdigit()
                        and chapter_text.isdigit() and verse_text.isdigit()):
                    continue
                key = (book_id, int(chapter_text), int(verse_text), int(index))
                groups.setdefault(key, []).append(row)

        matched = bridged = 0
        gloss_rows = []
        bridge_rows = []
        for key, rows in groups.items():
            token_id = tokens.get(key)
            if token_id is None:
                continue
            matched += 1
            head_row = rows[-1]

            for column, version_id in (("english", "cherith-en"), ("mandarin", "cherith-zh")):
                text = " ".join(r[column].strip() for r in rows if r.get(column)).strip()
                if text:
                    gloss_rows.append((token_id, version_id, text, "cherith-glosses"))

            greek_text = (head_row.get("greek") or "").strip()
            # MACULA marks "no Greek equivalent here" with punctuation placeholders
            # (’’, ^^^, ‐‐+). Storing those as Greek words would invent equivalents
            # that the Septuagint does not contain.
            if greek_text and any(ch.isalpha() for ch in greek_text):
                greek_strong = (head_row.get("greekstrong") or "").strip()
                lemma_id = None
                if greek_strong.isdigit():
                    lemma_id = greek_lemma.get(f"G{int(greek_strong)}")
                bridge_rows.append((token_id, greek_text, lemma_id, source_id))
                bridged += 1

        self.conn.executemany(
            "INSERT INTO gloss (token_id, version_id, text, source_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (token_id, version_id) DO UPDATE SET text=excluded.text",
            gloss_rows,
        )
        self.conn.executemany(
            "INSERT INTO lxx_equivalent (token_id, greek_text, greek_lemma_id, source_id) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (token_id) DO UPDATE SET "
            "greek_text=excluded.greek_text, greek_lemma_id=excluded.greek_lemma_id",
            bridge_rows,
        )

        total = len(groups)
        rate = (matched / total * 100) if total else 0
        print(f"  macula-hebrew: {matched} words matched ({rate:.1f}%), "
              f"{len(gloss_rows)} glosses, {bridged} Septuagint equivalents")


    def ingest_bdb(self):
        """Load Brown-Driver-Briggs as a second Hebrew sense authority.

        Until now every Hebrew meaning came from Strong's alone, so the app could
        not do the one thing it exists for: show that authorities disagree. BDB is
        public domain and independent, and its definitions are keyed to Strong's
        numbers through the Open Scriptures lexical index.

        This is the open route to a second opinion. The semantic-domain data
        inside MACULA (Louw-Nida via UBS MARBLE for Greek, and the Semantic
        Dictionary of Biblical Hebrew) would serve the same purpose, but both are
        marked "used with permission" rather than openly licensed, so they are
        deliberately not ingested.
        """
        source_id = "openscriptures-hebrewlexicon"
        index_path = RAW / "hebrewlexicon" / "LexicalIndex.xml"
        bdb_path = RAW / "hebrewlexicon" / "BrownDriverBriggs.xml"
        if not index_path.exists():
            print("  missing lexicon files -- run fetch_sources.py first")
            return

        def text_of(element):
            return " ".join("".join(element.itertext()).split())

        # These files are namespaced; iterating on bare tag names finds nothing.
        def tag(root, name):
            namespace = root.tag.split("}")[0][1:] if "}" in root.tag else ""
            return f"{{{namespace}}}{name}" if namespace else name

        # Fuller definitions from the BDB entries themselves, keyed by BDB id.
        bdb_defs = {}
        if bdb_path.exists():
            bdb_tree = ET.parse(bdb_path)
            bdb_root = bdb_tree.getroot()
            for entry in bdb_tree.iter(tag(bdb_root, "entry")):
                entry_id = entry.get("id")
                if not entry_id:
                    continue
                defs = [text_of(d) for d in entry.iter(tag(bdb_root, "def"))]
                defs = [d for d in defs if d]
                if defs:
                    bdb_defs[entry_id] = "; ".join(dict.fromkeys(defs))[:400]

        lemmas = {
            strongs: lemma_id
            for lemma_id, strongs in self.conn.execute(
                "SELECT id, strongs FROM lemma WHERE language='hbo' AND strongs IS NOT NULL"
            )
        }

        self.conn.execute("DELETE FROM sense WHERE source_id = ?", (source_id,))

        rows = []
        index_tree = ET.parse(index_path)
        index_root = index_tree.getroot()
        for entry in index_tree.iter(tag(index_root, "entry")):
            xref = entry.find(tag(index_root, "xref"))
            if xref is None:
                continue
            strongs = xref.get("strong")
            if not (strongs and strongs.isdigit()):
                continue
            lemma_id = lemmas.get(f"H{int(strongs)}")
            if lemma_id is None:
                continue

            definition = entry.find(tag(index_root, "def"))
            gloss = text_of(definition) if definition is not None else ""
            fuller = bdb_defs.get(xref.get("bdb") or "")
            if not gloss and fuller:
                gloss = fuller.split(";")[0]
            if not gloss:
                continue
            rows.append((lemma_id, gloss[:200], fuller, source_id))

        self.conn.executemany(
            "INSERT INTO sense (lemma_id, gloss, definition, source_id, attested, ordering) "
            "VALUES (?, ?, ?, ?, 1, 0)",
            rows,
        )
        print(f"  bdb: {len(rows)} senses from Brown-Driver-Briggs")


DATASETS = {
    "strongs": "ingest_strongs",
    "oshb": "ingest_oshb",
    "morphgnt": "ingest_morphgnt",
    "translations": "ingest_translations",
    "lxx": "ingest_lxx",
    "macula": "ingest_macula",
    "macula-hebrew": "ingest_macula_hebrew",
    "bdb": "ingest_bdb",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dataset", choices=sorted(DATASETS))
    parser.add_argument("--all", action="store_true", help="run every loader in order")
    args = parser.parse_args()

    if not args.dataset and not args.all:
        parser.error("pass --dataset <name> or --all")

    order = (["strongs", "bdb", "oshb", "morphgnt", "macula", "macula-hebrew",
              "translations", "lxx"] if args.all else [args.dataset])

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
