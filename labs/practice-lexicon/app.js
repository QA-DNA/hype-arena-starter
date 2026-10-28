const payload = JSON.parse(document.querySelector('#lab-data').textContent);
const model = createModel(payload.rows, payload.lexicon);
const $ = selector => document.querySelector(selector);
const esc = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const number = value => value.toLocaleString('ro-RO');
const dateLabel = date => new Intl.DateTimeFormat('ro-RO', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(date + 'T00:00:00Z'));
const badge = label => `<span class="badge ${label}">${label}</span>`;
const palette = { true: '#4d9b85', false: '#ce8975', unsure: '#c7a258' };
const pageSize = 20;
const state = { view: 'graph', filters: {}, focus: 'Hooly', graphMode: 'relations', all: false, scope: null, selected: null, page: 0, sort: 'asc', correlationLimit: 18, variationsOnly: true, zoom: 1, panX: 0, panY: 0, relatedLimit: 8 };
let filtered = [], shown = [], activeEdges = [], dragged = false;

function getRows() {
  filtered = filterRows(model, state.filters);
  shown = filtered.filter(row => !state.scope || (state.scope.type === 'pair' ? row.facts.some(f => f.key === state.scope.key) : state.scope.ids.includes(row.id)));
  if (state.sort === 'desc') shown = [...shown].reverse();
  if (!shown.some(row => row.id === state.selected)) state.selected = shown[0]?.id || null;
  state.page = Math.min(state.page, Math.max(0, Math.ceil(shown.length / pageSize) - 1));
}

function renderStats() {
  const counts = Object.fromEntries(LABELS.map(label => [label, filtered.filter(row => row.label === label).length]));
  const found = new Set(filtered.flatMap(row => row.entityNames));
  const facts = filtered.reduce((sum, row) => sum + row.facts.length, 0);
  $('#stats').innerHTML = `<div class="stat"><div class="stat-title">Afirmații practice</div><div class="stat-value">${number(filtered.length)}<span style="font-size:12px;color:var(--muted);letter-spacing:0"> / ${number(model.rows.length)}</span></div><div class="stat-labels">${LABELS.map(l => `<span class="stat-sub"><i class="dot ${l}"></i> ${number(counts[l])}</span>`).join('')}</div></div><div class="stat"><div class="stat-title">Subiecte în lexicon</div><div class="stat-value">${model.subjects.size}</div><div class="stat-sub">${found.size} apar în selecția curentă</div></div><div class="stat"><div class="stat-title">Valori structurate în selecție</div><div class="stat-value">${number(facts)}</div><div class="stat-sub">${summarizePairs(filtered).length} perechi subiect–atribut</div></div><div class="stat"><div class="stat-title">Evenimente în lexicon</div><div class="stat-value">${model.lexicon.events.length}</div><div class="stat-sub">${esc(model.rows[0].date)} → ${esc(model.rows.at(-1).date)}</div></div>`;
  const invalidRange = state.filters.from && state.filters.to && state.filters.from > state.filters.to;
  $('#filter-status').textContent = invalidRange ? 'Interval invalid: data de început este după data de sfârșit. Ajustează filtrele.' : `${number(filtered.length)} afirmații în selecție · data = data paginii-sursă · legături extrase din form, cu eticheta rândului păstrată`;
  $('#export').disabled = !shown.length;
}

function renderMonths() {
  const allMonths = [...new Set(model.rows.map(row => row.date.slice(0, 7)))].sort();
  const groups = new Map(allMonths.map(month => [month, { true: 0, false: 0, unsure: 0 }]));
  filtered.forEach(row => groups.get(row.date.slice(0, 7))[row.label]++);
  const maximum = Math.max(1, ...[...groups.values()].map(count => Object.values(count).reduce((a, b) => a + b, 0)));
  $('#monthly').innerHTML = '<div class="monthly-title"><strong>Ritmul datelor</strong>Click pe o lună ↗</div>' + allMonths.map(month => {
    const counts = groups.get(month), total = Object.values(counts).reduce((a, b) => a + b, 0);
    const label = new Intl.DateTimeFormat('ro-RO', { month: 'short', year: '2-digit', timeZone: 'UTC' }).format(new Date(month + '-01T00:00:00Z'));
    return `<button class="month ${state.filters.from?.startsWith(month) && state.filters.to?.startsWith(month) ? 'selected' : ''}" data-month="${month}" aria-label="${label}: ${total} query-uri; filtrează luna" title="${label} · ${total} query-uri (${counts.true} true / ${counts.false} false / ${counts.unsure} unsure)"><div class="month-stack"><div class="month-bar" style="height:${Math.max(2, total / maximum * 35)}px">${['unsure', 'false', 'true'].map(l => `<span class="${l}" style="height:${total ? counts[l] / total * 100 : 0}%"></span>`).join('')}</div></div><small>${esc(label)}</small></button>`;
  }).join('');
}

