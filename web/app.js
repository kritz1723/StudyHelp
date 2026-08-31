'use strict';

// The site is a static bundle: an index of every lemma, plus one JSON file per
// lemma fetched on demand. No backend, so it can be served from GitHub Pages.

const els = {
  q: document.getElementById('q'),
  hint: document.getElementById('hint'),
  results: document.getElementById('results'),
  detail: document.getElementById('detail'),
  about: document.getElementById('about'),
  sources: document.getElementById('sources'),
  stats: document.getElementById('stats'),
};

let INDEX = [];
let SOURCES = {};

const LANG = { hbo: 'Hebrew', arc: 'Aramaic', grc: 'Greek' };

function fold(text) {
  // Match the diacritic folding used at ingest, so searching "agape" finds
  // "agápē" and searching Greek text finds it regardless of accents.
  return (text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

async function boot() {
  try {
    const [index, stats] = await Promise.all([
      fetch('index.json').then((r) => r.json()),
      fetch('stats.json').then((r) => r.json()).catch(() => null),
    ]);
    INDEX = index.lemmas;
    SOURCES = index.sources;
    INDEX.forEach((entry) => {
      entry._key = fold(entry.xlit) + ' ' + fold(entry.lemma) + ' ' + fold(entry.gloss);
    });
    renderSources();
    if (stats) {
      els.stats.textContent =
        `${stats.hebrew_tokens.toLocaleString()} Hebrew and ${stats.greek_tokens.toLocaleString()} Greek ` +
        `tagged words, ${stats.lemmas.toLocaleString()} lemmas, ${stats.senses.toLocaleString()} attested senses, ` +
        `from ${stats.sources} registered sources.`;
    }
    els.hint.textContent = 'Search by English gloss, transliteration, original script, or Strong’s number.';
    routeFromHash();
  } catch (err) {
    els.hint.textContent = 'Could not load the index. The site may still be building.';
    console.error(err);
  }
}

function search(query) {
  const q = fold(query.trim());
  if (!q) return [];
  const strongs = q.toUpperCase().replace(/\s+/g, '');

  const scored = [];
  for (const entry of INDEX) {
    let score = null;
    if (entry.strongs && entry.strongs === strongs) score = 0;
    else if (fold(entry.xlit) === q || fold(entry.lemma) === q) score = 1;
    else if (fold(entry.xlit).startsWith(q)) score = 2;
    else if (entry._key.includes(q)) score = 3;
    if (score !== null) scored.push([score, -entry.n, entry]);
  }
  // Exact matches first, then by how often the word actually occurs: frequency
  // is the best proxy for "the one the reader probably means".
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return scored.slice(0, 60).map((row) => row[2]);
}

function renderResults(matches, query) {
  els.detail.hidden = true;
  els.about.hidden = false;
  if (!matches.length) {
    els.results.hidden = false;
    els.results.innerHTML = `<p class="hint">No lemma matches “${escapeHtml(query)}”.</p>`;
    return;
  }

  els.results.hidden = false;
  els.results.innerHTML =
    `<p class="hint">${matches.length} lemma${matches.length === 1 ? '' : 's'} match — ` +
    `pick one to see where it comes from.</p>` +
    matches.map((entry) => `
      <button class="result" data-slug="${escapeHtml(entry.slug)}">
        <span class="strongs">${escapeHtml(entry.strongs || '—')}</span>
        <span><span class="word">${escapeHtml(entry.lemma)}</span>
              <span class="xlit">${escapeHtml(entry.xlit || '')}</span></span>
        <span class="n">${entry.n.toLocaleString()}×</span>
        <span class="gloss">${escapeHtml(entry.gloss || '')}</span>
      </button>`).join('');
}

async function showLemma(slug) {
  const data = await fetch(`lemma/${encodeURIComponent(slug)}.json`).then((r) => r.json());

  const peak = data.distribution.length ? data.distribution[0][1] : 1;
  const dist = data.distribution.map(([book, count]) => `
    <span class="book">${escapeHtml(book)}</span>
    <span class="ct">${count}</span>
    <span class="track" style="width:${Math.max(2, (count / peak) * 100)}%"></span>`).join('');

  const senses = data.senses.length
    ? data.senses.map((s) => `
        <div class="sense">
          <p>${escapeHtml(s.gloss)}</p>
          ${s.attested ? '' : '<p class="inferred">inferred, not attested</p>'}
          <p class="provenance">source: ${escapeHtml(sourceName(s.source))}</p>
        </div>`).join('')
    : '<p class="hint">No lexicon entry is linked to this lemma yet.</p>';

  els.results.hidden = true;
  els.about.hidden = true;
  els.detail.hidden = false;
  els.detail.innerHTML = `
    <button class="back" id="back">&larr; back to results</button>
    <h2 class="headword">${escapeHtml(data.lemma)}</h2>
    <p class="meta">${escapeHtml(data.xlit || '')} · ${escapeHtml(data.strongs || 'no Strong’s number')}
       · ${LANG[data.lang] || data.lang} · ${data.count.toLocaleString()} occurrence${data.count === 1 ? '' : 's'}</p>

    <h3>First appearance</h3>
    ${data.first ? `
      <p class="first"><span class="ref">${escapeHtml(data.first.ref)}</span>
         &nbsp; ${escapeHtml(data.first.surface)}</p>
      <p class="provenance">canonical order · source: ${escapeHtml(sourceName(data.first.source))}</p>
      <p class="hint">Composition order gives a different answer and is contested; only
         canonical order is shown for now.</p>`
      : '<p class="hint">No tagged occurrence — known to a lexicon but unlinked in the corpus.</p>'}

    ${data.distribution.length ? `<h3>Where it clusters</h3><div class="dist">${dist}</div>` : ''}

    <h3>Attested meanings</h3>
    ${senses}`;

  document.getElementById('back').addEventListener('click', () => {
    location.hash = '';
    els.detail.hidden = true;
    els.about.hidden = false;
    if (els.q.value.trim()) renderResults(search(els.q.value), els.q.value);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function sourceName(id) {
  const src = SOURCES[id];
  return src ? `${src.name} [${id}]` : id;
}

function renderSources() {
  els.sources.innerHTML = Object.values(SOURCES)
    .filter((s) => s.name)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((s) => `<li>${s.url ? `<a href="${escapeHtml(s.url)}">${escapeHtml(s.name)}</a>` : escapeHtml(s.name)}
                 — ${escapeHtml(s.license)}${s.attribution ? ` · ${escapeHtml(s.attribution)}` : ''}</li>`)
    .join('');
}

function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

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
      els.about.hidden = false;
      return;
    }
    renderResults(search(value), value);
  }, 120);
});

els.results.addEventListener('click', (event) => {
  const button = event.target.closest('.result');
  if (button) location.hash = button.dataset.slug;
});

window.addEventListener('hashchange', routeFromHash);
boot();
