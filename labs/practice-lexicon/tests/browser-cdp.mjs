// Optional local Chromium QA. Pass an installed Chrome/Edge executable; no npm packages.
import { spawn } from 'node:child_process';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { expression } from './browser-checks.mjs';
const executable = process.argv[2];
if (!executable) throw new Error('Pass an installed Chrome or Edge executable path');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const output = resolve(root, 'artifacts/practice-lexicon-lab');
const profile = resolve(output, `browser-profile-${process.pid}`);
await mkdir(profile, { recursive: true });
const browser = spawn(executable, ['--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
let socket;
const pause = ms => new Promise(r => setTimeout(r, ms));
try {
  let port;
  for (let i = 0; i < 80; i++) {
    try { port = Number((await readFile(resolve(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; } catch { await pause(100); }
  }
  if (!port) throw new Error('Chromium debugging endpoint did not start');
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
  await new Promise((r, reject) => { socket.onopen = r; socket.onerror = reject; });
  let sequence = 0; const pending = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data), request = pending.get(message.id);
    if (request) { pending.delete(message.id); clearTimeout(request.timer); message.error ? request.reject(new Error(JSON.stringify(message.error))) : request.resolve(message.result); }
  };
  const command = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence, timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 20000);
    pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async code => {
    const result = await command('Runtime.evaluate', { expression: code, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await command('Page.enable');
  for (const width of [1440, 390]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: width === 390 ? 844 : 1000, deviceScaleFactor: 1, mobile: false });
    await command('Page.navigate', { url: new URL('../index.html', `file:///${output.replaceAll('\\', '/')}/browser-profile/`).href });
    for (let i = 0; i < 60; i++) {
      if (await evaluate("!!document.querySelector('.graph-node')")) break;
      await pause(100);
    }
    const result = await evaluate(`(${expression})()`);
    console.log(JSON.stringify(result));
    await evaluate("document.querySelector('#graph-expand').scrollIntoView({block:'center'})");
    const button = await evaluate("(()=>{const r=document.querySelector('#graph-expand').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', ...button, button: 'left', clickCount: 1 });
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', ...button, button: 'left', clickCount: 1 });
    await pause(100);
    const native = await evaluate("document.fullscreenElement?.tagName || null");
    const start = await evaluate("(()=>{const r=document.querySelector('#graph').getBoundingClientRect();const m=document.querySelector('#graph-camera').getScreenCTM();return {x:r.x+30,y:r.y+100,tx:m.e,ty:m.f}})()");
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: start.x, y: start.y, button: 'left', clickCount: 1 });
    await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: start.x + 85, y: start.y + 50, button: 'left', buttons: 1 });
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: start.x + 85, y: start.y + 50, button: 'left', clickCount: 1 });
    await pause(80);
    const end = await evaluate("(()=>{const m=document.querySelector('#graph-camera').getScreenCTM();return {tx:m.e,ty:m.f}})()");
    if (Math.abs(end.tx - start.tx - 85) > 1 || Math.abs(end.ty - start.ty - 50) > 1) throw new Error('Real pointer drag does not follow cursor displacement');
    await command('Emulation.setTouchEmulationEnabled', { enabled: true });
    const touch = await evaluate("(()=>{const r=document.querySelector('#graph').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,zoom:Number(document.querySelector('#graph').dataset.zoom)}})()");
    await command('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: touch.x - 40, y: touch.y, id: 1 }, { x: touch.x + 40, y: touch.y, id: 2 }] });
    await command('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: touch.x - 60, y: touch.y, id: 1 }, { x: touch.x + 60, y: touch.y, id: 2 }] });
    await command('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await pause(80);
    const afterTouch = await evaluate("Number(document.querySelector('#graph').dataset.zoom)");
    if (Math.abs(afterTouch / touch.zoom - 1.5) > .05) throw new Error('Real two-finger gesture does not zoom proportionally');
    await command('Emulation.setTouchEmulationEnabled', { enabled: false });
    console.log(JSON.stringify({ viewport: width, nativeFullscreen: native, pointerDrag: 'passed', pinchZoom: 'passed' }));
    await evaluate("document.querySelector('#graph-fit').click()"); await pause(80);
    const screenshot = await command('Page.captureScreenshot', { format: 'png' });
    await writeFile(resolve(output, `explorer-${width}.png`), Buffer.from(screenshot.data, 'base64'));
    await evaluate("document.fullscreenElement ? document.exitFullscreen() : Promise.resolve()");
    if (!await evaluate("document.querySelector('#graph-dialog').open")) throw new Error('Leaving native fullscreen unexpectedly closed the viewport explorer');
    await evaluate("document.querySelector('#graph-close').click()");
  }
  await command('Browser.close');
} finally { socket?.close(); browser.kill(); }
