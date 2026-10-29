import './build-viewer.mjs';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const port = Number(process.env.LAB_PORT || 8791);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('LAB_PORT must be 1..65535');
const output = new URL('../../artifacts/assertion-extraction-viewer/index.html', import.meta.url);
const server = createServer(async (req, res) => {
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
  if (!['/', '/index.html'].includes(req.url.split('?')[0])) { res.writeHead(404).end('Not found'); return; }
  try {
    const html = await readFile(output);
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(req.method === 'HEAD' ? undefined : html);
  } catch { res.writeHead(500).end('Rebuild the viewer and try again.'); }
});
server.on('error', e => { console.error(e.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Assertion viewer: http://127.0.0.1:${port}`));
