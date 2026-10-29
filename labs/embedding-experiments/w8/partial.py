import json, sys
d = json.load(open('eng_v2_scores.json'))
meta = {t['name']: t['type'] for t in d['tasksMeta']}
rows = {r['model']['name']: r for r in d['rows']}
names = sys.argv[1:]
for n in names:
    r = rows.get(n)
    if not r: print(n, 'NOT FOUND'); continue
    st = r['scoresByTask']
    have = {k:v for k,v in st.items() if v is not None}
    bytype = {}
    for k,v in have.items():
        bytype.setdefault(meta[k], []).append(v)
    s = ' '.join(f"{t[:6]}={sum(v)/len(v)*100:.1f}({len(v)})" for t,v in sorted(bytype.items()))
    pm = sum(have.values())/len(have)*100 if have else 0
    print(f"{n} | meanTask={r['meanTask']} | partialMean={pm:.2f} over {len(have)}/41 | {s}")
