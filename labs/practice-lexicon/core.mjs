// Pure, offline exploration helpers. No prediction or competition solver.
export const LABELS = ['true', 'false', 'unsure'];
export const normalizeName = value => value.toLowerCase().replace(/\s+/g, '');
export const pairKey = (subject, attribute) => JSON.stringify([subject, attribute]);
export const valueKey = value => JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))));
export const compareRows = (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id, 'en', { numeric: true });

export function parseCsv(source) {
  const table = [];
  let row = [], cell = '', quoted = false, closed = false;
  source = source.replace(/^\uFEFF/, '');
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (quoted) {
      if (char === '"' && source[i + 1] === '"') { cell += '"'; i++; }
      else if (char === '"') { quoted = false; closed = true; }
      else cell += char;
    } else if (char === '"') {
      if (cell || closed) throw new Error('Unexpected quote in CSV');
      quoted = true;
    } else if (char === ',' || char === '\n' || char === '\r') {
      row.push(cell); cell = ''; closed = false;
      if (char !== ',') {
        if (char === '\r' && source[i + 1] === '\n') i++;
        if (row.length > 1 || row[0]) table.push(row);
        row = [];
      }
    } else {
      if (closed) throw new Error('Unexpected text after CSV quote');
      cell += char;
    }
  }
  if (quoted) throw new Error('Unclosed CSV quote');
  if (cell || row.length || closed) { row.push(cell); table.push(row); }
  const header = table.shift();
  if (!header || new Set(header).size !== header.length) throw new Error('Invalid CSV header');
  for (const key of ['id', 'text', 'date', 'label', 'form']) {
    if (!header.includes(key)) throw new Error(`Missing CSV column: ${key}`);
  }
  return table.map((cells, i) => {
    if (cells.length !== header.length) throw new Error(`CSV row ${i + 2}: wrong column count`);
    const record = Object.fromEntries(header.map((key, j) => [key, cells[j]]));
    try { record.form = JSON.parse(record.form); }
    catch { throw new Error(`Invalid form JSON: ${record.id}`); }
    return record;
  });
}

export function createModel(input, lexicon) {
  if (!Array.isArray(lexicon.subjects) || !Array.isArray(lexicon.events)) throw new Error('Invalid lexicon');
  const names = new Map(), subjects = new Map();
  for (const subject of lexicon.subjects) {
    if (subjects.has(subject.name)) throw new Error(`Duplicate subject: ${subject.name}`);
    subjects.set(subject.name, subject);
    for (const name of [subject.name, ...subject.aliases]) {
      const key = normalizeName(name);
      if (names.has(key) && names.get(key) !== subject.name) throw new Error(`Ambiguous alias: ${name}`);
      names.set(key, subject.name);
    }
  }
  const resolve = name => names.get(normalizeName(name));
  const ids = new Set(), pairs = new Map(), byId = new Map();
  const rows = input.map(row => {
    if (!row.id || ids.has(row.id)) throw new Error(`Missing/duplicate row id: ${row.id}`);
    ids.add(row.id);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(Date.parse(row.date)) || new Date(row.date).toISOString().slice(0, 10) !== row.date) throw new Error(`Invalid date: ${row.id}`);
    if (!LABELS.includes(row.label)) throw new Error(`Invalid label: ${row.id}`);
    if (!Array.isArray(row.form) || !row.form.length) throw new Error(`Empty form: ${row.id}`);
    const facts = row.form.map((fact, index) => {
      const subject = resolve(fact.subject);
      if (!subject || !subjects.get(subject).attributes.includes(fact.attribute)) throw new Error(`Unknown subject/attribute: ${row.id} / ${fact.subject}.${fact.attribute}`);
      if (!fact.value || !['date', 'name', 'quantity', 'percent', 'duration', 'version', 'boolean', 'money'].includes(fact.value.kind) || fact.value.value === undefined) throw new Error(`Invalid value: ${row.id}`);
      return { ...fact, subject, index, key: pairKey(subject, fact.attribute), target: fact.value.kind === 'name' ? resolve(fact.value.value) || null : null };
    });
    const entityNames = [...new Set(facts.flatMap(f => [f.subject, ...(f.target ? [f.target] : [])]))];
    const aliases = entityNames.flatMap(name => subjects.get(name).aliases);
    return { ...row, facts, entityNames, search: [row.id, row.text, ...entityNames, ...aliases, ...facts.map(f => `${f.attribute} ${formatValue(f.value)}`)].join(' ').toLowerCase() };
  }).sort(compareRows);
  for (const row of rows) {
    byId.set(row.id, row);
    for (const fact of row.facts) {
      if (!pairs.has(fact.key)) pairs.set(fact.key, []);
      pairs.get(fact.key).push({ row, fact });
    }
  }
  return { rows, lexicon, subjects, resolve, byId, pairs };
}

