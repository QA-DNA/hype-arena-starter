import './build.mjs';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
const port = Number(process.env.LAB_PORT || 8790);
const output = new URL('../../artifacts/practice-lexicon-lab/index.html', import.meta.url);
const server = createServer(async (request, response) => {
  if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405).end(); return; }
  if (!['/', '/index.html'].includes(request.url.split('?')[0])) { response.writeHead(404).end('Not found'); return; }
  try {
    const html = await readFile(output);
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    response.end(request.method === 'HEAD' ? undefined : html);
  } catch { response.writeHead(500).end('Rebuild the lab HTML and try again.'); }
});
server.on('error', error => { console.error(error.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Practice / Lexicon Lab: http://127.0.0.1:${port}`));
