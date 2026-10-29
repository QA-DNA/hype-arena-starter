"""Selection scores of P3 results (results/P3*.jsonl, latest per (params, track)). usage: sel.py [filter-substring] [--top N] [--tracks a,b]"""
import glob, json, os, sys
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
flt = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else ""
top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 40
tr = sys.argv[sys.argv.index("--tracks") + 1].split(",") if "--tracks" in sys.argv else []
R = {}
for p in glob.glob(os.path.join(KBC, "results", "P3-remote.jsonl" if "--mac" not in sys.argv else "P3.jsonl")):
    if p.endswith("errors.jsonl") or "paired" in p:
        continue
    for l in open(p):
        r = json.loads(l)
        k = (r["variant"], json.dumps(r["params"], sort_keys=True))
        d = R.setdefault(k, {})
        if r["track"] not in d or r["ts"] >= d[r["track"]]["ts"]:
            d[r["track"]] = r
out = []
for (v, p), d in R.items():
    if flt and flt not in v + p:
        continue
    if "P80" in d and "P10" in d:
        m = lambda t, k: d[t]["metrics"][k]
        s = (m("P80", "points_per_row") + m("P10", "points_per_row")) / 2
        e = (m("P80", "ece10") + m("P10", "ece10")) / 2
        out.append((s, e, m("P80", "points_per_row"), m("P10", "points_per_row"), d["P10"].get("metrics_std", {}).get("points_per_row"),
                    [round(d[t]["metrics"]["points_per_row"], 4) if t in d else None for t in tr], v.split("/")[-1], p,
                    round(d["P80"]["runtime_s"] + d["P10"]["runtime_s"], 1)))
out.sort(key=lambda x: (-x[0], x[1]))
for x in out[:top]:
    print(f"{x[0]:.4f} ece {x[1]:.4f} P80 {x[2]:.4f} P10 {x[3]:.4f}+-{x[4] or 0:.4f} {x[5] if tr else ''} rt {x[8]} {x[6]} {x[7]}")
