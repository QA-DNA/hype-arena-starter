"""Isotonic confidence calibration fitted on dev targets only, then applied unchanged to
every other world of the same run. Labels never change; only true/false confidences.
Usage: python -I calibrate.py --run gold-point [--fit-world dev] [--worker A]
Reads preds/<run>/<world>.csv, writes preds/<run>-iso/<world>.csv, appends to results/e2e.jsonl
with engine "<engine>+iso"."""
import argparse, datetime, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score, suite, truth  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True, help="<tag>-<engine> directory under preds/")
ap.add_argument("--fit-world", default="dev")
ap.add_argument("--worker", default="A")
a = ap.parse_args()
src = os.path.join(suite.OUT, "preds", a.run)
targets, labels, _ = score.load_gold(a.fit_world)
preds, _ = score.read_preds(os.path.join(src, f"{a.fit_world}.csv"))
xs, ys = [], []
for t in targets:
    lab, c = preds.get(t, ("unsure", None))
    if lab != "unsure" and c is not None:
        xs.append(c); ys.append(float(lab == labels[t]))
iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(xs, ys)
latest = {}
for line in open(os.path.join(suite.OUT, "results", "e2e.jsonl")):
    r = json.loads(line)
    latest[(os.path.basename(os.path.dirname(r["pred"])), r["world"])] = r
for path in sorted(glob.glob(os.path.join(src, "*.csv"))):
    w = os.path.basename(path)[:-4]
    p, _ = score.read_preds(path)
    rows = [(rid, lab, None if c is None else round(float(iso.predict([c])[0]), 4)) for rid, (lab, c) in p.items()]
    out = os.path.join(suite.OUT, "preds", a.run + "-iso", f"{w}.csv")
    truth.write_preds(rows, out)
    m = score.score(w, out)
    base = latest.get((a.run, w), {})
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "worker": a.worker,
           "tag": base.get("tag", a.run), "engine": base.get("engine", "?") + "+iso", "world": w, "n_targets": m["n"],
           "runtime_s": base.get("runtime_s"), "forms": base.get("forms"), "pred": out, "metrics": m,
           "note": f"isotonic fitted on {a.fit_world} targets ({len(xs)} decided rows)"}
    with open(os.path.join(suite.OUT, "results", "e2e.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"{a.run}+iso {w:9s} ece10 {base.get('metrics', {}).get('ece10')} -> {m['ece10']}")
