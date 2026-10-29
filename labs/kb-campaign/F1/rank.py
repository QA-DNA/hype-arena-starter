"""Rank F1 results: selection = mean points over P80 and P10 per (variant, params); prints top-N per method."""
import json, sys, collections as C
path = sys.argv[1]; topn = int(sys.argv[2]) if len(sys.argv) > 2 else 5
flt = sys.argv[3] if len(sys.argv) > 3 else None
R = C.defaultdict(dict)
for l in open(path):
    r = json.loads(l)
    k = (r["variant"], json.dumps(r["params"], sort_keys=True))
    R[k][r["track"]] = r["metrics"]
rows = []
for (v, p), t in R.items():
    if "P80" in t and "P10" in t:
        if flt and flt not in p: continue
        s = (t["P80"]["points_per_row"] + t["P10"]["points_per_row"]) / 2
        rows.append((s, json.loads(p).get("method", v), p, t))
by = C.defaultdict(list)
for x in sorted(rows, key=lambda x: -x[0]): by[x[1]].append(x)
for m, xs in sorted(by.items(), key=lambda kv: -kv[1][0][0]):
    print(f"== {m}: {len(xs)} configs, best sel {xs[0][0]:.4f}, worst {xs[-1][0]:.4f}")
    for s, _, p, t in xs[:topn]:
        a, b = t["P80"], t["P10"]
        print(f"  {s:.4f} P80 {a['points_per_row']:.4f}/{a['accuracy']:.3f}/ece{a['ece10']:.3f}/fp{a['false_precision']:.2f}/fr{a['false_recall']:.2f}  P10 {b['points_per_row']:.4f}/{b['accuracy']:.3f}/ece{b['ece10']:.3f}/fp{b['false_precision']:.2f}/fr{b['false_recall']:.2f}  {p}")
