import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseCsv, createModel, filterRows, relatedRows, relationEdges, summarizePairs, valueKey, pairKey, formatValue, toCsv } from '../core.mjs';

const lexicon = { subjects: [{ name: 'Alpha', aliases: ['A Inc'], attributes: ['price', 'provider'] }, { name: 'Beta', aliases: [], attributes: ['price'] }], events: [] };
const fact = (subject, attribute, value) => ({ subject, attribute, value });
const money = (value, currency = 'EUR') => ({ kind: 'money', value, currency, per: 'month' });
const row = (id, date, label, form, text = 'A statement, with a "quote".\nSecond line.') => ({ id, date, label, form, text });
const rows = [
  row('p-10', '2026-01-12', 'false', [fact('Alpha', 'price', money(99)), fact('Alpha', 'provider', { kind: 'name', value: 'Beta' })]),
  row('p-2', '2026-01-12', 'true', [fact('a inc', 'price', money(49))]),
  row('p-1', '2025-12-01', 'true', [fact('Alpha', 'price', money(49))]),
  row('p-3', '2026-02-01', 'unsure', [fact('Beta', 'price', money(49))]),
  row('p-4', '2026-03-01', 'true', [fact('Alpha', 'price', money(49, 'USD'))]),
];

test('CSV round trip preserves commas, quotes, multiline text, BOM and form JSON', () => {
  assert.deepEqual(parseCsv(toCsv(rows)), rows);
  assert.deepEqual(parseCsv(toCsv(rows).replaceAll('\r\n', '\n')), rows);
});
test('malformed CSV is rejected with clear errors', () => {
  assert.throws(() => parseCsv('id,text,date,label,form\np-1,"unterminated'), /Unclosed/);
  assert.throws(() => parseCsv('id,text,date,label,form\np-1,x'), /column count/);
  assert.throws(() => parseCsv('id,text,date,label,form\np-1,x,2026-01-01,true,invalid'), /form JSON/);
});
test('chronology is stable by date then natural ID, aliases resolve without changing source forms', () => {
  const model = createModel(rows, lexicon);
  assert.deepEqual(model.rows.map(r => r.id), ['p-1', 'p-2', 'p-10', 'p-3', 'p-4']);
  assert.equal(model.resolve('AInc'), 'Alpha');
  assert.equal(model.byId.get('p-2').facts[0].subject, 'Alpha');
  assert.equal(model.byId.get('p-2').form[0].subject, 'a inc');
});
test('filters combine inclusively; entity filter includes name targets; empty ranges stay empty', () => {
  const model = createModel(rows, lexicon);
  assert.deepEqual(filterRows(model, { subject: 'Alpha', from: '2026-01-12', to: '2026-01-12', label: 'true' }).map(r => r.id), ['p-2']);
  assert.deepEqual(filterRows(model, { subject: 'Beta' }).map(r => r.id), ['p-10', 'p-3']);
  assert.equal(filterRows(model, { query: 'a inc', label: 'false' }).length, 1);
  assert.equal(filterRows(model, { from: '2026-02-01', to: '2025-01-01' }).length, 0);
  assert.equal(filterRows(model, { query: 'no match anywhere' }).length, 0);
});
test('related queries require both subject and attribute, preserve labels and distinguish currencies', () => {
  const model = createModel(rows, lexicon), related = relatedRows(model, model.byId.get('p-2'));
  assert.deepEqual(related.map(item => item.row.id), ['p-1', 'p-10', 'p-4']);
  assert.deepEqual(related.map(item => item.reasons[0].sameValue), [true, false, false]);
  assert.equal(related[1].row.label, 'false');
});
test('graph relations derive only from structured name facts and keep source row label', () => {
  const model = createModel(rows, lexicon), edges = relationEdges(model.rows);
  assert.deepEqual(edges, [{ source: 'Alpha', target: 'Beta', attribute: 'provider', label: 'false', rowIds: ['p-10'] }]);
  assert.deepEqual(relationEdges(filterRows(model, { label: 'true' })), []);
});
test('structural value comparison includes units, operators, billing periods and currency', () => {
  assert.equal(valueKey(money(49)), valueKey({ per: 'month', currency: 'EUR', value: 49, kind: 'money' }));
  assert.notEqual(valueKey(money(49)), valueKey({ ...money(49), per: 'year' }));
  assert.notEqual(valueKey(money(49)), valueKey({ ...money(49), op: 'gt' }));
  assert.notEqual(valueKey({ kind: 'duration', value: 1, unit: 'day' }), valueKey({ kind: 'duration', value: 24, unit: 'h' }));
  assert.equal(formatValue({ ...money(49), op: 'ge' }), '≥ 49 EUR/month');
});
test('summaries preserve observations rather than assigning fact-level verdicts', () => {
  const groups = summarizePairs(createModel(rows, lexicon).rows);
  const prices = groups.find(group => group.key === pairKey('Alpha', 'price'));
  assert.equal(prices.values.size, 3);
  assert.equal(prices.dates.size, 3);
  assert.deepEqual(prices.labels, { true: 3, false: 1, unsure: 0 });
});
test('invalid dates, duplicate IDs, schema mismatches and ambiguous aliases fail', () => {
  assert.throws(() => createModel([...rows, rows[0]], lexicon), /duplicate row/);
  assert.throws(() => createModel([{ ...rows[0], date: '2026-02-30' }], lexicon), /Invalid date/);
  assert.throws(() => createModel([row('x', '2026-01-01', 'true', [fact('Alpha', 'unknown', money(1))])], lexicon), /Unknown subject/);
  assert.throws(() => createModel(rows, { ...lexicon, subjects: [...lexicon.subjects, { name: 'Other', aliases: ['A Inc'], attributes: [] }] }), /Ambiguous alias/);
});
test('real practice parses completely with source labels, references and chronology intact', async () => {
  const [csv, json] = await Promise.all([readFile(new URL('../../../data/practice.csv', import.meta.url), 'utf8'), readFile(new URL('../../../data/lexicon.json', import.meta.url), 'utf8')].map(p => p));
  const model = createModel(parseCsv(csv), JSON.parse(json));
  assert.equal(model.rows.length, 1897);
  assert.equal(model.subjects.size, 62);
  assert.equal(model.pairs.size, 514);
  assert.deepEqual(Object.fromEntries(['true', 'false', 'unsure'].map(label => [label, filterRows(model, { label }).length])), { true: 1581, false: 277, unsure: 39 });
  assert.equal(model.rows[0].date, '2025-10-07');
  assert.equal(model.rows.at(-1).date, '2026-10-28');
  assert.equal(model.rows.reduce((n, r) => n + r.facts.length, 0), 2402);
  for (const edge of relationEdges(model.rows)) {
    assert.ok(model.subjects.has(edge.source) && model.subjects.has(edge.target));
    assert.ok(edge.rowIds.every(id => model.byId.get(id).label === edge.label));
  }
});
