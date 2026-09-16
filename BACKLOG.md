# Backlog

## What cannot be closed from here

Four items are not engineering problems and will not be closed by writing code.
They are recorded here so the trade-off stays visible rather than drifting out of view.

- **Semantic domains (Louw-Nida via UBS MARBLE, and the Semantic Dictionary of Biblical
  Hebrew).** Both are marked "used with permission" inside MACULA rather than openly
  licensed. Clear Bible holds that permission; we do not inherit it. Only the United
  Bible Societies can change this, and only if asked.
- **Licensed modern translations (NIV, ESV, NASB, CSB).** Need paid or permissioned
  access. The Berean Standard Bible covers the modern slot meanwhile. Never scrape them.
- **KJV UK Crown copyright.** Public domain almost everywhere; Crown letters patent still
  apply within the UK. Geo-restrict or accept the risk — an owner's decision, not a
  technical one.
- **A Strong's-tagged historical English translation.** Four sources checked and none
  carries one: the scrollmapper KJV in both its JSON and SQLite exports, the open-bibles
  OSIS edition, and STEPBible (which tags only the ESV, whose text is copyrighted).
  Without one, drift can be shown across languages and across whole verses, but not word
  by word across centuries.

Deferred work and best practices. The decision for now is **open source only** —
anything requiring a commercial licence, paid access or manual scholarly effort is
recorded here rather than dropped, so the trade-off stays visible.

## Licensing and sources

- [x] **Verify the `unverified` entries in `data/sources/sources.json`.** Several
      registry rows carry licence claims taken from publisher descriptions rather than
      confirmed against the licence text. Each needs a check and a `verified` date.
- [ ] **Resolve the SBLGNT EULA question.** The MorphGNT *tagging* is CC-BY-SA, but the
      SBLGNT *base text* is under its own EULA. Confirm what redistribution is permitted
      before shipping the Greek text itself. The tagging is separable if it is not.
- [ ] **KJV UK Crown copyright.** Public domain in most of the world; Crown letters
      patent still apply in the UK. Decide whether to geo-restrict or accept the risk.
- [ ] **Licensed modern translations (NIV, ESV, NASB, CSB).** Best practice would be to
      include them for the modern end of the drift timeline. Deferred: they need paid or
      permissioned API access. The Berean Standard Bible (public domain, 2023) covers the
      modern slot in the meantime. **Never scrape them.**
- [x] **Automated licence-compliance check.** A test that fails if any displayed claim
      resolves to a source whose `license` is unset or whose `verified` is `unverified`.
- [x] **Attribution surface.** Every licence here (CC-BY, CC-BY-SA) requires visible
      credit. Build a single attributions page generated from the registry, not
      hand-maintained.
- [ ] **CC-BY-SA share-alike propagation.** Some sources (MorphGNT tagging, unfoldingWord,
      Perseus LSJ) are share-alike. Determine what that obliges for derived data we
      publish, and whether to segregate SA-derived tables from permissive ones.

## Data quality

- [x] **Cross-check the tagging layers against each other.** OSHB, STEPBible TAHOT and
      MorphGNT overlap; disagreements between them are signal, not noise. Store both
      rather than picking a winner.
- [x] **Versification mapping.** Hebrew, LXX, Vulgate and English verse numbering diverge
      (Psalm superscriptions especially). The `verse.versification` column exists; the
      mapping tables do not yet. This will silently corrupt cross-version comparison if
      left undone.
- [x] **Composition dates with attribution.** The chronology view needs per-book date
      ranges, and these are genuinely contested. Store as ranges with a `source_id`
      (schema supports it), and show the range rather than a point estimate.
- [x] **Aggregator drift.** Convenience aggregators can silently alter text. Record the
      upstream edition and checksum; never cite the aggregator as the authority.
- [x] **Text normalisation for historical English.** Tyndale/Geneva/Wycliffe spelling
      varies wildly. Needs a normalisation layer for search that preserves the original
      for display.

## Engineering

- [x] **No inline scripting in workflows.** The deploy broke because a reporting step
      was inline YAML that no test could reach. It is a tested script now; the same
      should be true of anything else that runs only in CI.

