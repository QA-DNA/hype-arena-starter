import json, sys
d = json.load(open('eng_v2_scores.json'))
meta = {t['name']: t['type'] for t in d['tasksMeta']}
rows = {r['model']['name']: r for r in d['rows']}
cands = [l.strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith('#')]
missing=[c for c in cands if c not in rows]
print("not on leaderboard:", missing)
cands=[c for c in cands if c in rows]
def common(types):
    ts=[t for t,ty in meta.items() if ty in types]
    ok=[t for t in ts if all(rows[c]['scoresByTask'].get(t) is not None for c in cands)]
    return ok
for label,types in [('STS+PairCl',{'STS','PairClassification'}),('Classification',{'Classification'}),('Clustering',{'Clustering'}),('Retrieval',{'Retrieval'})]:
    ok=common(types)
    print(f"\n### {label}: {len(ok)} common tasks: {ok}")
    res=[]
    for c in cands:
        v=[rows[c]['scoresByTask'][t] for t in ok]
        res.append((sum(v)/len(v)*100 if v else 0,c))
    for s,c in sorted(res,reverse=True)[:int(sys.argv[2])]:
        r=rows[c]
        print(f"{s:.2f} | {c} | {r.get('totalParamsB')}B | mean={r['meanTask']}")
