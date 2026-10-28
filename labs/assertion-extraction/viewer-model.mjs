// Read-only inspection helpers. These never normalize, extract, or classify input.
export function parseCsv(source, required = []) {
  const table = [];
  let row = [], cell = '', quoted = false, closed = false;
  source = source.replace(/^\uFEFF/, '');
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (quoted) {
      if (c === '"' && source[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else cell += c;
    } else if (c === '"') {
      if (cell || closed) throw new Error('Unexpected quote in CSV');
      quoted = true;
    } else if (c === ',' || c === '\n' || c === '\r') {
      row.push(cell); cell = ''; closed = false;
      if (c !== ',') {
        if (c === '\r' && source[i + 1] === '\n') i++;
        if (row.length > 1 || row[0]) table.push(row);
        row = [];
      }
    } else {
      if (closed) throw new Error('Unexpected text after CSV quote');
      cell += c;
    }
  }
  if (quoted) throw new Error('Unclosed CSV quote');
  if (cell || row.length || closed) { row.push(cell); table.push(row); }
  const header = table.shift();
  if (!header || header.some(h => !h) || new Set(header).size !== header.length) throw new Error('Invalid CSV header');
  for (const key of required) if (!header.includes(key)) throw new Error(`Missing CSV column: ${key}`);
  return table.map((cells, i) => {
    if (cells.length !== header.length) throw new Error(`CSV record ${i + 2}: wrong column count`);
    return Object.fromEntries(header.map((key, j) => [key, cells[j]]));
  });
}

const pairKey = item => JSON.stringify([item.subject, item.attribute]);
export function comparePairs(fragments, reference) {
  const remaining = reference.map(item => ({ ...item, matched: false }));
  const extracted = fragments.map(item => {
    if (item.status !== 'paired') return { ...item, comparison: 'unresolved' };
    const found = remaining.find(r => !r.matched && pairKey(r) === pairKey(item));
    if (found) found.matched = true;
    return { ...item, comparison: found ? 'match' : 'extra' };
  });
  const missing = remaining.filter(r => !r.matched).length;
  const extra = extracted.filter(r => r.comparison === 'extra').length;
  return { fragments: extracted, reference: remaining, missing, extra, exact: missing === 0 && extra === 0 };
}

export function textSegments(text, spans) {
  const bytes = new TextEncoder().encode(text), decoder = new TextDecoder('utf-8', { fatal: true });
  const ranges = spans.map(s => ({ start: Number(s.start), end: Number(s.end) })).sort((a, b) => a.start - b.start);
  const merged = [];
  for (const span of ranges) {
    if (!Number.isSafeInteger(span.start) || !Number.isSafeInteger(span.end) || span.start < 0 || span.end < span.start || span.end > bytes.length) throw new Error('Invalid UTF-8 source span');
    decoder.decode(bytes.slice(0, span.start)); decoder.decode(bytes.slice(span.start, span.end));
    if (span.start === span.end) continue;
    const last = merged.at(-1);
    if (last && span.start <= last.end) last.end = Math.max(last.end, span.end);
    else merged.push({ ...span });
  }
  const result = []; let end = 0;
  for (const span of merged) {
    if (span.start > end) result.push({ text: decoder.decode(bytes.slice(end, span.start)), highlight: false });
    result.push({ text: decoder.decode(bytes.slice(span.start, span.end)), highlight: true }); end = span.end;
  }
  if (end < bytes.length) result.push({ text: decoder.decode(bytes.slice(end)), highlight: false });
  return result;
}

export function createViewerModel(practice, assertions) {
  const grouped = new Map(), occurrences = new Set();
  for (const a of assertions) {
    if (!a.id || !a.occurrence_id || occurrences.has(a.occurrence_id)) throw new Error('Missing or duplicate occurrence ID');
    if (!['paired', 'unresolved'].includes(a.status) || !['split', 'partial', 'unresolved'].includes(a.row_status)) throw new Error(`Invalid extraction status: ${a.id}`);
    if (a.status === 'paired' && (!a.subject || !a.attribute)) throw new Error(`Paired record has no pair: ${a.id}`);
    occurrences.add(a.occurrence_id);
    if (!grouped.has(a.id)) grouped.set(a.id, []);
    grouped.get(a.id).push(a);
  }
  const ids = new Set();
  const rows = practice.map(p => {
    if (!p.id || ids.has(p.id)) throw new Error('Missing or duplicate practice ID');
    ids.add(p.id);
    const fragments = grouped.get(p.id);
    if (!fragments?.length) throw new Error(`No output for ${p.id}; rerun the parser`);
    const reference = JSON.parse(p.form);
    if (!Array.isArray(reference) || reference.some(r => !r.subject || !r.attribute || !r.value)) throw new Error(`Invalid practice form: ${p.id}`);
    for (const a of fragments) {
      if (a.original_text !== p.text || a.date !== p.date || a.parent_label !== p.label || a.normalized_text !== fragments[0].normalized_text || a.row_status !== fragments[0].row_status || a.index_fingerprint !== assertions[0].index_fingerprint) throw new Error(`Stale or inconsistent output for ${p.id}; rerun the parser`);
      a.sourceSpans = JSON.parse(a.source_spans_json);
      a.normalizedSpan = { start: Number(a.normalized_start), end: Number(a.normalized_end) };
      textSegments(p.text, a.sourceSpans);
      const highlighted = textSegments(a.normalized_text, [a.normalizedSpan]).filter(s => s.highlight).map(s => s.text).join('');
      if (highlighted !== a.assertion_text) throw new Error(`Assertion text/span mismatch: ${p.id}`);
      a.subjectSpan = a.subject_source_start === '' ? null : { start: Number(a.subject_source_start), end: Number(a.subject_source_end) };
      if (a.subjectSpan) textSegments(p.text, [a.subjectSpan]);
    }
    const comparison = comparePairs(fragments, reference);
    return { id: p.id, date: p.date, label: p.label, text: p.text,
      normalized: fragments[0].normalized_text, status: fragments[0].row_status,
      issues: JSON.parse(fragments[0].normalization_issues_json), ...comparison,
      search: [p.id, p.text, fragments[0].normalized_text, ...fragments.flatMap(a => [a.subject, a.attribute, a.reason]), ...reference.flatMap(a => [a.subject, a.attribute])].join(' ').toLowerCase() };
  });
  if (grouped.size !== ids.size) throw new Error('Output contains unknown practice IDs');
  return { rows, counts: {
    rows: rows.length, paired: assertions.filter(a => a.status === 'paired').length,
    unresolved: assertions.filter(a => a.status === 'unresolved').length, exact: rows.filter(r => r.exact).length,
  } };
}

export function filterViewerRows(rows, { query = '', status = '', comparison = '' } = {}) {
  const needle = query.trim().toLowerCase();
  return rows.filter(r => (!needle || r.search.includes(needle)) && (!status || r.status === status)
    && (!comparison || (comparison === 'match' ? r.exact : !r.exact)));
}

export function formatReferenceValue(v) {
  const op = ({ eq: '', gt: '> ', ge: '≥ ', lt: '< ', le: '≤ ' })[v.op || 'eq'] ?? `${v.op} `;
  const value = typeof v.value === 'boolean' ? String(v.value) : v.value;
  const suffix = v.kind === 'percent' ? '%' : v.kind === 'money' ? ` ${v.currency || ''}${v.per ? ` / ${v.per}` : ''}` : v.unit ? ` ${v.unit}` : '';
  return `${op}${value}${suffix}`;
}
