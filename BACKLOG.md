# Backlog

Deferred work and best practices. The decision for now is **open source only** —
anything requiring a commercial licence, paid access or manual scholarly effort is
recorded here rather than dropped, so the trade-off stays visible.

## Licensing and sources

- [ ] **Verify the `unverified` entries in `data/sources/sources.json`.** Several
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
- [ ] **Automated licence-compliance check.** A test that fails if any displayed claim
      resolves to a source whose `license` is unset or whose `verified` is `unverified`.
- [ ] **Attribution surface.** Every licence here (CC-BY, CC-BY-SA) requires visible
      credit. Build a single attributions page generated from the registry, not
      hand-maintained.
- [ ] **CC-BY-SA share-alike propagation.** Some sources (MorphGNT tagging, unfoldingWord,
      Perseus LSJ) are share-alike. Determine what that obliges for derived data we
      publish, and whether to segregate SA-derived tables from permissive ones.

## Data quality

- [ ] **Cross-check the tagging layers against each other.** OSHB, STEPBible TAHOT and
      MorphGNT overlap; disagreements between them are signal, not noise. Store both
      rather than picking a winner.
- [ ] **Versification mapping.** Hebrew, LXX, Vulgate and English verse numbering diverge
      (Psalm superscriptions especially). The `verse.versification` column exists; the
      mapping tables do not yet. This will silently corrupt cross-version comparison if
      left undone.
- [ ] **Composition dates with attribution.** The chronology view needs per-book date
      ranges, and these are genuinely contested. Store as ranges with a `source_id`
      (schema supports it), and show the range rather than a point estimate.
- [ ] **Aggregator drift.** Convenience aggregators can silently alter text. Record the
      upstream edition and checksum; never cite the aggregator as the authority.
- [ ] **Text normalisation for historical English.** Tyndale/Geneva/Wycliffe spelling
      varies wildly. Needs a normalisation layer for search that preserves the original
      for display.

## Engineering

- [ ] **No inline scripting in workflows.** The deploy broke because a reporting step
      was inline YAML that no test could reach. It is a tested script now; the same
      should be true of anything else that runs only in CI.

- [x] **Ingestion parsers.** `scripts/ingest.py` loads Strong's (lemmas + senses), OSHB
      (Hebrew tokens) and MorphGNT (Greek tokens). 306,785 Hebrew and 137,554 Greek
      tokens; 98.5% of Greek tokens link to a Strong's entry.
- [ ] **Close the remaining 1.5% Greek linkage gap.** MorphGNT carries no Strong's
      numbers, so linkage is by diacritic-folded lemma text. ~2,100 tokens and 489
      lemmas remain unlinked. STEPBible TAGNT has explicit Strong's tags and would
      replace the heuristic entirely — the better fix.
- [x] **Load the English translations.** Nine editions loaded, 280,600 renderings,
      Wycliffe (1395) through the Berean Standard Bible (2023). KJV verse count checked
      against the known 31,102.
- [x] **Ingest the Septuagint text.** Swete (Cambridge 1909–1930) loaded, 22,955 verses,
      readable alongside every other version.
- [ ] **Lemma-level LXX bridging is BLOCKED by licensing.** This is the most consequential
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
- [ ] **Per-layer occurrence counts.** Show a word's count in Hebrew, LXX, Greek NT and
      each English version side by side, as sketched on the board.
- [ ] **Mark primary vs derivative sources** in the registry. A tagged original-language
      text and an aggregated translation should not carry equal weight.
- [ ] **The `gloss` table is still empty.** Word-level alignment between a translation
      and the original token is what turns "translations loaded" into a real drift view;
      unfoldingWord's aligned texts are the likely route.
- [ ] **BDB senses.** BrownDriverBriggs.xml is fetched but not parsed; currently the
      only Hebrew senses are Strong's, which is thin and dated for real study.
- [x] **Enumerate multi-file sources.** `downloads.json` now lists all 71 files
      (39 OSHB books, 27 MorphGNT books, 5 lexicon files).
- [ ] **Re-fetch and diff.** `fetch_log` records sha256 per retrieval; add a command that
      re-fetches and reports what changed upstream.
- [x] **Tests.** 23 Python tests and 17 reference-parser tests, run by CI on every push
      and pull request.
- [ ] **Consider Postgres.** SQLite is right for now. Full-corpus concordance queries
      across every version may outgrow it.

## Deployment

- [x] **Static site + Pages deploy via Actions.** Search, disambiguation and lemma detail,
      published on every push to `main`.
- [ ] **Repo setting: Pages source = GitHub Actions.** Must be set once by hand; the
      deploy job cannot do it for itself.
- [ ] **Index size.** `index.json` is 2.1 MB and every visitor downloads it. Fine now;
      shard or move to a prefix-indexed search once English translations land.
- [ ] **14,686 small files.** Works on Pages, but a keyed bundle would deploy faster.

## Regional and language coverage

- [x] **Translation is optional.** A reader can choose "original only", and the choice
      is remembered.
- [x] **Configurable canon.** Which books count as scripture is now data, not a
      hardcoded assumption. Protestant (66), Catholic (76) and Orthodox (82) canons are
      defined and selectable. Wycliffe and the Vulgate gained ~5,800 verses each and the
      Septuagint ~5,200 that were previously discarded in silence.
- [ ] **No tagged text covers the deuterocanonical books.** They can now be READ but not
      SEARCHED: OSHB and MorphGNT cover the 66-book canon only, so choosing a wider canon
      changes what is readable, not what is countable. The site says so plainly. Fixing
      it needs tagged Greek for those books — the same LXX tagging problem below.
- [ ] **Right-to-left rendering.** Hebrew is already on screen; proper bidi handling is
      needed before any Arabic, Persian or Urdu translation is added.
- [ ] **Indic and CJK scripts.** Line height, shaping and font fallbacks will need work
      before Hindi, Tamil, Telugu, Bengali or Chinese translations render acceptably.
- [ ] **Non-English open translations.** Coverage is uneven by language; the UI should
      show honestly what exists per language rather than implying parity.
- [ ] **Interface language separate from translation language.** A reader may want a
      Tamil translation with an English interface, or the reverse.
- [ ] **Versification schemes.** Hebrew, LXX, Vulgate and English numbering diverge, and
      Orthodox and Catholic canons differ in book count. The `versification` column
      exists; the mapping tables do not.

## Product

- [ ] **English word → lemma disambiguation UI.** Searching "love" must resolve to several
      Greek lemmas. The disambiguation step is the app's first real screen and its
      hardest design problem — get it wrong and the whole premise collapses back into
      English-word study.
- [ ] **Composition order vs canonical order.** "First appearance" has two defensible
      answers. Show both, labelled.
- [ ] **Perspectives sourcing.** Open-licensed commentary is thin. Public-domain options
      (Matthew Henry, Calvin, Gill, Barnes) skew heavily Protestant and pre-1900 —
      using only these would itself introduce the bias the app exists to avoid.
      Needs a deliberate plan, and honest labelling of the gaps.
- [ ] **Explicit "we don't know" state.** Where sources genuinely conflict or evidence is
      thin, say so rather than presenting a confident synthesis.