function renderEntity() {
  const subject = model.subjects.get(state.focus);
  const rows = filtered.filter(row => row.entityNames.includes(subject.name));
  const attributeCounts = new Map(subject.attributes.map(a => [a, new Set()]));
  rows.forEach(row => row.facts.filter(f => f.subject === subject.name).forEach(f => attributeCounts.get(f.attribute).add(row.id)));
  $('#entity-panel').innerHTML = `<div class="entity-icon">${model.lexicon.events.includes(subject.name) ? '◷' : '⌘'}</div><div class="eyebrow">${model.lexicon.events.includes(subject.name) ? 'EVENIMENT ÎN LEXICON' : 'SUBIECT SELECTAT'}</div><h2>${esc(subject.name)}</h2><div class="entity-description">${subject.aliases.length ? 'Aliasuri din lexicon' : 'Nume canonic · fără aliasuri'}</div><div class="tags">${subject.aliases.map(a => `<span class="tag">${esc(a)}</span>`).join('')}</div><div class="entity-metrics"><div><strong>${rows.length}</strong><small>query-uri filtrate</small></div><div><strong>${subject.attributes.length}</strong><small>atribute definite</small></div></div><h3>Atribute <span class="group-count">/ rânduri</span></h3><div class="attribute-list">${subject.attributes.map(a => `<button class="attribute-button" data-pair="${esc(pairKey(subject.name, a))}" title="Vezi istoricul ${esc(a)}"><span>${esc(a)}</span><b>${attributeCounts.get(a).size}</b></button>`).join('')}</div><button class="button entity-action" id="filter-entity">Filtrează query-urile acestui subiect ↗</button>`;
}

function renderRows() {
  const page = shown.slice(state.page * pageSize, (state.page + 1) * pageSize);
  $('#row-list').innerHTML = page.length ? page.map(row => `<button class="row-button ${row.id === state.selected ? 'selected' : ''}" data-row="${esc(row.id)}" aria-pressed="${row.id === state.selected}"><div class="row-date">${esc(row.date)}<small>${esc(row.id)}</small></div><div class="row-text">${esc(row.text)}<div class="row-sub">${esc([...new Set(row.facts.map(f => f.subject))].join(' · '))} <span> / ${row.facts.length} ${row.facts.length === 1 ? 'valoare' : 'valori'}</span></div></div>${badge(row.label)}</button>`).join('') : '<div class="empty">Niciun query pentru selecția curentă.<br>Schimbă filtrele sau resetează selecția.</div>';
  $('#pagination').innerHTML = `<span>${shown.length ? state.page * pageSize + 1 : 0}–${Math.min(shown.length, (state.page + 1) * pageSize)} din ${number(shown.length)} query-uri</span><div><button id="previous-page" ${state.page === 0 ? 'disabled' : ''} aria-label="Pagina anterioară">←</button><button id="next-page" ${(state.page + 1) * pageSize >= shown.length ? 'disabled' : ''} aria-label="Pagina următoare">→</button></div>`;
  $('#scope-banner').hidden = !state.scope;
  if (state.scope) $('#scope-banner').innerHTML = `<span>${esc(state.scope.title)} · ${shown.length} query-uri în filtrele curente</span><button id="clear-scope">Elimină selecția ×</button>`;
}

