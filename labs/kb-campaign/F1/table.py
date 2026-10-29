"""Per-config table over tracks from F1 results files: points/accuracy/ECE per track.
  python -I table.py <params-substring|''> [tracks comma list] [files...]"""
import json, sys, collections as C, glob, os
HERE = os.path.dirname(os.path.abspath(__file__))
sub = sys.argv[1]; tr = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else None
files = sys.argv[3:] or glob.glob(os.path.join(HERE, "..", "results", "F1*.jsonl"))
R = C.defaultdict(dict)
for f in files:
    for l in open(f):
        r = json.loads(l)
        if r.get("worker", "").startswith("F1-stress"): continue
        p = json.dumps(r["params"], sort_keys=True)
        if sub in p: R[p][r["track"]] = r
for p, t in R.items():
    print(p)
    for k in (tr or sorted(t)):
        if k in t:
            m = t[k]["metrics"]
            print(f"   {k:14s} pts {m['points_per_row']:.4f} acc {m['accuracy']:.4f} ece {m['ece10'] if m['ece10'] is None else round(m['ece10'],3)} fP {m['false_precision']:.3f} fR {m['false_recall']:.3f} cov {m['coverage']:.3f} run {t[k]['runtime_s']}s rss {t[k]['peak_rss_mb']}MB")
