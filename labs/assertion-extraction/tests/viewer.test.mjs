import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseCsv, comparePairs, textSegments, createViewerModel, filterViewerRows } from '../viewer-model.mjs';

test('CSV preserves quoted multiline text and rejects malformed records', () => {
  assert.deepEqual(parseCsv('id,text\r\nx,"hello, ""world""\nagain"\r\n', ['id', 'text']), [{ id: 'x', text: 'hello, "world"\nagain' }]);
  for (const source of ['id,id\na,b', 'id,text\nx,"broken', 'id,text\nx,y,z']) assert.throws(() => parseCsv(source));
});
test('pair comparison respects duplicate occurrences and never matches unresolved fragments', () => {
  const pair = { subject: 'S', attribute: 'a' };
  const comparison = comparePairs([{ ...pair, status: 'paired' }, { ...pair, status: 'paired' }, { ...pair, status: 'unresolved' }], [pair]);
  assert.deepEqual(comparison.fragments.map(f => f.comparison), ['match', 'extra', 'unresolved']);
  assert.equal(comparison.extra, 1); assert.equal(comparison.exact, false);
  assert.equal(comparePairs([{ ...pair, status: 'paired' }], [pair, pair]).missing, 1);
});
test('UTF-8 byte highlights preserve text, merge overlaps and reject partial characters', () => {
  const text = 'Éva €19';
  const segments = textSegments(text, [{ start: 5, end: 8 }, { start: 5, end: 10 }]);
  assert.equal(segments.map(s => s.text).join(''), text);
  assert.equal(segments.filter(s => s.highlight).map(s => s.text).join(''), '€19');
  assert.throws(() => textSegments(text, [{ start: 1, end: 3 }]));
  assert.throws(() => textSegments(text, [{ start: -1, end: 3 }]));
});
test('practice snapshot matches the Rust diagnostic and supports filters', async () => {
  const practice = parseCsv(await readFile(new URL('../../../data/practice.csv', import.meta.url), 'utf8'));
  const assertions = parseCsv(await readFile(new URL('../outputs/practice.assertions.csv', import.meta.url), 'utf8'));
  const model = createViewerModel(practice, assertions);
  assert.deepEqual(model.counts, { rows: 1897, paired: 593, unresolved: 2046, exact: 363 });
  assert.equal(model.rows.find(r => r.id === 'p-1834').fragments.length, 8);
  assert.equal(model.rows.find(r => r.id === 'p-843').missing, 4);
  assert.equal(filterViewerRows(model.rows, { comparison: 'match' }).length, 363);
  assert.equal(filterViewerRows(model.rows, { query: 'p-1834' }).length, 1);
  assert.equal(filterViewerRows(model.rows, { status: 'unresolved' }).length, 1376);
  const changed = structuredClone(assertions); changed[0].original_text += '!';
  assert.throws(() => createViewerModel(practice, changed), /Stale/);
});
