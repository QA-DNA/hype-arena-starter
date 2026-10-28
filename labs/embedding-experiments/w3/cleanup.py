"""Run once, with no run_model/run_centered process alive: drop superseded records from w3.jsonl, atomically.
 - 'load_failed' records of models that later loaded fine (static models failed once on max_seq_length=inf, fixed)
 - every GloVe record (re-run to fix disk_mb, which counted the duplicate pytorch_model.bin) and its embedding cache"""
import json, os, sys
WIPE = sys.argv[1:]  # model-name substrings whose records (and embedding cache) are re-generated
P = '/tmp/veridyct-emb/results/w3.jsonl'
recs = [json.loads(l) for l in open(P)]
ok = {r['model'] for r in recs if r['task'] == 'speed' and str(r['variant']).startswith('bs=')}
keep = [r for r in recs if not (r['variant'] in ('load_failed', 'run_failed') and r['model'] in ok) and not any(w in r['model'] for w in WIPE)]
print(f'{len(recs)} -> {len(keep)} records; dropped {len(recs) - len(keep)}')
with open(P + '.tmp', 'w') as f:
    for r in keep: f.write(json.dumps(r, ensure_ascii=False) + '\n')
os.replace(P + '.tmp', P)
for w in WIPE:
    for f in os.listdir('/tmp/veridyct-emb/w3/emb'):
        if w in f: os.remove('/tmp/veridyct-emb/w3/emb/' + f); print('removed cache', f)
