import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import numpy as np
from collections import Counter
rows, lex = H.load()
byidx = {r['idx']: r for r in rows}
sf = H.single_fact_rows(rows)
tf = [r for r in sf if r['label'] in ('true', 'false')]
NA = H.nearest_anchors(rows, k=2)
cov = [r for r in tf if NA[r['idx']]]
print('single-fact true/false:', len(tf), Counter(r['label'] for r in tf), '| with >=1 anchor:', len(cov), Counter(r['label'] for r in cov))
print('anchor pairs total:', sum(len(NA[r['idx']]) for r in cov), 'mean/row', np.mean([len(NA[r['idx']]) for r in cov]))
# nearest anchor same_value by label
c = Counter((r['label'], NA[r['idx']][0]['same_value']) for r in cov); print('nearest-anchor (label, same_value):', dict(c))
# how many false rows have an anchor with a different gold value at all
print('false rows covered:', sum(r['label']=='false' for r in cov), 'of', sum(r['label']=='false' for r in tf))
P = H.same_key_pairs(rows)
print('conflict pairs', len(P), 'same', sum(p[2] for p in P))
kc = Counter(); kd = Counter()
for i, j, s in P:
    k = byidx[i]['facts'][0]['value']['kind']
    kc[k] += 1; kd[k] += (not s)
print('by kind (n, n_differ):', {k: (kc[k], kd[k]) for k in kc})
lab = Counter((byidx[i]['label'], byidx[j]['label'], s) for i, j, s in P); print(lab)
cands = [len(H.candidates(lex, r['facts'][0]['subject'])) for r in sf]
print('attr: rows', len(sf), 'mean cands', np.mean(cands), 'total pairs', sum(cands), 'unrestricted rows', sum(c == 0 for c in cands))
tl = [len(r['text'].split()) for r in sf]; print('words/row mean', np.mean(tl), 'p95', np.percentile(tl, 95), 'max', max(tl))
# a few examples of pairs
for i, j, s in P[:5]: print(s, '|', byidx[i]['text'], '||', byidx[j]['text'])
# attr words example
s0 = sf[0]['facts'][0]; print(s0['subject'], H.candidates(lex, s0['subject'])[:6])
