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

- [ ] **Ingestion parsers.** `fetch_sources.py` retrieves and logs provenance; parsers to
      load OSIS XML, MorphGNT TSV and the lexicon XML into `token`/`lemma`/`sense` are
      not written yet. This is the next real milestone.
- [ ] **Enumerate multi-file sources.** OSHB and MorphGNT are one file per book;
      `downloads.json` currently lists a single sample file each. Enumerate the full set.
- [ ] **Re-fetch and diff.** `fetch_log` records sha256 per retrieval; add a command that
      re-fetches and reports what changed upstream.
- [ ] **Tests.** Canon integrity (66 books / 1189 chapters) is currently asserted ad hoc;
      make it a real test, alongside reference-parser cases.
- [ ] **Consider Postgres.** SQLite is right for now. Full-corpus concordance queries
      across every version may outgrow it.

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
