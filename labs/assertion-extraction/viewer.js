const payload = JSON.parse(document.getElementById('viewer-data').textContent);
const model = payload.model;
const $ = id => document.getElementById(id);
const statusNames = { split: 'Fully paired', partial: 'Partly paired', unresolved: 'Unresolved' };
const reasonNames = {
  subject_not_identified: 'The parser could not identify a subject in this fragment.',
  attribute_not_identified: 'A subject was found, but no supported attribute cue was found.',
  multiple_attributes_in_fragment: 'Several attributes were detected, but the parser could not safely split this fragment.',
  multiple_subjects_in_fragment: 'Several subjects were mentioned, but the parser could not attach this phrase to one of them.',
  unsupported_scope_or_alignment: 'The parser could not safely separate the condition, shared scope, or list alignment.',
  empty_or_unsupported_text: 'The text is empty or has no supported extraction pattern.',
};
let filtered = model.rows, selectedId = model.rows.some(r => r.id === 'p-5') ? 'p-5' : model.rows[0]?.id;
let page = 0, activeFragment = null;
const pageSize = 40;
function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function badge(text, type = 'neutral') { return el('span', text, `tag ${type}`); }
function highlight(node, text, spans) {
  node.replaceChildren(...textSegments(text, spans).map(s => s.highlight ? el('mark', s.text) : document.createTextNode(s.text)));
}
for (const [key, label] of [['rows', 'Practice rows'], ['paired', 'Fragments with a pair'], ['unresolved', 'Unresolved fragments'], ['exact', 'Rows whose pairs match']]) {
  const node = el('div', undefined, 'metric'); node.append(el('strong', model.counts[key].toLocaleString()), el('span', label)); $('metrics').append(node);
}
function renderList() {
  $('result-count').textContent = `${filtered.length.toLocaleString()} row${filtered.length === 1 ? '' : 's'}`;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  page = Math.max(0, Math.min(page, totalPages - 1));
  $('page-label').textContent = `${page + 1} / ${totalPages}`;
  $('page-prev').disabled = page === 0; $('page-next').disabled = page + 1 >= totalPages;
  $('row-list').replaceChildren();
  if (!filtered.length) $('row-list').append(el('p', 'No rows match these filters.', 'empty'));
  for (const row of filtered.slice(page * pageSize, (page + 1) * pageSize)) {
    const button = el('button', undefined, 'row-item'); button.dataset.id = row.id;
    button.setAttribute('aria-current', String(row.id === selectedId));
    const top = el('span', undefined, 'row-item-top');
    top.append(el('strong', row.id), badge(statusNames[row.status], row.status === 'split' ? 'good' : 'neutral'));
    button.append(top, el('span', row.text, 'row-preview'));
    button.addEventListener('click', () => selectRow(row.id)); $('row-list').append(button);
  }
}
function selectRow(id, scroll = false) {
  selectedId = id; activeFragment = null;
  const index = filtered.findIndex(r => r.id === id); if (index >= 0) page = Math.floor(index / pageSize);
  renderList(); renderDetail();
  if (scroll) $('detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function applyFilters() {
  filtered = filterViewerRows(model.rows, { query: $('search').value, status: $('status-filter').value, comparison: $('comparison-filter').value });
  if (!filtered.some(r => r.id === selectedId)) selectedId = filtered[0]?.id;
  activeFragment = null; page = Math.max(0, Math.floor(filtered.findIndex(r => r.id === selectedId) / pageSize));
  renderList(); renderDetail();
}
function renderDetail() {
  const row = filtered.find(r => r.id === selectedId);
  $('detail').hidden = !row; if (!row) return;
  const index = filtered.indexOf(row);
  $('previous').disabled = index === 0; $('next').disabled = index === filtered.length - 1;
  $('row-id').textContent = row.id;
  $('row-meta').textContent = `${row.date} · Source truth label: ${row.label || 'unlabelled'} (whole row)`;
  $('row-summary').replaceChildren(badge(statusNames[row.status], row.status === 'split' ? 'good' : 'neutral'));
  $('row-summary').append(el('span', row.exact ? 'Subject–attribute pairs match the practice annotations.' : `${row.missing} missing reference pair${row.missing === 1 ? '' : 's'} · ${row.extra} extra extracted pair${row.extra === 1 ? '' : 's'}`));
  highlight($('original-text'), row.text, []); highlight($('normalized-text'), row.normalized, []);
  $('normalization-status').textContent = row.text === row.normalized ? 'Text unchanged' : 'Names normalized';
  $('highlight-help').textContent = 'Select an extracted fragment below to highlight its source.';
  $('normalization-issues').replaceChildren();
  for (const issue of row.issues) {
    const wording = textSegments(row.text, [issue.original_span]).filter(s => s.highlight).map(s => s.text).join('');
    $('normalization-issues').append(el('p', `Normalization left “${wording}” unchanged: ${issue.reason === 'ambiguous_common_word' ? 'this alias can also be an ordinary word' : 'this alias has several possible subjects'}. Candidate${issue.candidates.length === 1 ? '' : 's'}: ${issue.candidates.join(', ')}.`, 'issue'));
  }
  $('fragment-count').textContent = `${row.fragments.length} fragment${row.fragments.length === 1 ? '' : 's'}`;
  $('extracted-body').replaceChildren(); $('reference-body').replaceChildren();
  $('fragment-detail').hidden = true;
  for (const fragment of row.fragments) {
    const tr = el('tr'); tr.dataset.occurrence = fragment.occurrence_id;
    tr.append(el('td', fragment.subject || 'Not identified', fragment.subject ? '' : 'muted'), el('td', fragment.attribute || 'Not identified', 'attribute'));
    const cell = el('td'), button = el('button', fragment.assertion_text || '(empty text)', 'fragment-button');
    button.setAttribute('aria-pressed', 'false'); button.setAttribute('aria-label', `Inspect ${fragment.occurrence_id}: ${fragment.assertion_text || 'empty text'}`);
    button.addEventListener('click', () => inspect(row, fragment)); cell.append(button); tr.append(cell);
    const result = el('td'); result.append(badge(({ match: 'Pair matches', extra: 'Extra pair', unresolved: 'Unresolved' })[fragment.comparison], fragment.comparison === 'match' ? 'good' : fragment.comparison === 'extra' ? 'warn' : 'neutral')); tr.append(result);
    $('extracted-body').append(tr);
  }
  for (const reference of row.reference) {
    const tr = el('tr'); tr.append(el('td', reference.subject), el('td', reference.attribute, 'attribute'), el('td', formatReferenceValue(reference.value)));
    const cell = el('td'); cell.append(badge(reference.matched ? 'Pair found' : 'Pair missing', reference.matched ? 'good' : 'warn')); tr.append(cell); $('reference-body').append(tr);
  }
}
function inspect(row, fragment) {
  activeFragment = activeFragment === fragment.occurrence_id ? null : fragment.occurrence_id;
  for (const tr of $('extracted-body').children) {
    const active = tr.dataset.occurrence === activeFragment;
    tr.classList.toggle('selected-fragment', active); tr.querySelector('button').setAttribute('aria-pressed', String(active));
  }
  highlight($('original-text'), row.text, activeFragment ? [...fragment.sourceSpans, ...(fragment.subjectSpan ? [fragment.subjectSpan] : [])] : []);
  highlight($('normalized-text'), row.normalized, activeFragment ? [fragment.normalizedSpan] : []);
  $('highlight-help').textContent = activeFragment ? 'Yellow highlights show the fragment and its subject in the original text, and the assertion wording in the normalized text.' : 'Select an extracted fragment below to highlight its source.';
  $('fragment-detail').hidden = !activeFragment; $('fragment-detail').replaceChildren();
  if (!activeFragment) return;
  $('fragment-detail').append(el('strong', fragment.occurrence_id), el('p', fragment.status === 'unresolved' ? reasonNames[fragment.reason] || fragment.reason : fragment.comparison === 'match' ? 'This subject–attribute occurrence appears in the practice annotations. Check the highlighted assertion wording yourself; value correctness is not compared.' : 'This subject–attribute occurrence has no remaining match in the practice annotations. It may be a parser error or a difference in annotation scope.'));
  const details = el('details'), summary = el('summary', 'Rule and source offsets');
  details.append(summary, el('pre', JSON.stringify({ rule: fragment.rule, reason: fragment.reason || null, original_byte_spans: fragment.sourceSpans, subject_byte_span: fragment.subjectSpan, normalized_byte_span: fragment.normalizedSpan }, null, 2))); $('fragment-detail').append(details);
}
for (const id of ['search', 'status-filter', 'comparison-filter']) $(id).addEventListener(id === 'search' ? 'input' : 'change', applyFilters);
$('reset').addEventListener('click', () => { $('search').value = ''; $('status-filter').value = ''; $('comparison-filter').value = ''; selectedId = null; applyFilters(); });
$('page-prev').addEventListener('click', () => { page--; renderList(); }); $('page-next').addEventListener('click', () => { page++; renderList(); });
for (const [id, step] of [['previous', -1], ['next', 1]]) $(id).addEventListener('click', () => { const row = filtered[filtered.findIndex(r => r.id === selectedId) + step]; if (row) selectRow(row.id); });
for (const button of document.querySelectorAll('[data-example]')) button.addEventListener('click', () => { $('reset').click(); selectRow(button.dataset.example, true); });
$('provenance').append(el('p', `Snapshot built ${new Date(payload.builtAt).toLocaleString()}`));
for (const source of payload.sources) $('provenance').append(el('p', `${source.path} · SHA-256 ${source.sha256}`));
selectRow(selectedId);