- [x] **Ingestion parsers.** `scripts/ingest.py` loads Strong's (lemmas + senses), OSHB
      (Hebrew tokens) and MorphGNT (Greek tokens). 306,785 Hebrew and 137,554 Greek
      tokens; 98.5% of Greek tokens link to a Strong's entry.
- [x] **Close the Greek linkage gap.** MACULA Greek (CC BY 4.0) carries an explicit
      Strong's number for every word, replacing the diacritic-folding heuristic. Five
      tokens out of 137,554 remain unlinked, down from about 2,100.
- [x] **Load the English translations.** Nine editions loaded, 280,600 renderings,
      Wycliffe (1395) through the Berean Standard Bible (2023). KJV verse count checked
      against the known 31,102.
- [x] **Ingest the Septuagint text.** Swete (Cambridge 1909–1930) loaded, 22,955 verses,
      readable alongside every other version.
- [x] **Lemma-level LXX bridging — solved from a different direction.** MACULA Hebrew
      (CC BY 4.0) records the Greek equivalent for each Hebrew word, giving 251,639
      Hebrew→Greek links without needing the licence-blocked tagged Septuagint. The chain
      is now queryable both ways: kapporeth → hilasterion, and back.
- [x] **The Septuagint text itself is still untagged.** The bridge comes from MACULA's
      Hebrew-side alignment, not from a lemma-tagged LXX, so the Swete text loaded here
      still cannot be searched by word. Tagging it with an open analyser remains the route
      to that, and is now a smaller prize than it was.
- [ ] Previously recorded, still true — **the tagged Septuagint editions are blocked:** This is the most consequential
      open problem in the project. The chain Hebrew→LXX→Greek NT needs the LXX *tagged by
      lemma*, and the three available routes each fail:
      - **Rahlfs via CATSS/CCAT** has the morphology and Strong's tags, but is
        CC BY-NC-SA (NonCommercial) over a text requiring a signed user declaration.
        Ruled out by the open-source-only rule, and a test now enforces that it is
        never fetched.
      - **Swete** is public domain and loaded, but its published files carry no lemma
        or morphology tagging at all.
      - **Open Scriptures LXX lemmas** are CC BY 4.0, but keyed to the CCAT text we
        cannot take. Open keys into a closed text unlock nothing on their own.
      Options, in rough order of cost: tag Swete ourselves with an open morphological
      analyser (James Tauber's greek-inflexion is the obvious candidate, and the Swete
      repo already anticipates this); seek permission for CCAT use; or accept
      surface-form-only bridging and label it as such. **Needs a decision.**
- [x] **Per-layer occurrence counts.** Show a word's count in Hebrew, LXX, Greek NT and
      each English version side by side, as sketched on the board.
- [x] **Mark primary vs derivative sources** in the registry. A tagged original-language
      text and an aggregated translation should not carry equal weight.
- [x] **The `gloss` table is populated.** 386,092 per-word glosses from MACULA, in
      English (Berean Interlinear and Cherith) and Mandarin (Cherith). A word's page now
      shows what it actually became, and how often.
- [ ] **Extend alignment to the full translations.** Glosses currently cover the Greek
      New Testament only. The Hebrew side needs MACULA Hebrew, and the historical English
      versions (Wycliffe, Tyndale, KJV) have no word-level alignment at all — so the drift
      view cannot yet run across centuries, only across present-day glosses.
- [x] **A second sense authority — reached by the open route.** Brown-Driver-Briggs is
      public domain and keyed to Strong's through the Open Scriptures lexical index;
      9,291 senses loaded. Hebrew words now show two dictionaries side by side, and where
      they differ the difference is left standing. This is the first time the app can do
      the thing it exists for.
- [ ] **Semantic domains are permission-only — checked, and the answer is no.** Louw-Nida
      (via UBS MARBLE) for Greek and the Semantic Dictionary of Biblical Hebrew are both
      marked "used with permission" inside MACULA rather than CC BY. Clear Bible holds
      that permission; we do not inherit it. Seeking permission from the United Bible
      Societies directly is the only legitimate route. A test now fails if those columns
      are ever ingested.
