// Canon metadata: name, abbreviation, chapter count, testament.
// Chapter counts follow the Protestant 66-book canon.
const BOOKS = [
  ['Genesis', 'Gen', 50, 'OT'],
  ['Exodus', 'Exod', 40, 'OT'],
  ['Leviticus', 'Lev', 27, 'OT'],
  ['Numbers', 'Num', 36, 'OT'],
  ['Deuteronomy', 'Deut', 34, 'OT'],
  ['Joshua', 'Josh', 24, 'OT'],
  ['Judges', 'Judg', 21, 'OT'],
  ['Ruth', 'Ruth', 4, 'OT'],
  ['1 Samuel', '1Sam', 31, 'OT'],
  ['2 Samuel', '2Sam', 24, 'OT'],
  ['1 Kings', '1Kgs', 22, 'OT'],
  ['2 Kings', '2Kgs', 25, 'OT'],
  ['1 Chronicles', '1Chr', 29, 'OT'],
  ['2 Chronicles', '2Chr', 36, 'OT'],
  ['Ezra', 'Ezra', 10, 'OT'],
  ['Nehemiah', 'Neh', 13, 'OT'],
  ['Esther', 'Esth', 10, 'OT'],
  ['Job', 'Job', 42, 'OT'],
  ['Psalms', 'Ps', 150, 'OT'],
  ['Proverbs', 'Prov', 31, 'OT'],
  ['Ecclesiastes', 'Eccl', 12, 'OT'],
  ['Song of Solomon', 'Song', 8, 'OT'],
  ['Isaiah', 'Isa', 66, 'OT'],
  ['Jeremiah', 'Jer', 52, 'OT'],
  ['Lamentations', 'Lam', 5, 'OT'],
  ['Ezekiel', 'Ezek', 48, 'OT'],
  ['Daniel', 'Dan', 12, 'OT'],
  ['Hosea', 'Hos', 14, 'OT'],
  ['Joel', 'Joel', 3, 'OT'],
  ['Amos', 'Amos', 9, 'OT'],
  ['Obadiah', 'Obad', 1, 'OT'],
  ['Jonah', 'Jonah', 4, 'OT'],
  ['Micah', 'Mic', 7, 'OT'],
  ['Nahum', 'Nah', 3, 'OT'],
  ['Habakkuk', 'Hab', 3, 'OT'],
  ['Zephaniah', 'Zeph', 3, 'OT'],
  ['Haggai', 'Hag', 2, 'OT'],
  ['Zechariah', 'Zech', 14, 'OT'],
  ['Malachi', 'Mal', 4, 'OT'],
  ['Matthew', 'Matt', 28, 'NT'],
  ['Mark', 'Mark', 16, 'NT'],
  ['Luke', 'Luke', 24, 'NT'],
  ['John', 'John', 21, 'NT'],
  ['Acts', 'Acts', 28, 'NT'],
  ['Romans', 'Rom', 16, 'NT'],
  ['1 Corinthians', '1Cor', 16, 'NT'],
  ['2 Corinthians', '2Cor', 13, 'NT'],
  ['Galatians', 'Gal', 6, 'NT'],
  ['Ephesians', 'Eph', 6, 'NT'],
  ['Philippians', 'Phil', 4, 'NT'],
  ['Colossians', 'Col', 4, 'NT'],
  ['1 Thessalonians', '1Thess', 5, 'NT'],
  ['2 Thessalonians', '2Thess', 3, 'NT'],
  ['1 Timothy', '1Tim', 6, 'NT'],
  ['2 Timothy', '2Tim', 4, 'NT'],
  ['Titus', 'Titus', 3, 'NT'],
  ['Philemon', 'Phlm', 1, 'NT'],
  ['Hebrews', 'Heb', 13, 'NT'],
  ['James', 'Jas', 5, 'NT'],
  ['1 Peter', '1Pet', 5, 'NT'],
  ['2 Peter', '2Pet', 3, 'NT'],
  ['1 John', '1John', 5, 'NT'],
  ['2 John', '2John', 1, 'NT'],
  ['3 John', '3John', 1, 'NT'],
  ['Jude', 'Jude', 1, 'NT'],
  ['Revelation', 'Rev', 22, 'NT'],
].map(([name, abbr, chapters, testament]) => ({ name, abbr, chapters, testament }));

const BOOK_BY_NAME = new Map(BOOKS.map((b) => [b.name.toLowerCase(), b]));

// Accepts "John", "john 3", "1 cor", "Jn" and similar loose input.
function findBook(input) {
  const q = String(input || '').trim().toLowerCase();
  if (!q) return null;
  if (BOOK_BY_NAME.has(q)) return BOOK_BY_NAME.get(q);

  const exactAbbr = BOOKS.find((b) => b.abbr.toLowerCase() === q);
  if (exactAbbr) return exactAbbr;

  const prefix = BOOKS.filter(
    (b) => b.name.toLowerCase().startsWith(q) || b.abbr.toLowerCase().startsWith(q)
  );
  return prefix.length === 1 ? prefix[0] : prefix[0] || null;
}

// "John 3:16-18" -> { book, chapter, verses, ref }
function parseReference(text) {
  const raw = String(text || '').trim();
  const m = raw.match(/^\s*((?:[1-3]\s*)?[A-Za-z][A-Za-z\s]*?)\s*(\d+)?(?::\s*(\d+)(?:\s*-\s*(\d+))?)?\s*$/);
  if (!m) return null;

  const book = findBook(m[1]);
  if (!book) return null;

  let chapter = m[2] ? parseInt(m[2], 10) : 1;
  if (chapter < 1) chapter = 1;
  if (chapter > book.chapters) chapter = book.chapters;

  const verseStart = m[3] ? parseInt(m[3], 10) : null;
  const verseEnd = m[4] ? parseInt(m[4], 10) : verseStart;

  return { book, chapter, verseStart, verseEnd, ref: formatRef(book, chapter, verseStart, verseEnd) };
}

function formatRef(book, chapter, verseStart, verseEnd) {
  let ref = `${book.name} ${chapter}`;
  if (verseStart) {
    ref += `:${verseStart}`;
    if (verseEnd && verseEnd !== verseStart) ref += `-${verseEnd}`;
  }
  return ref;
}
