#!/usr/bin/env python3
"""Tests for canon integrity, the source registry, and the ingestion helpers.

Tests that need fetched corpora skip when data/raw is absent, so the suite runs
on a clean checkout (and in CI) without a 47 MB download.

    python3 -m unittest discover tests -v
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ingest  # noqa: E402
import init_db  # noqa: E402
import report_stats  # noqa: E402

RAW = ROOT / "data" / "raw"


class CanonTests(unittest.TestCase):
    def setUp(self):
        doc = json.loads((ROOT / "data" / "canon.json").read_text())
        self.books = doc["books"]
        self.canons = doc["canons"]
        self.by_id = {b["id"]: b for b in self.books}

    def protestant(self):
        return [self.by_id[i] for i in self.canons["protestant"]["books"]]

    def test_protestant_canon_is_sixty_six_books(self):
        self.assertEqual(len(self.protestant()), 66)

    def test_protestant_chapter_total(self):
        # 1189 chapters. A wrong chapter count in any single book shows up here
        # rather than as a silent gap in a reading view.
        self.assertEqual(sum(b["chapters"] for b in self.protestant()), 1189)

    def test_protestant_ids_are_canonical_order(self):
        self.assertEqual([b["id"] for b in self.protestant()], list(range(1, 67)))
        self.assertEqual(self.protestant()[0]["name"], "Genesis")
        self.assertEqual(self.protestant()[-1]["name"], "Revelation")

    def test_testament_split(self):
        protestant = self.protestant()
        self.assertEqual(sum(b["testament"] == "OT" for b in protestant), 39)
        self.assertEqual(sum(b["testament"] == "NT" for b in protestant), 27)

    def test_names_and_abbrs_unique(self):
        self.assertEqual(len({b["name"] for b in self.books}), len(self.books))
        self.assertEqual(len({b["abbr"] for b in self.books}), len(self.books))

    def test_wider_canons_contain_the_protestant_one(self):
        # Catholic and Orthodox canons add to the 66 rather than replacing them,
        # so a reader switching canon never loses a book.
        protestant = set(self.canons["protestant"]["books"])
        for name in ("catholic", "orthodox"):
            self.assertTrue(protestant.issubset(set(self.canons[name]["books"])), name)

    def test_every_canon_book_exists_and_is_documented(self):
        known = set(self.by_id)
        for name, meta in self.canons.items():
            self.assertTrue(meta.get("label"), name)
            self.assertTrue(meta.get("note"), name)
            self.assertTrue(set(meta["books"]).issubset(known), name)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.sources = json.loads(
            (ROOT / "data" / "sources" / "sources.json").read_text()
        )["sources"]
        self.downloads = json.loads(
            (ROOT / "data" / "sources" / "downloads.json").read_text()
        )["downloads"]

    def test_every_source_declares_a_licence(self):
        # The whole provenance story rests on this: an unlicensed source must
        # never reach the registry unnoticed.
        for src in self.sources:
            self.assertTrue(src.get("license"), f"{src['id']} has no licence")
            self.assertTrue(src.get("name"), f"{src['id']} has no name")

    def test_no_noncommercial_source_is_fetched(self):
        """A NonCommercial or declaration-gated source must never be in the fetch list.

        LXX-Rahlfs carries exactly the tagging this project wants, which is why
        this needs to be a test and not a good intention.
        """
        blocked = {
            s["id"] for s in self.sources
            if "NC" in s.get("license", "") or "declaration" in s.get("license", "")
        }
        self.assertIn("lxx-rahlfs-1935", blocked, "expected Rahlfs to be marked blocked")
        for entry in self.downloads:
            self.assertNotIn(entry["source_id"], blocked,
                             f"{entry['source_id']} is licence-blocked but is in downloads")

    def test_source_ids_unique(self):
        ids = [s["id"] for s in self.sources]
        self.assertEqual(len(ids), len(set(ids)))

    def test_downloads_reference_known_sources(self):
        known = {s["id"] for s in self.sources}
        for entry in self.downloads:
            self.assertIn(entry["source_id"], known)

    def test_download_urls_are_https(self):
        for entry in self.downloads:
            for spec in entry.get("files", []):
                self.assertTrue(spec["url"].startswith("https://"), spec["url"])


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        conn = sqlite3.connect(self.db)
        conn.executescript((ROOT / "db" / "schema.sql").read_text())
        init_db.upsert_sources(conn, init_db.load_registry())
        init_db.upsert_canon(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_canon_loads(self):
        conn = sqlite3.connect(self.db)
        count, chapters = conn.execute(
            "SELECT COUNT(*), SUM(b.chapters) FROM canon_membership m "
            "JOIN book b ON b.id = m.book_id WHERE m.canon = 'protestant'"
        ).fetchone()
        self.assertEqual(count, 66)
        self.assertEqual(chapters, 1189)
        conn.close()

    def test_all_three_canons_load(self):
        conn = sqlite3.connect(self.db)
        sizes = dict(conn.execute(
            "SELECT canon, COUNT(*) FROM canon_membership GROUP BY canon"
        ))
        self.assertEqual(sizes["protestant"], 66)
        self.assertGreater(sizes["catholic"], sizes["protestant"])
        self.assertGreater(sizes["orthodox"], sizes["catholic"])
        conn.close()

    def test_content_tables_carry_provenance(self):
        # Provenance is enforced structurally, not by convention: every table
        # holding a displayable claim must have a source_id column.
        conn = sqlite3.connect(self.db)
        for table in ("token", "lemma", "sense", "gloss", "rendering", "version", "perspective"):
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            self.assertIn("source_id", columns, f"{table} has no source_id")
        conn.close()

    def test_source_foreign_key_is_enforced(self):
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO lemma (lemma, language, strongs, source_id) "
                "VALUES ('x', 'grc', 'G1', 'no-such-source')"
            )
        conn.close()

    def test_init_db_is_rerunnable(self):
        # Re-running must not duplicate rows; the count is whatever the canon
        # file holds, so this asserts idempotency rather than a canon size.
        conn = sqlite3.connect(self.db)
        before = conn.execute("SELECT COUNT(*) FROM book").fetchone()[0]
        init_db.upsert_sources(conn, init_db.load_registry())
        init_db.upsert_canon(conn)
        conn.commit()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM book").fetchone()[0], before)
        conn.close()


class CompositionDateTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads((ROOT / "data" / "composition_dates.json").read_text())

    def test_every_book_is_dated(self):
        books = {b["name"] for b in json.loads((ROOT / "data" / "canon.json").read_text())["books"]}
        dated = {e["book"] for e in self.doc["books"]}
        self.assertEqual(books, dated)

    def test_ranges_are_ordered_and_never_points_only(self):
        for entry in self.doc["books"]:
            for tradition in ("traditional", "critical"):
                span = entry[tradition]
                self.assertLessEqual(
                    span["earliest"], span["latest"],
                    f"{entry['book']} {tradition} range runs backwards",
                )

    def test_traditions_are_documented(self):
        # A dating scheme without a stated position is exactly the hidden
        # editorial judgement this app is meant to avoid.
        for key, meta in self.doc["traditions"].items():
            self.assertTrue(meta.get("label"))
            self.assertTrue(meta.get("description"))


class StatsReportTests(unittest.TestCase):
    """The deploy's own reporting broke a release once, by assuming every
    statistic was a number. It is a script with tests now, not inline YAML."""

    def test_nested_mappings_do_not_raise(self):
        lines = report_stats.format_stats(
            {"canons": {"protestant": 66, "catholic": 76}}
        )
        self.assertEqual(lines, ["canons: catholic 76, protestant 66"])

    def test_numbers_get_thousands_separators(self):
        self.assertEqual(report_stats.format_stats({"lemmas": 14686}), ["lemmas: 14,686"])

    def test_strings_and_none_survive(self):
        self.assertEqual(
            report_stats.format_stats({"built": "yes", "missing": None}),
            ["built: yes", "missing: None"],
        )

    def test_real_stats_file_formats(self):
        site = ROOT / "site" / "stats.json"
        if not site.exists():
            self.skipTest("site not built")
        stats = json.loads(site.read_text())
        self.assertEqual(len(report_stats.format_stats(stats)), len(stats))


class GreekNormalisationTests(unittest.TestCase):
    def test_diacritics_are_folded(self):
        # This fold is what links MorphGNT lemmas to Strong's entries, which
        # accent differently. If it regresses, NT linkage silently collapses.
        self.assertEqual(ingest.normalize_greek("ἀγάπη"), ingest.normalize_greek("αγαπη"))
        self.assertEqual(ingest.normalize_greek("Ἰησοῦς"), ingest.normalize_greek("ιησους"))

    def test_final_sigma_folds(self):
        self.assertEqual(ingest.normalize_greek("λόγος"), ingest.normalize_greek("λογοσ"))

    def test_distinct_words_stay_distinct(self):
        self.assertNotEqual(ingest.normalize_greek("ἀγάπη"), ingest.normalize_greek("φιλία"))


@unittest.skipUnless((RAW / "strongs").exists(), "fetched corpora not present")
class StrongsParsingTests(unittest.TestCase):
    def test_hebrew_dictionary_parses(self):
        data = ingest.strongs_json(RAW / "strongs" / "strongs-hebrew-dictionary.js")
        self.assertIn("H430", data)
        self.assertEqual(data["H430"]["lemma"], "אֱלֹהִים")

    def test_greek_dictionary_parses(self):
        data = ingest.strongs_json(RAW / "strongs" / "strongs-greek-dictionary.js")
        self.assertIn("G26", data)
        self.assertEqual(data["G26"]["lemma"], "ἀγάπη")


@unittest.skipUnless((ROOT / "data" / "studyhelp.db").exists(), "database not built")
class IngestedCorpusTests(unittest.TestCase):
    """Spot-checks against counts that are independently verifiable.

    These guard the parsers: an off-by-one in verse handling or a broken lemma
    link moves these numbers immediately.
    """

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(ROOT / "data" / "studyhelp.db")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def occurrences(self, strongs):
        row = self.conn.execute(
            "SELECT id FROM lemma WHERE strongs = ?", (strongs,)
        ).fetchone()
        if not row:
            self.skipTest(f"{strongs} not loaded")
        return self.conn.execute(
            "SELECT COUNT(*) FROM token WHERE lemma_id = ?", (row[0],)
        ).fetchone()[0]

    def first_reference(self, strongs):
        row = self.conn.execute(
            "SELECT b.name, v.chapter, v.verse FROM token t "
            "JOIN verse v ON v.id = t.verse_id JOIN book b ON b.id = v.book_id "
            "JOIN lemma l ON l.id = t.lemma_id WHERE l.strongs = ? "
            "ORDER BY b.id, v.chapter, v.verse, t.position LIMIT 1",
            (strongs,),
        ).fetchone()
        if not row:
            self.skipTest(f"{strongs} not loaded")
        return f"{row[0]} {row[1]}:{row[2]}"

    def test_elohim_first_appears_in_genesis_1_1(self):
        self.assertEqual(self.first_reference("H430"), "Genesis 1:1")

    def test_agape_first_appears_in_matthew(self):
        self.assertEqual(self.first_reference("G26"), "Matthew 24:12")

    def test_agape_occurrence_count(self):
        # ~116 in the SBLGNT; a tight band catches parser drift without being
        # brittle about edition differences.
        self.assertTrue(110 <= self.occurrences("G26") <= 120, self.occurrences("G26"))

    def test_greek_corpus_size(self):
        count = self.conn.execute(
            "SELECT COUNT(*) FROM token WHERE source_id = 'morphgnt-sblgnt'"
        ).fetchone()[0]
        if not count:
            self.skipTest("morphgnt not ingested")
        self.assertTrue(135_000 <= count <= 140_000, count)

    def test_composition_dates_loaded_for_every_book(self):
        books, dated = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM book), COUNT(DISTINCT book_id) FROM composition_date"
        ).fetchone()
        self.assertEqual(dated, books)

    def test_deuterocanonical_books_are_not_dropped(self):
        """Wycliffe, the Vulgate and the LXX all carry books beyond the 66.

        Before the canon became configurable these were silently discarded,
        which quietly excluded Catholic and Orthodox readers.
        """
        count = self.conn.execute(
            "SELECT COUNT(*) FROM rendering r JOIN verse v ON v.id = r.verse_id "
            "JOIN book b ON b.id = v.book_id WHERE b.name = 'Sirach'"
        ).fetchone()[0]
        if not self.conn.execute("SELECT COUNT(*) FROM rendering").fetchone()[0]:
            self.skipTest("translations not ingested")
        self.assertGreater(count, 0, "Sirach loaded from no source")

    def test_kjv_verse_count(self):
        count = self.conn.execute(
            "SELECT COUNT(*) FROM rendering WHERE version_id = 'kjv'"
        ).fetchone()[0]
        if not count:
            self.skipTest("translations not ingested")
        # The KJV has 31,102 verses. Book-name mismatches during ingest show up
        # here as a shortfall rather than as silently missing books.
        self.assertEqual(count, 31_102)

    def test_translations_span_eras(self):
        years = [
            r[0] for r in self.conn.execute(
                "SELECT year FROM version WHERE year IS NOT NULL ORDER BY year"
            )
        ]
        if not years:
            self.skipTest("translations not ingested")
        self.assertLess(years[0], 1600, "no pre-1600 translation loaded")
        self.assertGreater(years[-1], 1900, "no modern translation loaded")

    def test_rendering_names_the_bytes_it_came_from(self):
        # version.source_id names the upstream edition; rendering.source_id names
        # where the bytes were actually parsed from. They are meant to differ.
        row = self.conn.execute(
            "SELECT r.source_id, v.source_id FROM rendering r "
            "JOIN version v ON v.id = r.version_id LIMIT 1"
        ).fetchone()
        if not row:
            self.skipTest("translations not ingested")
        self.assertNotEqual(row[0], row[1])

    def test_septuagint_loaded(self):
        count = self.conn.execute(
            "SELECT COUNT(*) FROM rendering WHERE version_id = 'lxx-swete'"
        ).fetchone()[0]
        if not count:
            self.skipTest("LXX not ingested")
        self.assertGreater(count, 20_000)

    def test_septuagint_keeps_its_own_versification(self):
        # LXX numbering differs from the Hebrew, so its verses must not be filed
        # under English versification -- that would silently misalign the Psalms.
        rows = self.conn.execute(
            "SELECT COUNT(*) FROM rendering r JOIN verse v ON v.id = r.verse_id "
            "WHERE r.version_id = 'lxx-swete' AND v.versification != 'lxx'"
        ).fetchone()[0]
        self.assertEqual(rows, 0)

    def test_every_token_traces_to_a_registered_source(self):
        orphans = self.conn.execute(
            "SELECT COUNT(*) FROM token t "
            "LEFT JOIN source s ON s.id = t.source_id WHERE s.id IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0)


if __name__ == "__main__":
    unittest.main()
