import json
d = json.load(open('eng_v2_scores.json'))
meta = {t['name']: t['type'] for t in d['tasksMeta']}
out=[]
for r in d['rows']:
    m=r['model']
    p=r.get('totalParamsB')
    rel=m.get('releaseDate') or ''
    if p is None or p>=1.1 or rel < '2025-01-01': continue
    st={k:v for k,v in r['scoresByTask'].items() if v is not None}
    pm=sum(st.values())/len(st)*100 if st else 0
    sts=[v for k,v in st.items() if meta[k]=='STS']
    out.append((r['meanTask'] or 0, pm, len(st), m['name'], p, r.get('embeddingDim'), r.get('maxTokens'), m.get('license'), rel, r.get('zeroShotPct'), (sum(sts)/len(sts)*100 if sts else 0), len(sts), m.get('openWeights')))
out.sort(key=lambda x:-(x[0] or x[1]))
for o in out:
    print(f"mean={o[0]*100:.2f} partial={o[1]:.2f}({o[2]}) | {o[3]} | {o[4]:.3f}B | dim={o[5]} | max={o[6]} | {o[7]} | {o[8]} | zs={o[9]} | STS={o[10]:.1f}({o[11]}) | ow={o[12]}")
print(len(out))