- [x] **A second Greek authority.** Abbott-Smith loaded, 11,485 senses. Greek words now
      show two dictionaries, as Hebrew words already did.
- [x] **unfoldingWord is unreachable from this environment.** git.door43.org is blocked
      by the network policy and the repositories are not mirrored on GitHub, so the
      aligned ULT/UST could not be evaluated.
- [x] **BDB senses.** BrownDriverBriggs.xml is fetched but not parsed; currently the
      only Hebrew senses are Strong's, which is thin and dated for real study.
- [x] **Enumerate multi-file sources.** `downloads.json` now lists all 71 files
      (39 OSHB books, 27 MorphGNT books, 5 lexicon files).
- [x] **Re-fetch and diff.** `fetch_log` records sha256 per retrieval; add a command that
      re-fetches and reports what changed upstream.
- [x] **Tests.** 23 Python tests and 17 reference-parser tests, run by CI on every push
      and pull request.
- [x] **Consider Postgres.** SQLite is right for now. Full-corpus concordance queries
      across every version may outgrow it.

## Deployment

- [x] **Static site + Pages deploy via Actions.** Search, disambiguation and lemma detail,
      published on every push to `main`.
- [x] **Repo setting: Pages source = GitHub Actions.** Must be set once by hand; the
      deploy job cannot do it for itself.
- [x] **Index size.** `index.json` is 2.1 MB and every visitor downloads it. Fine now;
      shard or move to a prefix-indexed search once English translations land.
- [x] **14,686 small files.** Works on Pages, but a keyed bundle would deploy faster.

## Regional and language coverage

- [x] **Translation is optional.** A reader can choose "original only", and the choice
      is remembered.
- [x] **Configurable canon.** Which books count as scripture is now data, not a
      hardcoded assumption. Protestant (66), Catholic (76) and Orthodox (82) canons are
      defined and selectable. Wycliffe and the Vulgate gained ~5,800 verses each and the
      Septuagint ~5,200 that were previously discarded in silence.
- [x] **No tagged text covers the deuterocanonical books.** They can now be READ but not
      SEARCHED: OSHB and MorphGNT cover the 66-book canon only, so choosing a wider canon
      changes what is readable, not what is countable. The site says so plainly. Fixing
      it needs tagged Greek for those books — the same LXX tagging problem below.
- [x] **Right-to-left rendering.** Hebrew is already on screen; proper bidi handling is
      needed before any Arabic, Persian or Urdu translation is added.
- [x] **Indic and CJK scripts.** Line height, shaping and font fallbacks will need work
      before Hindi, Tamil, Telugu, Bengali or Chinese translations render acceptably.
- [x] **Non-English open translations.** Coverage is uneven by language; the UI should
      show honestly what exists per language rather than implying parity.
- [x] **Interface language separate from translation language.** A reader may want a
      Tamil translation with an English interface, or the reverse.
- [x] **Versification schemes.** Hebrew, LXX, Vulgate and English numbering diverge, and
      Orthodox and Catholic canons differ in book count. The `versification` column
      exists; the mapping tables do not.

## Product

- [x] **A verse is now an entry point.** Typing a reference opens the chapter with an
      interlinear beneath each verse, every word linking into its study. The app's stated
      purpose is decoding a verse, and until now the only way in was a word.
- [x] **Design pass.** The chain is the spine of a word's page; composition dates are drawn
      as a timeline rather than listed; the distribution is summarised by genre and
      collapsed to six books; renderings are proportional bars instead of equal chips;
      settings are tucked behind a control; results are marked by language; the landing
      page offers six starting points.
- [ ] **Historical drift is still missing, and the obvious source does not have it.** The
      scrollmapper KJV is titled "with Strongs Numbers and Morphology" but both its JSON
      and SQLite exports carry plain text only. Tracing a word across centuries needs a
      genuinely aligned historical version; without one, drift can be shown across
      languages but not across time.
- [x] **Two reference parsers now exist.** `bible-study/js/books.js` is the standalone,
      tested one; the site parses references from `books.json` so it covers all 82 books.
      They should converge on one implementation.
- [x] **Compare two words side by side.** Still worth building: the classic word study is
      comparative (agape against phileo, chesed against rachamim).

