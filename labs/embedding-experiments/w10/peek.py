import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import json, collections, random
rows, lex = H.load(); sf = H.single_fact_rows(rows)
print(len(rows), len(sf))
for r in rows[:4]: print(json.dumps({k: r[k] for k in ('idx','id','text','date','label','facts','page')}, ensure_ascii=False)[:600])
kinds = collections.Counter()
for r in sf:
    v = r['facts'][0]['value']
    kinds[v.get('kind') if isinstance(v, dict) else type(v).__name__] += 1
print(kinds)
print(collections.Counter(r['label'] for r in sf))
print(collections.Counter(tuple(sorted(r['facts'][0].keys())) for r in sf))
random.seed(1)
for r in random.sample(sf, 12): print(r['label'], '|', r['text'], '|', json.dumps(r['facts'][0], ensure_ascii=False))
A = H.nearest_anchors(rows, k=2)
tf = [r for r in sf if r['label'] in ('true','false')]
cov = [r for r in tf if A[r['idx']]]
print('single-fact true/false', len(tf), 'with anchors', len(cov), collections.Counter(r['label'] for r in cov))
print('anchor count per row', collections.Counter(min(len(A[r['idx']]),6) for r in cov))
P = H.same_key_pairs(rows)
print(len(P), sum(p[2] for p in P))
sub = collections.Counter(r['facts'][0]['subject'] for r in sf)
print(len(sub), sub.most_common(5))
print(list(lex['subjects'].items())[0])
