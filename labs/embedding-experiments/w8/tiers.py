import json, sys
d = json.load(open('eng_v2_scores.json'))
rows = d['rows']
out = []
for r in rows:
    m = r['model']
    out.append(dict(
        name=m['name'], params=r.get('totalParamsB'), act=r.get('activeParamsB'), dim=r.get('embeddingDim'),
        maxtok=r.get('maxTokens'), mean=r.get('meanTask'), mtt=r.get('meanTaskType'),
        zs=r.get('zeroShotPct'), lic=m.get('license'), rel=m.get('releaseDate'),
        ow=m.get('openWeights'), st=m.get('sentenceTransformersCompatible'),
        adapted=m.get('adaptedFrom'), typ=m.get('modelType'), rank=r.get('rank'),
    ))
json.dump(out, open('eng_v2_flat.json','w'))
lo, hi = float(sys.argv[1]), float(sys.argv[2])
sel = [o for o in out if o['params'] is not None and lo <= o['params'] < hi and o['mean'] is not None]
sel.sort(key=lambda o: -o['mean'])
n = int(sys.argv[3])
print("rank | name | paramsB | dim | maxtok | meanTask | meanTT | zs% | license | release | openW | ST")
for o in sel[:n]:
    print(f"{o['rank']} | {o['name']} | {o['params']:.3f} | {o['dim']} | {o['maxtok']} | {o['mean']*100:.2f} | {(o['mtt'] or 0)*100:.2f} | {o['zs']} | {o['lic']} | {o['rel']} | {o['ow']} | {o['st']}")
print("total in tier:", len(sel))
