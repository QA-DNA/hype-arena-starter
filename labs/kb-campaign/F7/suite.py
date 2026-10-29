"""Print suite-track lines of F7 results: track, params, points, accuracy, ECE, false P/R, runtime, RSS."""
import glob, json, os, sys
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for f in [f for f in sorted(glob.glob(os.path.join(KBC, "results", "F7*.jsonl"))) if "errors" not in f]:
    for l in open(f):
        r = json.loads(l)
        if r["track"][0] in "SX":
            m = r["metrics"]
            print(f"{r['track']:12s} {r['variant'].replace('F7/','')[:12]:12s} {json.dumps(r['params'])[:80]:80s} pts={m['points_per_row']:.4f} acc={m['accuracy']:.4f} "
                  f"ece={m['ece10'] if m['ece10'] is None else round(m['ece10'],4)} fP={m['false_precision']:.3f} fR={m['false_recall']:.3f} run={r['runtime_s']:.0f}s rss={r['peak_rss_mb']}")
