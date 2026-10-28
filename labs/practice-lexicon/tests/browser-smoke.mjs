import { expression } from './browser-checks.mjs';
// Run against an already opened Orca browser page: node .../browser-smoke.mjs PAGE_ID
import { execFileSync } from 'node:child_process';
const page = process.argv[2];
if (!page) throw new Error('Pass the Orca browserPageId as the first argument');
const cli = process.env.ORCA_CLI_COMMAND || 'orca';
function run(args) {
  let output;
  try { output = execFileSync(cli, args, { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 }); }
  catch (error) { throw new Error(error.stdout || error.message); }
  const response = JSON.parse(output);
  if (!response.ok) throw new Error(JSON.stringify(response.error));
  return response;
}
run(['reload', '--page', page, '--json']);
run(['snapshot', '--page', page, '--json']);
if (process.argv[3]) run(['exec', '--page', page, '--command', `set viewport ${Number(process.argv[3])} ${Number(process.argv[4] || 844)}`, '--json']);

const response = run(['eval', '--page', page, '--expression', `(${expression})()`, '--json']);
console.log(JSON.stringify(response.result, null, 2));
