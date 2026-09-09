'use strict';

// A static bundle: an index of every word, one file per word, one per chapter.
// No backend, so it can be served from anywhere.

const el = (id) => document.getElementById(id);
const els = {
  q: el('q'), hint: el('hint'), settings: el('settings'),
  sort: el('sort'), tradition: el('tradition'), canon: el('canon'), version: el('version'),
  results: el('results'), detail: el('detail'), reader: el('reader'),
  welcome: el('welcome'), featured: el('featured'), sources: el('sources'), stats: el('stats'),
};

let INDEX = [], SOURCES = {}, VERSIONS = [], CANONS = {}, BOOKS = [];
let lastMatches = [];

const LANG = { hbo: 'Hebrew', arc: 'Aramaic', grc: 'Greek', en: 'English', la: 'Latin', zh: 'Mandarin' };
const GENRE = {
  law: 'Law', narrative: 'Narrative', wisdom: 'Wisdom and poetry', prophecy: 'Prophecy',
  gospel: 'Gospels', history: 'Early church', epistle: 'Letters', apocalyptic: 'Apocalyptic',
};

// Words chosen because each one teaches something different: a chain across
// languages, a word split between traditions, a cultic term, a covenant word.
const FEATURED = [
  { slug: 'G2435', why: 'Follows the chain from the mercy seat to “propitiation”.' },
  { slug: 'G26', why: 'One Greek word, six different Mandarin renderings.' },
  { slug: 'H2617', why: 'A covenant word English has never settled on.' },
  { slug: 'H2403', why: 'A word that gathers in the sacrificial legislation.' },
  { slug: 'H7307', why: 'Breath, wind and spirit, all in one word.' },
  { slug: 'G3056', why: 'Word, reason, account — a term that widened.' },
];

