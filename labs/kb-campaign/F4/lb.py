"""Tiny leaderboard over F4 result files: mean points over P80 and P10 per (variant, params)."""
import json, sys, collections as C
since = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--since=")]
files = [a for a in sys.argv[1:] if not a.startswith("--")]
R = C.defaultdict(dict)
for fn in files:
    for l in open(fn):
        r = json.loads(l)
        if since and r["ts"] < since[0]:
            continue
        k = (r["variant"].split("/")[-1], json.dumps(r["params"], sort_keys=True))
        R[k][r["track"]] = r["metrics"]
rows = []
for k, t in R.items():
    if "P80" in t and "P10" in t:
        rows.append(((t["P80"]["points_per_row"] + t["P10"]["points_per_row"]) / 2, k, t))
for s, k, t in sorted(rows, reverse=True):
    extra = " ".join(f"{tr}={m['points_per_row']:.4f}" for tr, m in sorted(t.items()) if tr not in ("P80", "P10"))
    print(f"{s:.4f} P80={t['P80']['points_per_row']:.4f} P10={t['P10']['points_per_row']:.4f} "
          f"ece={t['P80']['ece10'] or 0:.3f}/{t['P10']['ece10'] or 0:.3f} {k[0]} {k[1][:150]} {extra}")