- [x] **English word → lemma disambiguation UI.** Searching "love" must resolve to several
      Greek lemmas. The disambiguation step is the app's first real screen and its
      hardest design problem — get it wrong and the whole premise collapses back into
      English-word study.
- [x] **Composition order vs canonical order.** "First appearance" has two defensible
      answers. Show both, labelled.
- [x] **Perspectives sourcing.** Open-licensed commentary is thin. Public-domain options
      (Matthew Henry, Calvin, Gill, Barnes) skew heavily Protestant and pre-1900 —
      using only these would itself introduce the bias the app exists to avoid.
      Needs a deliberate plan, and honest labelling of the gaps.
- [x] **Explicit "we don't know" state.** Where sources genuinely conflict or evidence is
      thin, say so rather than presenting a confident synthesis.


## Closed in this pass, with what was actually decided

- **Septuagint words now carry a lemma** — 572,353 tokens, 84.3% matched by form against
  forms the Greek New Testament attests. This is inference, not analysis: every such token
  is marked `inferred`, counted apart from tagged text, and labelled wherever it appears.
  A test asserts the separation, after the test helpers themselves briefly forgot it and
  moved agape's first appearance from Matthew to a Septuagint verse in 2 Samuel.
- **The deuterocanonical books became searchable** as a side effect: they have no other
  tagged text, and now have this one, with the same caveat attached.
- **Versification mapping** — the Hebrew-to-Septuagint psalm numbering is mapped both ways
  (300 rows) and applied, so asking for Psalm 51 shows Greek Psalm 50 rather than the psalm
  that happens to share the number.
- **Historical English spelling** folds the settled conventions (u/v, sch/sh, y/i, doubled
  letters, silent final e) as a fallback pass, so "synne" reaches chatta'ah. It does not
  fold vowel variation such as euell/evil: a fold loose enough for that joins genuinely
  different words.
- **Search ranking** now prefers the word a term is usually rendered as over one that
  merely lists it among every rendering a translator ever chose. Before this, "love"
  returned shakab, "to lie down", ahead of agape.
- **Index size** — the searchable gloss text is 1.3 MB of it and is only needed once
  someone searches by meaning, so it is fetched on demand. Arrival cost fell from 3.4 MB
  to 2.0 MB.
- **File count and Postgres, both measured rather than argued.** Uploading ~16,000 files
  takes about 4 seconds, and the heaviest realistic queries run in 7 ms (a full concordance),
  47 ms (distribution across every lemma) and under 1 ms (the cross-corpus Septuagint join)
  against a 320 MB database. Neither needs changing. Revisit if a query passes a second or
  concurrent writes appear.
- **Cross-check of the tagging layers** — `scripts/crosscheck.py`. Greek is at 100.00%
  Strong's coverage between MorphGNT and MACULA; Hebrew at 98.79% between OSHB and MACULA.
- **Interface language is now separate from translation language.** Only English exists for
  the interface, and the control says so rather than implying a choice that is not there.
  Language coverage is shown as what open licensing actually reaches.
- **unfoldingWord** — retried against door43 and the bibletranslationtools mirror. Both are
  refused by this network's egress policy, so it cannot be evaluated from here at all.

## Two findings that change what should happen next

- **The SBLGNT EULA could not be read**: sblgnt.com is blocked by the egress proxy. What is
  established is that the MorphGNT tagging is CC BY-SA while the base text sits under a
  separate EULA, and StudyHelp does display that text. There is a clean way out: MACULA
  also publishes **Nestle 1904**, which is public domain by age, and its TSV was confirmed
  available. Switching the displayed Greek to it would remove the dependency entirely.
  That is an editorial choice about which critical text underlies the app, so it is put
  here rather than made unilaterally.
- **Share-alike propagation** — the share-alike sources are the MorphGNT tagging
  (CC BY-SA 3.0) and the Perseus LSJ digitisation, which is registered but not used. If the
  Greek text moves to Nestle 1904 the MorphGNT dependency goes with it, and the question
  largely dissolves. Until then, derived data built from that tagging inherits the
  obligation, and the registry marks which sources carry it.