function renderQuery() {
  const row = model.byId.get(state.selected);
  if (!row) { $('#query-panel').innerHTML = '<div class="empty">Selectează un query pentru formele sale și conexiunile cu alte rânduri.</div>'; return; }
  const related = relatedRows(model, row);
  const relatedItems = related.slice(0, state.relatedLimit);
  $('#query-panel').innerHTML = `<div class="eyebrow">QUERY INSPECTOR</div><div class="query-heading"><h2>${esc(row.id)}</h2>${badge(row.label)}</div><div class="query-date">Pagina-sursă · ${dateLabel(row.date)}</div><p class="query-text">${esc(row.text)}</p><h3>Ce afirmă acest rând</h3>${row.facts.map(f => `<div class="fact-card"><div class="fact-subject">${esc(f.subject)}</div><div class="fact-attribute">${esc(f.attribute)}</div><div class="fact-value">${esc(formatValue(f.value))}<small>${esc(f.value.kind)}</small></div><button data-pair="${esc(f.key)}">Istoricul acestui atribut →</button></div>`).join('')}${row.label !== 'true' ? `<p class="note emphasis">Eticheta <strong>${row.label}</strong> se aplică întregului rând.${row.facts.length > 1 ? ' Nu indică individual care dintre valorile de mai sus este falsă sau necunoscută.' : ''}</p>` : '<p class="note">Eticheta true este cea publicată în practice, pe data acestui rând.</p>'}<details><summary>Vezi form original · JSON</summary><pre>${esc(JSON.stringify(row.form, null, 2))}</pre></details><div class="related-heading"><h3>Query-uri corelate</h3><small>${related.length} rânduri</small></div><p class="note">Din întregul practice, în ordine cronologică. Legătură = același subiect și atribut. Click-ul deschide rândul și elimină filtrele care îl ascund.</p>${relatedItems.map(item => `<button class="related-button" data-related="${esc(item.row.id)}"><span class="related-meta">${esc(item.row.id)} · ${item.row.date}${badge(item.row.label)}</span>${esc(item.row.text)}<span class="related-reason">${item.reasons.some(reason => reason.sameValue) ? 'Valoare structurată identică' : 'Altă valoare structurată'} · ${esc([...new Set(item.reasons.map(reason => reason.attribute))].join(', '))}</span></button>`).join('') || '<p class="note">Niciun alt rând cu aceeași pereche subiect–atribut.</p>'}${related.length > state.relatedLimit ? `<button id="more-related" class="text-button">Arată încă ${Math.min(20, related.length - state.relatedLimit)} rânduri ↓</button>` : ''}`;
}

function renderCorrelations() {
  const groups = summarizePairs(filtered).filter(group => !state.variationsOnly || group.values.size > 1);
  $('#correlation-list').innerHTML = groups.slice(0, state.correlationLimit).map(group => {
    const values = [...new Map(group.entries.map(entry => [valueKey(entry.fact.value), formatValue(entry.fact.value)])).values()];
    return `<button class="correlation-card" data-pair="${esc(group.key)}"><span class="pair-subject">${esc(group.subject)}</span><h3>${esc(group.attribute)}</h3><div class="correlation-meta"><strong>${group.values.size} valori distincte</strong><span>${group.dates.size} date de pagină</span></div><div class="correlation-values">${values.slice(0, 4).map(value => `<span>${esc(value)}</span>`).join('<small>·</small>')}${values.length > 4 ? `<small>+${values.length - 4}</small>` : ''}</div><div class="correlation-meta"><span>${group.entries[0].row.date} → ${group.entries.at(-1).row.date}</span><span>Vezi sursele ↗</span></div><div class="legend">${LABELS.map(l => `<span><i class="dot ${l}"></i>${group.labels[l]} ${l}</span>`).join('')}</div></button>`;
  }).join('') || '<div class="empty">Nu există grupuri cu aceste filtre.</div>';
  $('#more-correlations').hidden = groups.length <= state.correlationLimit;
}

function render() {
  getRows(); renderStats(); renderMonths();
  document.querySelectorAll('.nav').forEach(button => { button.classList.toggle('active', button.dataset.view === state.view); button.setAttribute('aria-current', button.dataset.view === state.view ? 'page' : 'false'); });
  $('#graph-view').hidden = state.view !== 'graph'; $('#correlations-view').hidden = state.view !== 'correlations'; $('#rows-section').hidden = state.view === 'correlations';
  if (state.view === 'graph') { renderEntity(); renderGraph(); }
  if (state.view === 'correlations') renderCorrelations();
  renderRows(); renderQuery();
}

