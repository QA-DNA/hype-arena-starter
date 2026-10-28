import sys, json, re, time
sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w7')
import harness as H, values as V
from collections import Counter, defaultdict
rows, lex = H.load()
def noop(v): return {k: x for k, x in v.items() if k != 'op'}
t0 = time.time()
cand = {r['idx']: V.extract_values(r['text'], lex) for r in rows}
print('extract secs', round(time.time() - t0, 2))
stat = defaultdict(lambda: [0, 0, 0])
fails = defaultdict(list)
ncand = Counter()
for r in rows:
    C = cand[r['idx']]
    for f in r['facts']:
        g = f['value']; k = g['kind']
        strict = any(H.value_equal(c['value'], g) for c in C)
        len_ = any(H.value_equal(noop(c['value']), noop(g)) for c in C)
        st = stat[k]; st[0] += 1; st[1] += strict; st[2] += len_
        if not len_: fails[k].append((r, f, C))
for k, (n, s, l) in sorted(stat.items()):
    print(f'{k:9s} n={n:4d} strict={s/n:.3f} lenient={l/n:.3f}')
tot = [sum(v[i] for v in stat.values()) for i in range(3)]
print('ALL', tot[0], f'{tot[1]/tot[0]:.3f} {tot[2]/tot[0]:.3f}', 'cands/row', sum(len(c) for c in cand.values())/len(rows), 'gold/row', tot[0]/len(rows))
which = sys.argv[1] if len(sys.argv) > 1 else None
lim = int(sys.argv[2]) if len(sys.argv) > 2 else 15
for k, L in fails.items():
    if which and k != which: continue
    print('=====', k, len(L))
    for r, f, C in L[:lim]:
        mine = [ (c['kind'], json.dumps({a:b for a,b in c['value'].items() if a!='kind'}, ensure_ascii=False), c['text']) for c in C if c['kind']==k][:4]
        print(f"{r['id']:7s} {f['attribute']:24s} gold={json.dumps(f['value'], ensure_ascii=False)} | {r['text'][:140]}\n          mine={mine}")
