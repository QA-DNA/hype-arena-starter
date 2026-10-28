// Optional Chromium-family smoke test; no npm packages. Development fixtures only.
import { spawn } from 'node:child_process';
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const executable = process.argv[2];
if (!executable) throw new Error('Pass an installed Chromium-family executable, e.g. /usr/bin/brave');
const output = fileURLToPath(new URL('../../../artifacts/assertion-extraction-viewer/', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'veridyct-viewer-browser-'));
const browser = spawn(executable, ['--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
let socket, launchError;
browser.on('error', error => { launchError = error; });
const exited = new Promise(resolve => browser.once('exit', resolve));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  let port;
  for (let i = 0; i < 100; i++) {
    if (launchError) throw launchError;
    if (browser.exitCode !== null) throw new Error('Browser exited before starting its debug endpoint');
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; } catch { await pause(100); }
  }
  if (!port) throw new Error('Browser debug endpoint did not start');
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0; const pending = new Map();
  socket.onmessage = event => {
    const data = JSON.parse(event.data), item = pending.get(data.id);
    if (!item) return;
    pending.delete(data.id); clearTimeout(item.timer);
    if (data.error) item.reject(new Error(JSON.stringify(data.error))); else item.resolve(data.result);
  };
  const command = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence, timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 15000);
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await command('Page.enable');
  for (const width of [1440, 390]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1100, deviceScaleFactor: 1, mobile: false });
    await command('Page.navigate', { url: pathToFileURL(join(output, 'index.html')).href });
    for (let i = 0; i < 100; i++) {
      if (await evaluate("document.querySelectorAll('#extracted-body tr').length > 0")) break;
      await pause(100);
    }
    const checks = await evaluate(`(() => {
      let checks = 0;
      const ok = (condition, message) => { if (!condition) throw new Error(message); checks++; };
      const byId = id => document.getElementById(id);
      const example = id => document.querySelector('[data-example="' + id + '"]').click();
      ok(byId('row-id').textContent === 'p-5', 'Default example');
      ok(document.querySelectorAll('#extracted-body tr').length === 2, 'Default split');
      document.querySelector('.fragment-button').click();
      ok(document.querySelectorAll('#original-text mark').length > 0, 'Original highlight');
      ok(document.querySelector('#normalized-text mark').textContent.includes('November'), 'Normalized highlight');
      ok(!byId('fragment-detail').hidden, 'Fragment explanation');
      document.querySelector('.fragment-button').click();
      ok(byId('fragment-detail').hidden, 'Toggle selection');
      example('p-1834');
      ok(document.querySelectorAll('#extracted-body tr').length === 8, 'Eight extracted pairs');
      ok(document.querySelectorAll('#reference-body tr').length === 8, 'Eight reference pairs');
      ok(byId('row-summary').textContent.includes('pairs match'), 'Pair comparison');
      byId('next').click(); ok(byId('row-id').textContent === 'p-1835', 'Next row');
      byId('previous').click(); ok(byId('row-id').textContent === 'p-1834', 'Previous row');
      example('p-843');
      ok(byId('row-summary').textContent.includes('4 missing'), 'Unresolved reference gaps');
      document.querySelector('.fragment-button').click();
      ok(byId('fragment-detail').textContent.includes('could not identify a subject'), 'Unresolved explanation');
      byId('search').value = 'not-a-real-id-0123'; byId('search').dispatchEvent(new Event('input'));
      ok(byId('detail').hidden && byId('result-count').textContent === '0 rows', 'Empty search');
      byId('reset').click();
      byId('comparison-filter').value = 'match'; byId('comparison-filter').dispatchEvent(new Event('change'));
      ok(byId('result-count').textContent === '363 rows', 'Match filter');
      byId('comparison-filter').value = ''; byId('status-filter').value = 'unresolved'; byId('status-filter').dispatchEvent(new Event('change'));
      ok(byId('result-count').textContent === '1,376 rows', 'Status filter');
      byId('reset').click();
      byId('search').value = 'p-1834'; byId('search').dispatchEvent(new Event('input'));
      ok(byId('result-count').textContent === '1 row' && byId('row-id').textContent === 'p-1834', 'ID search');
      byId('reset').click(); byId('page-next').click();
      ok(byId('page-label').textContent.startsWith('2 /'), 'List pagination');
      example('p-5');
      ok(document.documentElement.scrollWidth <= innerWidth + 1, 'No page-level horizontal overflow');
      return { checks, width: innerWidth };
    })()`);
    await evaluate("window.scrollTo({top:0,behavior:'instant'})"); await pause(200);
    const shot = await command('Page.captureScreenshot', { format: 'png' });
    await writeFile(join(output, `viewer-${width}.png`), Buffer.from(shot.data, 'base64'));
    console.log(JSON.stringify(checks));
  }
  await command('Browser.close');
} finally {
  socket?.close(); browser.kill(); await Promise.race([exited, pause(3000)]);
  await rm(profile, { recursive: true, force: true, maxRetries: 3 });
}