function syncFilters() {
  $('#search').value = state.filters.query || ''; $('#subject-filter').value = state.filters.subject || ''; $('#label-filter').value = state.filters.label || '';
  $('#date-from').value = state.filters.from || ''; $('#date-to').value = state.filters.to || '';
}
function resetFilters() { state.filters = {}; state.scope = null; state.page = 0; state.relatedLimit = 8; syncFilters(); }
function selectPair(key) {
  const [subject, attribute] = JSON.parse(key);
  state.scope = { type: 'pair', key, title: `${subject} / ${attribute}` }; state.page = 0; state.view = 'timeline'; state.relatedLimit = 8; render(); $('#rows-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function showAbout() {
  $('#about-content').innerHTML = `<div class="step"><b>1</b><p><strong>Lexiconul este vocabularul.</strong><br>Subiecte, aliasuri, atribute și nume de evenimente. Nu furnizează singur valorile adevărate ale atributelor sau datele evenimentelor.</p></div><div class="step"><b>2</b><p><strong>Practice conține afirmațiile.</strong><br>Fiecare rând are text, data paginii, etichetă și un form structurat. O săgeată din graf înseamnă că un atribut are o valoare de tip name care se rezolvă la un subiect din lexicon. Culorile păstrează eticheta rândului; nu reprezintă predicții.</p></div><div class="step"><b>3</b><p><strong>Cronologia ajută la comparație.</strong><br>Data paginii nu este neapărat data intrării în vigoare a valorii. Ordinea în aceeași zi este stabilă, după ID. O valoare nouă observată nu dovedește automat o schimbare reală.</p></div><div class="step"><b>4</b><p><strong>Corelațiile sunt explicite.</strong><br>Același subiect + atribut; valorile identice se compară structural, inclusiv unitatea, moneda, perioada și operatorul. Nu convertim unități și nu inferăm cauzalitate. O etichetă false se aplică rândului întreg, nu fiecărui fapt separat.</p></div><p>Toate filtrele se aplică grafului, listei și corelațiilor. Panoul „Query-uri corelate” caută în întregul practice și precizează asta. Schema lexiconului rămâne completă, inclusiv subiectele fără query-uri în selecție. Pentru graf: click pe nod sau săgeată, trage fundalul pentru deplasare, folosește + / − pentru zoom.</p><details><summary>Proveniență · SHA-256</summary><p><code>data/practice.csv<br>${esc(payload.provenance.practice)}</code></p><p><code>data/lexicon.json<br>${esc(payload.provenance.lexicon)}</code></p><p>Lab de explorare local. Nicio etichetă generată, niciun model predictiv, nicio evaluare de generalizare. Numerele din cardurile de corelații numără aparițiile din form.</p></details>`;
  $('#about').showModal();
}

document.addEventListener('click', event => {
  const target = event.target.closest('button, a, .graph-node, .graph-link');
  if (!target || target.disabled) return;
  if (dragged && target.closest('#graph')) { dragged = false; return; }
  if (target.dataset.view) { state.view = target.dataset.view; if (state.view === 'correlations') state.scope = null; render(); }
  else if (target.dataset.pair) {
    if ($('#graph-dialog').open && target.closest('#graph-workspace')) {
      const key = target.dataset.pair, [subject, attribute] = JSON.parse(key);
      showGraphEvidence({ title: `${subject} / ${attribute}`, rows: filtered.filter(r => r.facts.some(f => f.key === key)) });
    } else selectPair(target.dataset.pair);
  }
  else if (target.dataset.graphRow) { explorer.row = target.dataset.graphRow; renderGraphEvidence(); }
  else if (target.dataset.row) { state.selected = target.dataset.row; state.relatedLimit = 8; renderRows(); renderQuery(); if (window.innerWidth <= 720) $('#query-panel').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  else if (target.dataset.related) {
    const id = target.dataset.related; resetFilters(); state.selected = id; state.view = 'timeline'; getRows(); state.page = Math.floor(shown.findIndex(row => row.id === id) / pageSize); render(); $('#query-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else if (target.dataset.node) selectGraphNode(target.dataset.node);
  else if (target.dataset.edge !== undefined) {
    const edge = activeEdges[Number(target.dataset.edge)], title = `${edge.source} → ${edge.attribute} → ${edge.target} (${edge.label})`;
    if ($('#graph-dialog').open) showGraphEvidence({ title, rows: filtered.filter(r => edge.rowIds.includes(r.id)) });
    else { state.scope = { type: 'rows', ids: edge.rowIds, title }; state.page = 0; render(); $('#rows-section').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  } else if (target.dataset.month) {
    const month = target.dataset.month, [year, monthNumber] = month.split('-').map(Number);
    state.filters.from = month + '-01'; state.filters.to = `${month}-${new Date(Date.UTC(year, monthNumber, 0)).getUTCDate()}`; state.page = 0; syncFilters(); render();
  } else if (target.classList.contains('brand')) { event.preventDefault(); resetFilters(); state.view = 'graph'; render(); }
  else {
    switch (target.id) {
      case 'reset': resetFilters(); render(); break;
      case 'relations-mode': state.graphMode = 'relations'; explorer.fit = true; explorer.selection = null; renderGraph(); break;
      case 'attributes-mode': state.graphMode = 'attributes'; explorer.fit = true; explorer.selection = null; renderGraph(); break;
      case 'graph-expand': openGraph(); break;
      case 'graph-close': closeGraph(); break;
      case 'graph-back': selectGraphNode(explorer.history.pop(), false); break;
      case 'graph-details-toggle': explorer.details = !explorer.details; syncGraphDetails(); break;
      case 'graph-evidence-back':
        if (explorer.row) { explorer.row = null; renderGraphEvidence(); }
        else { explorer.selection = null; syncGraphDetails(); }
        break;
      case 'graph-more-evidence': explorer.limit += 30; renderGraphEvidence(); break;
      case 'graph-open-timeline': {
        const selection = explorer.selection, row = explorer.row;
        closeGraph(); state.scope = { type: 'rows', ids: selection.rows.map(r => r.id), title: selection.title };
        state.view = 'timeline'; state.page = 0; state.selected = row || selection.rows[0]?.id || null;
        render(); $('#rows-section').scrollIntoView({ behavior: 'smooth' }); break;
      }
      case 'graph-fit': resetCamera(); break;
      case 'zoom-in': zoomGraph(1.25); break;
      case 'zoom-out': zoomGraph(.8); break;
      case 'filter-entity': state.filters.subject = state.focus; state.scope = null; state.page = 0; syncFilters(); render(); break;
      case 'previous-page': state.page--; renderRows(); $('#rows-section').scrollIntoView({ behavior: 'smooth' }); break;
      case 'next-page': state.page++; renderRows(); $('#rows-section').scrollIntoView({ behavior: 'smooth' }); break;
      case 'clear-scope': state.scope = null; state.page = 0; render(); break;
      case 'more-related': state.relatedLimit += 20; renderQuery(); break;
      case 'more-correlations': state.correlationLimit += 18; renderCorrelations(); break;
      case 'about-button': case 'provenance-button': showAbout(); break;
      case 'close-about': $('#about').close(); break;
      case 'export': {
        const url = URL.createObjectURL(new Blob([toCsv(shown)], { type: 'text/csv;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = 'practice-selection.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); break;
      }
    }
  }
});

let searchTimer;
$('#search').addEventListener('input', event => { clearTimeout(searchTimer); state.filters.query = event.target.value; state.page = 0; searchTimer = setTimeout(render, 120); });
for (const [id, key] of [['subject-filter', 'subject'], ['label-filter', 'label'], ['date-from', 'from'], ['date-to', 'to']]) {
  $('#' + id).addEventListener('change', event => { state.filters[key] = event.target.value; state.page = 0; render(); });
}
$('#sort').addEventListener('change', event => { state.sort = event.target.value; state.page = 0; render(); });
$('#graph-focus').addEventListener('change', event => selectGraphNode(event.target.value, true, true));
$('#graph-all').addEventListener('change', event => { state.all = event.target.checked; explorer.fit = true; explorer.selection = null; renderGraph(); });
$('#variations-only').addEventListener('change', event => { state.variationsOnly = event.target.checked; state.correlationLimit = 18; renderCorrelations(); });
for (const name of [...model.subjects.keys()].sort()) {
  for (const id of ['subject-filter', 'graph-focus']) { const option = document.createElement('option'); option.value = name; option.textContent = name; $('#' + id).append(option); }
}
$('#date-from').min = $('#date-to').min = model.rows[0].date;
$('#date-from').max = $('#date-to').max = model.rows.at(-1).date;
render();
initGraph();