const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function fold(t) { return (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }

// -- appearance ------------------------------------------------------------

function setTheme(name) {
  document.documentElement.dataset.theme = name;
  document.querySelectorAll('[data-set-theme]').forEach((b) =>
    b.classList.toggle('on', b.dataset.setTheme === name));
  store.set('theme', name);
}
document.querySelectorAll('[data-set-theme]').forEach((b) =>
  b.addEventListener('click', () => setTheme(b.dataset.setTheme)));
setTheme(store.get('theme', 'illuminated'));

// -- dates -----------------------------------------------------------------

const year = (v) => (v == null ? '' : v < 0 ? `${Math.abs(v)} BC` : `AD ${v}`);

function span(range) {
  if (!range) return '';
  const [a, b] = range;
  if (a === b) return `c. ${year(a)}`;
  if (a < 0 && b < 0) return `c. ${Math.abs(a)}–${Math.abs(b)} BC`;
  if (a > 0 && b > 0) return `c. AD ${a}–${b}`;
  return `c. ${year(a)} – ${year(b)}`;
}
const TRADITION = { traditional: 'Traditional dating', critical: 'Critical dating' };

// -- references ------------------------------------------------------------

// Reference parsing is driven by the book list the site ships, so it covers
// every canon rather than a hardcoded sixty-six.
function parseReference(text) {
  const raw = String(text || '').trim();
  const m = raw.match(/^\s*((?:[1-4]\s*)?[A-Za-z][A-Za-z\s]*?)\s*(\d+)?(?::\s*(\d+))?\s*$/);
  if (!m) return null;
  const book = findBook(m[1]);
  if (!book) return null;
  let chapter = m[2] ? parseInt(m[2], 10) : 1;
  if (chapter < 1) chapter = 1;
  if (chapter > book.chapters) chapter = book.chapters;
  return { book, chapter, verse: m[3] ? parseInt(m[3], 10) : null };
}

function findBook(input) {
  const q = fold(String(input || '').trim()).replace(/\s+/g, ' ');
  if (!q) return null;
  const exact = BOOKS.find((b) => fold(b.name) === q || fold(b.abbr) === q);
  if (exact) return exact;
  const starts = BOOKS.filter((b) => fold(b.name).startsWith(q) || fold(b.abbr).startsWith(q));
  return starts.length ? starts[0] : null;
}

// -- boot ------------------------------------------------------------------

async function boot() {
  try {
    const [index, stats, canons, books] = await Promise.all([
      fetch('index.json').then((r) => r.json()),
      fetch('stats.json').then((r) => r.json()).catch(() => null),
      fetch('canons.json').then((r) => r.json()).catch(() => ({})),
      fetch('books.json').then((r) => r.json()).catch(() => ({ books: [] })),
    ]);
    INDEX = index.lemmas; SOURCES = index.sources; VERSIONS = index.versions || [];
    CANONS = canons; BOOKS = books.books || [];
    INDEX.forEach((e) => { e._key = fold(e.xlit) + ' ' + fold(e.lemma) + ' ' + fold(e.terms || e.gloss); });

    els.version.innerHTML = VERSIONS
      .filter((v) => v.language !== 'zh')
      .map((v) => `<option value="${esc(v.id)}">${esc(v.name)}${v.year ? ` (${v.year})` : ''}</option>`)
      .join('');
    els.version.value = store.get('version', 'kjv');
    els.tradition.value = store.get('tradition', 'traditional');
    els.canon.value = store.get('canon', 'protestant');

    renderSources();
    renderFeatured();
    if (stats) {
      els.stats.textContent =
        `${stats.hebrew_tokens.toLocaleString()} Hebrew and ${stats.greek_tokens.toLocaleString()} Greek ` +
        `words traced, ${(stats.septuagint_links || 0).toLocaleString()} of them followed into the ` +
        `Septuagint; ${stats.lemmas.toLocaleString()} entries, ${stats.senses.toLocaleString()} recorded ` +
        `meanings, ${(stats.renderings || 0).toLocaleString()} verses across ${stats.versions || 0} versions.`;
    }
    els.hint.textContent = 'Type a reference like John 3:16, or a word in English, transliteration or the original script.';
    routeFromHash();
  } catch (err) {
    els.hint.textContent = 'The index could not be loaded. The site may still be building.';
    console.error(err);
  }
}

function renderFeatured() {
  const byslug = new Map(INDEX.map((e) => [e.slug, e]));
  els.featured.innerHTML = FEATURED
    .map((f) => [f, byslug.get(f.slug)])
    .filter(([, entry]) => entry)
    .map(([f, entry]) => `
      <button class="card" data-slug="${esc(entry.slug)}">
        <span class="w">${esc(entry.lemma)}</span>
        <span class="x">${esc(entry.xlit || '')}</span>
        <span class="why">${esc(f.why)}</span>
      </button>`).join('');
}

// -- search ----------------------------------------------------------------

function search(query) {
  const q = fold(query.trim());
  if (!q) return [];
  const strongs = q.toUpperCase().replace(/\s+/g, '');
  const scored = [];
  for (const e of INDEX) {
    let score = null;
    if (e.strongs && e.strongs === strongs) score = 0;
    else if (fold(e.xlit) === q || fold(e.lemma) === q) score = 1;
    else if (fold(e.xlit).startsWith(q)) score = 2;
    else if (new RegExp(`\\b${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`).test(e._key)) score = 3;
    else if (e._key.includes(q)) score = 4;
    if (score !== null) scored.push([score, -e.n, e]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return scored.slice(0, 80).map((r) => r[2]);
}

function applySort(matches) {
  const mode = els.sort.value;
  const key = els.tradition.value === 'critical' ? 'yc' : 'yt';
  const list = matches.slice();
  if (mode === 'frequency') list.sort((a, b) => b.n - a.n);
  else if (mode === 'earliest' || mode === 'latest') {
    list.sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return mode === 'earliest' ? x - y : y - x;
    });
  }
  return list;
}

function show(section) {
  for (const name of ['results', 'detail', 'reader', 'welcome']) {
    els[name].hidden = name !== section;
  }
}

function renderResults(matches, query) {
  lastMatches = matches;
  show('results');
  if (!matches.length) {
    els.results.innerHTML = `<p class="hint">Nothing matches “${esc(query)}”.</p>`;
    return;
  }
  const key = els.tradition.value === 'critical' ? 'yc' : 'yt';
  const sorted = applySort(matches);
  const ordered = els.sort.value === 'earliest' || els.sort.value === 'latest'
    ? ` Ordered by the earliest possible date of the book each word first appears in.` : '';

  els.results.innerHTML =
    `<p class="hint">${sorted.length} entr${sorted.length === 1 ? 'y' : 'ies'}.${ordered}</p>` +
    sorted.map((e) => `
      <button class="result" data-slug="${esc(e.slug)}">
        <span><span class="word">${esc(e.lemma)}</span><span class="xlit">${esc(e.xlit || '')}</span>
          <span class="badge">${esc(LANG[e.lang] || e.lang)}</span></span>
        <span class="when">${e[key] != null ? esc(year(e[key])) : ''} · ${e.n.toLocaleString()}×</span>
        <span class="gloss">${esc(e.gloss || '')}</span>
      </button>`).join('');
}

// -- the reader ------------------------------------------------------------

async function showChapter(bookName, chapter, focusVerse) {
  const slug = `${bookName}.${chapter}`.replace(/ /g, '_');
  let data;
  try {
    data = await fetch(`chapter/${encodeURIComponent(slug)}.json`).then((r) => r.json());
  } catch {
    show('results');
    els.results.innerHTML = `<p class="hint">No text is loaded for ${esc(bookName)} ${chapter}.</p>`;
    return;
  }

  const book = BOOKS.find((b) => b.name === bookName);
  const version = els.version.value;
  const versionName = (VERSIONS.find((v) => v.id === version) || {}).name || version;

  const verses = data.verses
    .filter((v) => !focusVerse || v.v === focusVerse)
    .map((v) => {
      const text = v.t[version] || v.t.kjv || Object.values(v.t)[0] || '';
      const words = (v.w || []).map((w) => w.k
        ? `<button class="iw" data-slug="${esc(w.k)}">
             <span class="o">${esc(w.s)}</span><span class="m">${esc(w.g || '')}</span></button>`
        : `<span class="iw"><span class="o">${esc(w.s)}</span></span>`).join('');
      return `
        <div class="verse-row">
          <span class="verse-no">${bookName} ${chapter}:${v.v}</span>
          <p class="verse-text">${esc(text)}</p>
          ${words ? `<div class="interlinear">${words}</div>` : ''}
        </div>`;
    }).join('');

  show('reader');
  els.reader.innerHTML = `
    <h2>${esc(bookName)} ${chapter}${focusVerse ? `:${focusVerse}` : ''}</h2>
    <p class="hint">Reading ${esc(versionName)}. Every word below the verse is the original
       behind it — click one to trace it. ${focusVerse
         ? `<button class="more" id="whole-chapter">Show the whole chapter</button>` : ''}</p>
    ${verses || '<p class="hint">This chapter has no text loaded.</p>'}
    <div class="chapter-nav">
      ${chapter > 1 ? `<button data-goto="${esc(bookName)}|${chapter - 1}">← ${esc(bookName)} ${chapter - 1}</button>` : ''}
      ${book && chapter < book.chapters ? `<button data-goto="${esc(bookName)}|${chapter + 1}">${esc(bookName)} ${chapter + 1} →</button>` : ''}
    </div>`;

  const whole = el('whole-chapter');
  if (whole) whole.addEventListener('click', () => { location.hash = `${slug}`; });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// -- word detail -----------------------------------------------------------

function timeline(dates) {
  if (!dates) return '';
  const spans = Object.entries(dates);
  const all = spans.flatMap(([, r]) => r);
  const lo = Math.min(...all, -100), hi = Math.max(...all, 100);
  const pad = Math.max(50, (hi - lo) * 0.08);
  const from = lo - pad, to = hi + pad;
  const pct = (v) => ((v - from) / (to - from)) * 100;

  return `
    <div class="timeline">
      <div class="tl-track">
        ${spans.map(([name, [a, b]], i) => `
          <div class="tl-span ${esc(name)}" style="left:${pct(a)}%;width:${Math.max(1.5, pct(b) - pct(a))}%;top:${i * 2 + 0.5}rem"></div>
          <span class="tl-label" style="left:${Math.min(pct(a), 72)}%;top:${i * 2 + 1.1}rem">${esc(TRADITION[name] || name)}, ${esc(span([a, b]))}</span>
        `).join('')}
      </div>
      <div class="tl-axis"><span>${esc(year(Math.round(from)))}</span><span>${esc(year(Math.round(to)))}</span></div>
    </div>`;
}

function shareBars(entries, limit) {
  const total = entries.reduce((n, [, c]) => n + c, 0) || 1;
  return entries.slice(0, limit).map(([text, count]) => `
    <span class="t">${esc(text)}</span>
    <span class="b" style="width:${Math.max(1, (count / total) * 100)}%"></span>
    <span class="p">${Math.round((count / total) * 100)}%</span>`).join('');
}

async function showLemma(slug) {
  const data = await fetch(`lemma/${encodeURIComponent(slug)}.json`).then((r) => r.json());

  const inCanon = new Set(CANONS[els.canon.value] || []);
  const distribution = inCanon.size
    ? data.distribution.filter(([b]) => inCanon.has(b)) : data.distribution;
  const hiddenBooks = data.distribution.length - distribution.length;

  const peak = distribution.length ? distribution[0][1] : 1;
  const bar = ([book, count]) => `
    <span class="book">${esc(book)}</span><span class="ct">${count}</span>
    <span class="track" style="width:${Math.max(2, (count / peak) * 100)}%"></span>`;
  const topBooks = distribution.slice(0, 6).map(bar).join('');
  const restBooks = distribution.slice(6).map(bar).join('');

  const genreTotal = (data.by_genre || []).reduce((n, [, c]) => n + c, 0) || 1;
  const genreChips = (data.by_genre || []).map(([g, c]) =>
    `<span class="genre"><b>${esc(GENRE[g] || g)}</b> ${Math.round((c / genreTotal) * 100)}%</span>`).join('');

  // The chain, as the spine of the page.
  const toGreek = data.to_greek || [], fromHebrew = data.from_hebrew || [];
  const englishGloss = (data.renderings || {})['cherith-en'] || [];
  const chain = (toGreek.length || fromHebrew.length || englishGloss.length) ? `
    <h3>The chain</h3>
    <div class="spine">
      ${data.lang !== 'grc' ? `<div class="link"><span class="stage">Hebrew</span>
        <span class="body">${esc(data.lemma)} <span class="sep">·</span>
        <span class="xlit">${esc(data.xlit || '')}</span></span></div>` : ''}
      ${toGreek.length ? `<div class="link"><span class="stage">Septuagint</span>
        <span class="body">${toGreek.slice(0, 4).map(([t, c]) =>
          `${esc(t)} <span class="sep">${c}</span>`).join(' ')}</span></div>` : ''}
      ${fromHebrew.length ? `<div class="link"><span class="stage">Stands for</span>
        <span class="body">${fromHebrew.slice(0, 4).map(([h, x, c]) =>
          `${esc(h)} <span class="sep">${esc(x || '')} ${c}</span>`).join(' ')}</span></div>` : ''}
      ${data.lang === 'grc' ? `<div class="link"><span class="stage">Greek</span>
        <span class="body">${esc(data.lemma)} <span class="sep">·</span>
        <span class="xlit">${esc(data.xlit || '')}</span></span></div>` : ''}
      ${englishGloss.length ? `<div class="link"><span class="stage">English</span>
        <span class="body">${englishGloss.slice(0, 4).map(([t]) => esc(t)).join(', ')}</span></div>` : ''}
    </div>
    <p class="note">Read downward: this is the route the meaning travelled, not a definition.</p>` : '';

  const senseGroups = Object.entries(data.senses || {});
  const senses = senseGroups.length
    ? senseGroups.map(([source, entries]) => `
        <div class="sense">
          <p class="said-by">${esc(said(source))}</p>
          ${entries.slice(0, 6).map((e) => `<p>${esc(e.gloss)}</p>`).join('')}
        </div>`).join('') +
      (senseGroups.length > 1
        ? `<p class="note">Two dictionaries side by side. Where they differ the difference is
             left standing — deciding between them is yours, not this page's.</p>`
        : `<p class="note">Only one dictionary covers this word, so there is no second opinion
             to set against it.</p>`)
    : '<p class="hint">No dictionary entry is linked to this word yet.</p>';

  const written = data.earliest_written || {};
  const tradition = els.tradition.value;
  const writtenNote = written[tradition]
    ? `<p class="note">Earliest by composition order — the book most likely written first —
         is <strong>${esc(written[tradition][0])}</strong>, ${esc(year(written[tradition][1]))}.
         Canonical order and composition order give different answers, and both are shown
         rather than one being chosen for you.</p>` : '';

  const first = data.first;
  show('detail');
  els.detail.innerHTML = `
    <button class="back" id="back">← back</button>
    <h2 class="headword">${esc(data.lemma)}</h2>
    <p class="meta">${esc(data.xlit || '')} · ${esc(LANG[data.lang] || data.lang)} ·
      ${data.count.toLocaleString()} occurrence${data.count === 1 ? '' : 's'}
      ${data.hapax ? '<span class="badge">appears once</span>' : ''}</p>

    ${chain}

    <h3>Where it first appears</h3>
    ${first ? `
      <div class="origin">
        <div><span class="ref">${esc(first.ref)}</span><span class="surface">${esc(first.surface)}</span></div>
        ${first.dates ? timeline(first.dates) : ''}
        ${first.dates ? `<p class="note">${esc(TRADITION.traditional)}: ${esc(span(first.dates.traditional))}
           · ${esc(TRADITION.critical)}: ${esc(span(first.dates.critical))}. The year a book was
           written is genuinely disputed; both are ranges, not settled facts.</p>` : ''}
        ${writtenNote}
        <p class="note">Attested by ${esc(said(first.source))}.
          <button class="more" data-read="${esc(first.book)}|${first.chapter}|${first.verse}">Read the verse →</button></p>
      </div>` : '<p class="hint">Known to a dictionary, but with no tagged occurrence in the text.</p>'}

    ${distribution.length ? `
      <h3>Where it gathers</h3>
      ${genreChips ? `<div class="genres">${genreChips}</div>` : ''}
      <div class="dist">${topBooks}</div>
      ${restBooks ? `<div class="dist" id="rest" hidden>${restBooks}</div>
        <button class="more" id="show-rest">Show all ${distribution.length} books</button>` : ''}
      ${hiddenBooks > 0 ? `<p class="note">${hiddenBooks} further book${hiddenBooks === 1 ? '' : 's'}
         outside the ${esc(els.canon.value)} canon ${hiddenBooks === 1 ? 'is' : 'are'} not shown.</p>` : ''}
      ${data.lang !== 'en' ? `<p class="note">Counts come from the tagged Hebrew and Greek, which
         cover the 66-book canon only.</p>` : ''}` : ''}

    ${Object.keys(data.renderings || {}).length ? `<h3>What it became</h3>` +
      Object.entries(data.renderings).map(([id, entries]) => {
        const v = VERSIONS.find((x) => x.id === id);
        return `<div class="rendered"><p class="which">${esc(v ? v.name : id)}</p>
          <div class="share">${shareBars(entries, 8)}</div></div>`;
      }).join('') +
      `<p class="note">One word in the original, and the share of times each word was chosen
         for it. A word that collapses to a single choice in one language and spreads across
         many in another is telling you about the translation, not the word.</p>` : ''}

    <h3>What it has meant</h3>
    ${senses}`;

  el('back').addEventListener('click', goBack);
  const showRest = el('show-rest');
  if (showRest) showRest.addEventListener('click', () => {
    el('rest').hidden = false; showRest.remove();
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goBack() {
  location.hash = '';
  if (els.q.value.trim()) renderResults(search(els.q.value), els.q.value);
  else show('welcome');
}

function said(id) { const s = SOURCES[id]; return s ? s.name : 'an unrecorded source'; }

function renderSources() {
  els.sources.innerHTML = Object.values(SOURCES).filter((s) => s.name)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((s) => `<li>${s.url ? `<a href="${esc(s.url)}">${esc(s.name)}</a>` : esc(s.name)}
       — ${esc(s.license)}${s.attribution ? ` · ${esc(s.attribution)}` : ''}</li>`).join('');
}

// -- routing ---------------------------------------------------------------

function routeFromHash() {
  const raw = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (!raw) { show('welcome'); return; }
  const parts = raw.split('.');
  // A reference route looks like Book.chapter[.verse]; anything else is a word.
  if (parts.length >= 2 && /^\d+$/.test(parts[1])) {
    const bookName = parts[0].replace(/_/g, ' ');
    showChapter(bookName, parseInt(parts[1], 10),
      parts[2] && /^\d+$/.test(parts[2]) ? parseInt(parts[2], 10) : null);
    return;
  }
  showLemma(raw).catch(() => { location.hash = ''; });
}

let timer;
els.q.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const value = els.q.value.trim();
    if (!value) { show('welcome'); return; }
    // A reference wins over a word search: someone typing "John 3:16" wants to read.
    const ref = parseReference(value);
    if (ref && /\d/.test(value)) {
      location.hash = `${ref.book.name.replace(/ /g, '_')}.${ref.chapter}${ref.verse ? `.${ref.verse}` : ''}`;
      return;
    }
    renderResults(search(value), value);
  }, 140);
});

document.addEventListener('click', (event) => {
  const word = event.target.closest('[data-slug]');
  if (word) { location.hash = word.dataset.slug; return; }
  const read = event.target.closest('[data-read]');
  if (read) {
    const [book, chapter, verse] = read.dataset.read.split('|');
    location.hash = `${book.replace(/ /g, '_')}.${chapter}.${verse}`;
    return;
  }
  const goto = event.target.closest('[data-goto]');
  if (goto) {
    const [book, chapter] = goto.dataset.goto.split('|');
    location.hash = `${book.replace(/ /g, '_')}.${chapter}`;
  }
});

el('home').addEventListener('click', (e) => {
  e.preventDefault(); els.q.value = ''; location.hash = ''; show('welcome');
});

for (const [control, key] of [[els.sort, null], [els.tradition, 'tradition'],
                              [els.canon, 'canon'], [els.version, 'version']]) {
  control.addEventListener('change', () => {
    if (key) store.set(key, control.value);
    if (!els.detail.hidden || !els.reader.hidden) routeFromHash();
    else if (lastMatches.length) renderResults(lastMatches, els.q.value);
  });
}

window.addEventListener('hashchange', routeFromHash);
boot();
