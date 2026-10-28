import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { parseCsv, createViewerModel } from './viewer-model.mjs';

const root = new URL('../../', import.meta.url);
const here = new URL('./', import.meta.url);
const sources = ['data/practice.csv', 'labs/assertion-extraction/outputs/practice.assertions.csv'];
let texts;
try { texts = await Promise.all(sources.map(p => readFile(new URL(p, root), 'utf8'))); }
catch (e) { throw new Error('Generate practice.assertions.csv first using the parse command in labs/assertion-extraction/README.md. ' + e.message); }
const practice = parseCsv(texts[0], ['id', 'text', 'date', 'label', 'form']);
const assertions = parseCsv(texts[1], ['id', 'occurrence_id', 'date', 'parent_label', 'subject', 'attribute', 'assertion_text', 'original_text', 'normalized_text', 'source_spans_json', 'normalized_start', 'normalized_end', 'subject_source_start', 'subject_source_end', 'normalization_issues_json', 'index_fingerprint']);
const model = createViewerModel(practice, assertions);
const payload = JSON.stringify({ model, sources: sources.map((path, i) => ({ path, sha256: createHash('sha256').update(texts[i]).digest('hex') })), builtAt: new Date().toISOString() }).replaceAll('<', '\\u003c');
const [template, css, modelCode, app] = await Promise.all(['viewer.html', 'viewer.css', 'viewer-model.mjs', 'viewer.js'].map(p => readFile(new URL(p, here), 'utf8')));
const html = template.replace('/* VIEWER_STYLE */', () => css).replace('/* VIEWER_DATA */', () => payload).replace('/* VIEWER_CODE */', () => modelCode.replace(/^export /gm, '') + '\n' + app);
const output = new URL('artifacts/assertion-extraction-viewer/index.html', root);
await mkdir(new URL('./', output), { recursive: true });
await writeFile(output, html);
console.log(`Built ${output.pathname} (${model.counts.rows} rows)`);
