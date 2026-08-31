// Tests for the reference parser in bible-study/js/books.js.
// Run with: node tests/books.test.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'bible-study', 'js', 'books.js'), 'utf8');
// books.js declares with `const`, which does not attach to the vm context
// object, so the module's bindings are returned as the script's completion value.
const context = vm.createContext({});
const { BOOKS, findBook, parseReference } = vm.runInContext(
  `${source}\n;({ BOOKS, findBook, parseReference });`,
  context
);

let failures = 0;

function check(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    console.error(`FAIL ${label}\n  expected ${JSON.stringify(expected)}\n  actual   ${JSON.stringify(actual)}`);
    failures += 1;
  } else {
    console.log(`ok   ${label}`);
  }
}

check('66 books', BOOKS.length, 66);
check('1189 chapters', BOOKS.reduce((n, b) => n + b.chapters, 0), 1189);

check('exact name', findBook('John').name, 'John');
check('case insensitive', findBook('john').name, 'John');
check('abbreviation', findBook('Rev').name, 'Revelation');
check('numbered book', findBook('1 Corinthians').name, '1 Corinthians');
check('unknown book', findBook('Nephi'), null);
check('empty input', findBook(''), null);

check('chapter and verse', parseReference('John 3:16').ref, 'John 3:16');
check('verse range', parseReference('John 3:16-18').ref, 'John 3:16-18');
check('chapter only', parseReference('Psalms 23').ref, 'Psalms 23');
check('bare book defaults to chapter 1', parseReference('Jude').ref, 'Jude 1');
check('numbered book with chapter', parseReference('1 cor 13').ref, '1 Corinthians 13');
check('whitespace tolerated', parseReference('  John   3:16  ').ref, 'John 3:16');

// Chapter numbers beyond a book's length clamp rather than producing a
// reference that cannot resolve to any text.
check('chapter clamps to book length', parseReference('Jude 5').ref, 'Jude 1');
check('psalms upper bound', parseReference('Psalms 200').ref, 'Psalms 150');
check('unparseable input', parseReference('!!!'), null);

if (failures) {
  console.error(`\n${failures} failure(s)`);
  process.exit(1);
}
console.log('\nAll reference-parser tests passed.');
