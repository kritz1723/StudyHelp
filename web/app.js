'use strict';

// Static bundle: an index of every word, one file per word, one file per verse
// that any word first appears in. No backend.

const els = {
  q: document.getElementById('q'),
  hint: document.getElementById('hint'),
  sorter: document.getElementById('sorter'),
  sort: document.getElementById('sort'),
  tradition: document.getElementById('tradition'),
  canon: document.getElementById('canon'),
  results: document.getElementById('results'),
  detail: document.getElementById('detail'),
  about: document.getElementById('about'),
  sources: document.getElementById('sources'),
  stats: document.getElementById('stats'),
};

let INDEX = [];
let SOURCES = {};
let VERSIONS = [];
let CANONS = {};
let lastMatches = [];

const LANG = { hbo: 'Hebrew', arc: 'Aramaic', grc: 'Greek', en: 'English', la: 'Latin' };

const store = {
  get(key, fallback) {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
};

// -- appearance ------------------------------------------------------------

function setTheme(name) {
  document.documentElement.dataset.theme = name;
  document.querySelectorAll('[data-set-theme]').forEach((b) => {
    b.classList.toggle('on', b.dataset.setTheme === name);
  });
  store.set('theme', name);
}
document.querySelectorAll('[data-set-theme]').forEach((b) => {
  b.addEventListener('click', () => setTheme(b.dataset.setTheme));
});
setTheme(store.get('theme', 'illuminated'));

// -- dates -----------------------------------------------------------------

function year(value) {
  if (value == null) return '';
  return value < 0 ? `${Math.abs(value)} BC` : `AD ${value}`;
}

function span(range) {
  if (!range) return '';
  const [from, to] = range;
  if (from === to) return `c. ${year(from)}`;
  // Keep the era label once, on the end that needs it.
  if (from < 0 && to < 0) return `c. ${Math.abs(from)}–${Math.abs(to)} BC`;
  if (from > 0 && to > 0) return `c. AD ${from}–${to}`;
  return `c. ${year(from)} – ${year(to)}`;
}

const TRADITION_LABEL = { traditional: 'Traditional dating', critical: 'Critical dating' };

// -- boot ------------------------------------------------------------------

async function boot() {
  try {
    const [index, stats, canons] = await Promise.all([
      fetch('index.json').then((r) => r.json()),
      fetch('stats.json').then((r) => r.json()).catch(() => null),
      fetch('canons.json').then((r) => r.json()).catch(() => ({})),
    ]);
    CANONS = canons;
    INDEX = index.lemmas;
    SOURCES = index.sources;
    VERSIONS = index.versions || [];
    INDEX.forEach((e) => {
      e._key = fold(e.xlit) + ' ' + fold(e.lemma) + ' ' + fold(e.terms || e.gloss);
    });

    renderSources();
    if (stats) {
      els.stats.textContent =
        `${stats.hebrew_tokens.toLocaleString()} Hebrew and ${stats.greek_tokens.toLocaleString()} Greek ` +
        `words traced, ${stats.lemmas.toLocaleString()} entries, ${stats.senses.toLocaleString()} recorded meanings, ` +
        `and ${(stats.renderings || 0).toLocaleString()} verses across ${stats.versions || 0} translations.`;
    }
    els.hint.textContent = 'Search in English, in transliteration, or in the original script.';
    els.tradition.value = store.get('tradition', 'traditional');
    els.canon.value = store.get('canon', 'protestant');
    routeFromHash();
  } catch (err) {
    els.hint.textContent = 'The index could not be loaded. The site may still be building.';
    console.error(err);
  }
}

function fold(text) {
  return (text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
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
    // A range cannot be ordered directly. The declared rule is: order by the
    // EARLIEST bound of the chosen dating tradition. Entries with no dated
    // appearance sort last either way, rather than pretending to a position.
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

function renderResults(matches, query) {
  lastMatches = matches;
  els.detail.hidden = true;
  els.about.hidden = false;
  els.results.hidden = false;
  els.sorter.hidden = matches.length === 0;

  if (!matches.length) {
    els.results.innerHTML = `<p class="hint">Nothing matches “${esc(query)}”.</p>`;
    return;
  }

  const key = els.tradition.value === 'critical' ? 'yc' : 'yt';
  const sorted = applySort(matches);
  const ruleNote = els.sort.value === 'earliest' || els.sort.value === 'latest'
    ? ` Ordered by the earliest possible date of the book each word first appears in,
        under ${esc(TRADITION_LABEL[els.tradition.value].toLowerCase())}.`
    : '';

  els.results.innerHTML =
    `<p class="hint">${sorted.length} entr${sorted.length === 1 ? 'y' : 'ies'}.${ruleNote}</p>` +
    sorted.map((e) => `
      <button class="result" data-slug="${esc(e.slug)}">
        <span><span class="word">${esc(e.lemma)}</span><span class="xlit">${esc(e.xlit || '')}</span></span>
        <span class="when">${e[key] != null ? esc(year(e[key])) : ''} · ${e.n.toLocaleString()}×</span>
        <span class="gloss">${esc(e.gloss || '')}</span>
      </button>`).join('');
}

// -- detail ----------------------------------------------------------------

async function showLemma(slug) {
  const data = await fetch(`lemma/${encodeURIComponent(slug)}.json`).then((r) => r.json());

  const inCanon = new Set(CANONS[els.canon.value] || []);
  const distribution = inCanon.size
    ? data.distribution.filter(([book]) => inCanon.has(book))
    : data.distribution;
  const hidden = data.distribution.length - distribution.length;

  const peak = distribution.length ? distribution[0][1] : 1;
  const dist = distribution.map(([book, count]) => `
    <span class="book">${esc(book)}</span>
    <span class="ct">${count}</span>
    <span class="track" style="width:${Math.max(2, (count / peak) * 100)}%"></span>`).join('');

  const senseGroups = Object.entries(data.senses || {});
  const senses = senseGroups.length
    ? senseGroups.map(([source, entries]) => `
        <div class="sense">
          <p class="said-by">${esc(said(source))}</p>
          ${entries.map((e) => `<p>${esc(e.gloss)}</p>
            ${e.attested ? '' : '<p class="inferred">a reading inferred, not directly attested</p>'}`).join('')}
        </div>`).join('') +
      (senseGroups.length > 1
        ? `<p class="note">Two dictionaries, shown side by side. Where they differ, the
             difference is left standing rather than resolved — deciding between them is
             yours, not this page's.</p>`
        : `<p class="note">Only one dictionary covers this word here, so there is no second
             opinion to set against it.</p>`)
    : '<p class="hint">No dictionary entry is linked to this word yet.</p>';

  // The transmission chain: Hebrew → Septuagint → Greek → English.
  const toGreek = data.to_greek || [];
  const fromHebrew = data.from_hebrew || [];
  const chain = (toGreek.length || fromHebrew.length) ? `
    <h3>Through the Septuagint</h3>
    ${toGreek.length ? `
      <p class="note">When the Hebrew scriptures were translated into Greek, around the
         third to second century BC, this word was rendered:</p>
      <div class="chips">${toGreek.map(([text, count]) => `
        <span class="chip"><span class="w">${esc(text)}</span>
          <span class="c">${count}</span></span>`).join('')}</div>` : ''}
    ${fromHebrew.length ? `
      <p class="note">This Greek word stands in the Septuagint for these Hebrew words —
         the route by which Hebrew meaning reached the Greek of the New Testament:</p>
      <div class="chips">${fromHebrew.map(([hebrew, xlit, count]) => `
        <span class="chip"><span class="w">${esc(hebrew)}</span>
          <span class="c">${esc(xlit || '')} ${count}</span></span>`).join('')}</div>` : ''}
    <p class="note">According to ${esc(said('macula-hebrew'))}.</p>` : '';

  let origin = '<p class="hint">This word is known to a dictionary but has no tagged occurrence in the text.</p>';
  if (data.first) {
    const d = data.first.dates;
    origin = `
      <div class="origin">
        <div><span class="ref">${esc(data.first.ref)}</span><span class="surface">${esc(data.first.surface)}</span></div>
        ${d ? `<div class="years">
          <div class="row"><span class="who">${esc(TRADITION_LABEL.traditional)}</span>
               <span class="span">${esc(span(d.traditional))}</span></div>
          <div class="row"><span class="who">${esc(TRADITION_LABEL.critical)}</span>
               <span class="span">${esc(span(d.critical))}</span></div>
        </div>
        <p class="note">Two datings are shown because the year a book was written is
           genuinely disputed. Both are approximate ranges, not settled facts.</p>` : ''}
        <p class="note">Earliest in the order the books are arranged, according to
           ${esc(said(data.first.source))}.</p>
      </div>`;
  }

  els.results.hidden = true;
  els.sorter.hidden = true;
  els.about.hidden = true;
  els.detail.hidden = false;
  const renderings = data.renderings || {};
  const renderedIn = Object.keys(renderings)
    .map((id) => {
      const version = VERSIONS.find((v) => v.id === id);
      const entries = renderings[id];
      const total = entries.reduce((n, [, c]) => n + c, 0) || 1;
      return `
        <div class="rendered">
          <p class="which">${esc(version ? version.name : id)}</p>
          <div class="chips">${entries.map(([text, count]) => `
            <span class="chip"><span class="w">${esc(text)}</span>
              <span class="c">${count}</span></span>`).join('')}</div>
          ${entries.length > 1 ? `<p class="note">${entries.length} different
             rendering${entries.length === 1 ? '' : 's'}; the most common covers
             ${Math.round((entries[0][1] / total) * 100)}% of its uses.</p>` : ''}
        </div>`;
    }).join('');

  els.detail.innerHTML = `
    <button class="back" id="back">← back</button>
    <h2 class="headword">${esc(data.lemma)}</h2>
    <p class="meta">${esc(data.xlit || '')} · ${esc(LANG[data.lang] || data.lang)} ·
       ${data.count.toLocaleString()} occurrence${data.count === 1 ? '' : 's'}</p>

    <h3>Where it first appears</h3>
    ${origin}
    <div class="verse" id="verse" ${data.first ? '' : 'hidden'}>
      <div class="picker">
        <label for="version">Read it in</label>
        <select id="version"></select>
      </div>
      <p class="text" id="verse-text"></p>
    </div>

    ${distribution.length ? `<h3>Where it gathers</h3><div class="dist">${dist}</div>` : ''}
    ${hidden > 0 ? `<p class="note">${hidden} further book${hidden === 1 ? '' : 's'}
       carrying this word ${hidden === 1 ? 'is' : 'are'} outside the
       ${esc(els.canon.value)} canon and not shown.</p>` : ''}
    ${data.lang !== 'en' ? `<p class="note">Counts come from the tagged Hebrew and Greek,
       which cover the 66-book canon only. The deuterocanonical books can be read here
       but are not yet counted.</p>` : ''}

    ${chain}

    ${renderedIn ? `<h3>What it became</h3>${renderedIn}
       <p class="note">One word in the original, and the words chosen for it.
          Where a single original word splits into many, the choice is the
          translator's — which is exactly what a word study is for.</p>` : ''}

    <h3>What it has meant</h3>
    ${senses}`;

  document.getElementById('back').addEventListener('click', goBack);
  if (data.first) setupVerse(data.first);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Translation is optional: "None" is a real choice and the default is remembered.
function setupVerse(first) {
  const select = document.getElementById('version');
  const target = document.getElementById('verse-text');
  const slug = `${first.book}.${first.chapter}.${first.verse}`.replace(/ /g, '_');

  select.innerHTML = '<option value="">None — original only</option>' +
    VERSIONS.map((v) => `<option value="${esc(v.id)}">${esc(v.name)}${v.year ? ` (${v.year})` : ''} · ${esc(LANG[v.language] || v.language)}</option>`).join('');
  select.value = store.get('version', 'kjv');

  const render = async () => {
    store.set('version', select.value);
    if (!select.value) { target.textContent = ''; return; }
    try {
      const texts = await fetch(`verse/${encodeURIComponent(slug)}.json`).then((r) => r.json());
      const text = texts[select.value];
      const version = VERSIONS.find((v) => v.id === select.value);
      target.innerHTML = text
        ? `${esc(text)}<br><span class="which">${esc(version ? version.name : select.value)}${version && version.from ? `, translated from the ${esc(version.from)}` : ''}` +
          `${version && version.caution ? ` — ${esc(version.caution)}` : ''}</span>`
        : '<span class="which">This translation does not carry this verse.</span>';
    } catch {
      target.innerHTML = '<span class="which">That verse is not available here.</span>';
    }
  };
  select.addEventListener('change', render);
  render();
}

function goBack() {
  location.hash = '';
  els.detail.hidden = true;
  els.about.hidden = false;
  if (els.q.value.trim()) renderResults(search(els.q.value), els.q.value);
}

// -- attribution -----------------------------------------------------------

// Readers get the name of the work, never our internal identifier for it.
function said(id) {
  const src = SOURCES[id];
  return src ? src.name : 'an unrecorded source';
}

function renderSources() {
  els.sources.innerHTML = Object.values(SOURCES)
    .filter((s) => s.name)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((s) => `<li>${s.url ? `<a href="${esc(s.url)}">${esc(s.name)}</a>` : esc(s.name)}
                 — ${esc(s.license)}${s.attribution ? ` · ${esc(s.attribution)}` : ''}</li>`)
    .join('');
}

function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// -- wiring ----------------------------------------------------------------

function routeFromHash() {
  const slug = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (slug) showLemma(slug).catch(() => { location.hash = ''; });
}

let timer;
els.q.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const value = els.q.value;
    if (!value.trim()) {
      els.results.hidden = true;
      els.detail.hidden = true;
      els.sorter.hidden = true;
      els.about.hidden = false;
      return;
    }
    renderResults(search(value), value);
  }, 120);
});

els.sort.addEventListener('change', () => {
  if (lastMatches.length) renderResults(lastMatches, els.q.value);
});
els.canon.addEventListener('change', () => {
  store.set('canon', els.canon.value);
  routeFromHash();
});
els.tradition.addEventListener('change', () => {
  store.set('tradition', els.tradition.value);
  if (lastMatches.length) renderResults(lastMatches, els.q.value);
});

els.results.addEventListener('click', (event) => {
  const button = event.target.closest('.result');
  if (button) location.hash = button.dataset.slug;
});

window.addEventListener('hashchange', routeFromHash);
boot();