export function filterRows(model, filters = {}) {
  const query = (filters.query || '').trim().toLowerCase();
  return model.rows.filter(row => (!query || row.search.includes(query))
    && (!filters.subject || row.entityNames.includes(filters.subject))
    && (!filters.label || row.label === filters.label)
    && (!filters.from || row.date >= filters.from)
    && (!filters.to || row.date <= filters.to));
}

export function formatValue(v) {
  const prefix = ({ gt: '> ', ge: '≥ ', lt: '< ', le: '≤ ', eq: '' })[v.op || 'eq'] ?? `${v.op} `;
  if (v.kind === 'boolean') return `${prefix}${v.value ? 'da' : 'nu'}`;
  const suffix = v.kind === 'percent' ? '%' : v.kind === 'money' ? ` ${v.currency || ''}${v.per ? '/' + v.per : ''}` : v.unit ? ` ${v.unit}` : '';
  return `${prefix}${v.value}${suffix}`;
}

export function relatedRows(model, row) {
  const related = new Map();
  for (const fact of row.facts) {
    for (const entry of model.pairs.get(fact.key) || []) {
      if (entry.row.id === row.id) continue;
      if (!related.has(entry.row.id)) related.set(entry.row.id, { row: entry.row, reasons: [] });
      const reasons = related.get(entry.row.id).reasons;
      const sameValue = valueKey(fact.value) === valueKey(entry.fact.value);
      if (!reasons.some(reason => reason.key === fact.key && reason.sameValue === sameValue)) reasons.push({ key: fact.key, subject: fact.subject, attribute: fact.attribute, sameValue });
    }
  }
  return [...related.values()].sort((a, b) => compareRows(a.row, b.row));
}

export function relationEdges(rows) {
  const edges = new Map();
  for (const row of rows) for (const fact of row.facts) {
    if (!fact.target) continue;
    const key = JSON.stringify([fact.subject, fact.attribute, fact.target, row.label]);
    if (!edges.has(key)) edges.set(key, { source: fact.subject, target: fact.target, attribute: fact.attribute, label: row.label, rowIds: [] });
    if (!edges.get(key).rowIds.includes(row.id)) edges.get(key).rowIds.push(row.id);
  }
  return [...edges.values()];
}

export function summarizePairs(rows) {
  const groups = new Map();
  for (const row of rows) for (const fact of row.facts) {
    if (!groups.has(fact.key)) groups.set(fact.key, { key: fact.key, subject: fact.subject, attribute: fact.attribute, entries: [], values: new Set(), dates: new Set(), labels: { true: 0, false: 0, unsure: 0 } });
    const group = groups.get(fact.key);
    group.entries.push({ row, fact }); group.values.add(valueKey(fact.value)); group.dates.add(row.date); group.labels[row.label]++;
  }
  return [...groups.values()].sort((a, b) => b.values.size - a.values.size || b.entries.length - a.entries.length || a.key.localeCompare(b.key));
}

export function toCsv(rows) {
  const cell = value => `"${String(value).replaceAll('"', '""')}"`;
  return '\uFEFF' + ['id,text,date,label,form', ...rows.map(row => [row.id, row.text, row.date, row.label, JSON.stringify(row.form)].map(cell).join(','))].join('\r\n');
}
