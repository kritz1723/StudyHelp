# StudyHelp

A Bible study tool for decoding what a verse actually means — by tracing the word,
not by handing over one commentator's opinion.

For a given word, StudyHelp aims to show where it first appears, every other place it
is used, what it meant in the original language, how that meaning shifted over time,
and how different traditions and eras have read it — each claim attributed to a source,
with disagreement shown rather than resolved.

## Status

Early. Design in progress.

- `docs/word-study-architecture.md` — data model, the four views, source acquisition
  plan, and build order. Draft, pending ideation-board review.
- `bible-study/js/books.js` — canon metadata (66 books, chapter counts, testament) and
  a loose reference parser (`John 3:16-18`, `1 cor 13`, `Jn`).
