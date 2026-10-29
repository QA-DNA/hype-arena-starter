"""End-to-end: forms -> truth engine -> predictions -> score -> results/e2e.jsonl.

Usage: python -I e2e.py --forms-dir /tmp/veridyct-evalsuite/forms/<extractor> --tag <name>
                        [--engine interval|point] [--worlds dev,cal,...] [--worker B]
Runs every world (or the --worlds subset) that has <forms-dir>/<world>.jsonl.
Writes preds/<tag>-<engine>/<world>.csv and appends one JSON line per world to
results/e2e.jsonl. --engine always-true ignores forms (baseline; needs --worlds).
"""
import argparse
import datetime
import json
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score  # noqa: E402
import suite  # noqa: E402
import truth  # noqa: E402

RESULTS = os.path.join(suite.OUT, "results", "e2e.jsonl")
HEADLINE = ("accuracy", "macro_f1", "balanced_accuracy", "points_per_row", "coverage", "ece10")


def always_true(world):
    return [(r["id"], "true", 1.0) for r in suite.read_universe(world) if r["label"] == ""]


def run(world, forms_dir, tag, engine, worker):
    forms = os.path.join(forms_dir, f"{world}.jsonl") if forms_dir else None
    t0 = time.perf_counter()
    rows = always_true(world) if engine == "always-true" else truth.predict(world, forms, engine)
    runtime = time.perf_counter() - t0
    pred_path = os.path.join(suite.OUT, "preds", f"{tag}-{engine}", f"{world}.csv")
    truth.write_preds(rows, pred_path)
    m = score.score(world, pred_path)
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "worker": worker, "tag": tag,
           "engine": engine, "world": world, "n_targets": m["n"], "runtime_s": round(runtime, 3),
           "forms": forms, "pred": pred_path, "metrics": m}
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    pc = m["per_class"]
    print(f"{tag}-{engine} {world:9s} n={m['n']:6d} " + " ".join(f"{k}={m[k]:.4f}" for k in HEADLINE if m[k] is not None)
          + f" falseP/R={pc['false']['precision']:.4f}/{pc['false']['recall']:.4f}"
          + f" unsureP/R={pc['unsure']['precision']:.4f}/{pc['unsure']['recall']:.4f} t={runtime:.2f}s", flush=True)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forms-dir")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--engine", choices=("interval", "point", "point-jitter", "always-true"), default="interval")
    ap.add_argument("--worlds", help="comma list; default: every world with a forms file")
    ap.add_argument("--worker", help="recorded in results (default: the tag)")
    a = ap.parse_args()
    if a.engine != "always-true" and not a.forms_dir:
        ap.error("--forms-dir is required for this engine")
    worlds = a.worlds.split(",") if a.worlds else list(suite.WORLDS)
    bad = [w for w in worlds if w not in suite.WORLDS]
    if bad:
        ap.error(f"unknown worlds {bad}; known: {','.join(suite.WORLDS)}")
    ran = 0
    for w in worlds:
        if a.engine != "always-true" and not os.path.exists(os.path.join(a.forms_dir, f"{w}.jsonl")):
            if a.worlds:
                print(f"skip {w}: no {w}.jsonl in {a.forms_dir}", file=sys.stderr)
            continue
        run(w, a.forms_dir, a.tag, a.engine, a.worker or a.tag)
        ran += 1
    if not ran:
        sys.exit("no world ran (no matching forms files)")


if __name__ == "__main__":
    main()
