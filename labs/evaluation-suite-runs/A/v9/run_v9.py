"""V9 (copied from labs/kb-experiments, DATA patched) trained on a world's anchors,
predicting its targets from a forms file (interval ignored: V9 is date/point based).
Usage: python -I run_v9.py --world dev --forms /tmp/veridyct-evalsuite/forms/gold/dev.jsonl [--model lr]"""
import argparse, csv, datetime, json, os, sys, time
for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[v] = "4"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import score, suite, truth  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--world", required=True)
ap.add_argument("--forms", required=True)
ap.add_argument("--model", default="lr")
ap.add_argument("--tag", default="gold")
a = ap.parse_args()

data = os.path.join(HERE, f"data-{a.world}")
os.makedirs(data, exist_ok=True)
uni = suite.read_universe(a.world)
forms = {}
for r in suite.read_jsonl(a.forms):
    forms.setdefault(r["id"], r)
idmap, n, prev_anchor = {}, 0, None
with open(os.path.join(data, "practice.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "text", "date", "label", "form"])
    for r in uni:
        anchor = r["label"] != ""
        n += 1 + (prev_anchor is not None and anchor != prev_anchor)  # id gap => page break
        prev_anchor = anchor
        form = [{k: x[k] for k in ("subject", "attribute", "value")} for x in (forms.get(r["id"]) or {}).get("assertions", [])]
        pid = f"p-{n}"
        idmap[pid] = r["id"]
        w.writerow([pid, r["text"], r["date"], r["label"], json.dumps(form)])
with open(suite.public_path(a.world, "lexicon.json"), encoding="utf-8") as src, open(os.path.join(data, "lexicon.json"), "w") as dst:
    dst.write(src.read())

os.environ["V9_DATA"] = data
sys.path.insert(0, os.path.join(HERE, "kb"))
t0 = time.perf_counter()
import numpy as np  # noqa: E402
import v9  # noqa: E402  (exp loads ROWS from V9_DATA at import)
lab = np.zeros(v9.NP, bool)
for r in v9.ROWS:
    if r["label"]:
        lab[r["page"]] = True
fn = v9.v9(a.model)
out, conf = fn(lab)
runtime = time.perf_counter() - t0
rows = []
n_trunc = int(sum(str(x) == "unsur" for x in out))
for r, lbl, c in zip(v9.ROWS, out, conf):
    lbl = "unsure" if str(lbl) == "unsur" else str(lbl)  # V9 decide(): '<U5' array truncates 'unsure'
    if not r["label"]:
        rows.append((idmap[r["id"]], str(lbl), None if lbl == "unsure" else round(float(min(max(c, 0.0), 1.0)), 4)))
tag, engine = a.tag, f"v9{a.model}"
pred = os.path.join(suite.OUT, "preds", f"{tag}-{engine}", f"{a.world}.csv")
truth.write_preds(rows, pred)
m = score.score(a.world, pred)
rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "worker": "A", "tag": tag, "engine": engine,
       "world": a.world, "n_targets": m["n"], "runtime_s": round(runtime, 3), "forms": a.forms, "pred": pred,
       "metrics": m, "note": f"V9 chosen (t, band, gap): {v9.CHOSEN[-1] if v9.CHOSEN else None}; 'unsur' truncations mapped: {n_trunc}"}
with open(os.path.join(suite.OUT, "results", "e2e.jsonl"), "a") as f:
    f.write(json.dumps(rec) + "\n")
pc = m["per_class"]
print(f"{tag}-{engine} {a.world} acc={m['accuracy']:.4f} mf1={m['macro_f1']:.4f} pts={m['points_per_row']:.4f} "
      f"falseP/R={pc['false']['precision']:.4f}/{pc['false']['recall']:.4f} unsureP/R={pc['unsure']['precision']:.4f}/{pc['unsure']['recall']:.4f} "
      f"ece={m['ece10']} t={runtime:.1f}s chosen={rec['note']}")
