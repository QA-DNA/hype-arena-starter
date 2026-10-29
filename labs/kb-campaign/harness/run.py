"""Run variants x param grids x tracks; append one JSON line per (variant, params, track) to
$KBC_RESULTS_DIR/<worker>.jsonl. See API.md.

  python -I run.py --variant v9='{"model": ["lr", "hgb"]}' --variant always_true --tracks P80,P10,Sdev-jt \
      --jobs 4 --worker F3
Selection tracks: P80, P10. Every suite track is a test track.
"""
import argparse
import datetime
import hashlib
import itertools
import json
import multiprocessing as mp
import os
import resource
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def expand(grid):
    if grid is None:
        return [{}]
    if isinstance(grid, list):
        return [dict(g) for g in grid]
    keys = sorted(grid)
    vals = [v if isinstance(v, list) else [v] for v in (grid[k] for k in keys)]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def src_hash(spec, params):
    from api import resolve
    files = [resolve(spec, "Variant")[1]]
    files += [resolve(s, "features")[1] for s in params.get("extra_features", ())]
    h = hashlib.sha256()
    for f in files:
        h.update(open(f, "rb").read())
    return h.hexdigest()[:12]


def peak_rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / 2**20 if sys.platform == "darwin" else r / 1024, 1)


def job(args):
    spec, params, track_name, worker = args
    import numpy as np
    import metrics as M
    from api import check_prediction, resolve, run_variant
    from world import load_track
    t0 = time.perf_counter()
    track = load_track(track_name)
    load_s = time.perf_counter() - t0
    cls, _ = resolve(spec, "Variant")
    run_s, per, golds, preds, confs, chosen = 0.0, [], [], [], [], []
    for world, gold, sc in track.folds:
        v = cls(**params)
        t1 = time.perf_counter()
        p = check_prediction(world, run_variant(v, world, track.train))
        run_s += time.perf_counter() - t1
        if getattr(v, "chosen", None):
            chosen.append([list(c) for c in v.chosen])
        g, pr, c = gold, p.labels[sc], p.conf[sc]
        per.append(M.compute(g, pr, c))
        golds.append(g); preds.append(pr); confs.append(c)
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "worker": worker, "variant": spec,
           "params": params, "track": track_name, "n_scored": int(sum(len(g) for g in golds))}
    if track.kind == "seeds":
        rec["metrics"], rec["metrics_std"] = M.mean_std(per)
    else:
        rec["metrics"] = M.compute(np.concatenate(golds), np.concatenate(preds), np.concatenate(confs))
        if track.kind == "pooled":
            rec["fold_mean"] = M.mean_std(per)[0]
    rec.update(runtime_s=round(run_s, 3), load_s=round(load_s, 3), peak_rss_mb=peak_rss_mb(),
               src_hash=src_hash(spec, params), host=socket.gethostname(), n_folds=len(track.folds),
               world_stats=track.folds[0][0].stats)
    if chosen:
        rec["chosen"] = chosen
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", action="append", required=True, metavar="NAME[=GRID_JSON]")
    ap.add_argument("--tracks", default="P80,P10")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--worker", default="W0")
    ap.add_argument("--dry", action="store_true", help="print the job list and exit")
    a = ap.parse_args()
    from world import RESULTS_DIR, parse_track
    tracks = [t.strip() for t in a.tracks.split(",") if t.strip()]
    for t in tracks:
        parse_track(t)
    jobs = []
    for v in a.variant:
        spec, _, grid = v.partition("=")
        for params in expand(json.loads(grid) if grid else None):
            jobs += [(spec, params, t, a.worker) for t in tracks]
    if a.dry:
        for j in jobs:
            print(j)
        return
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(var, "1")  # one thread per job unless the caller says otherwise
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"{a.worker}.jsonl")
    ctx = mp.get_context("spawn")
    fails = 0
    fd = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    efd = None
    with ctx.Pool(max(1, min(a.jobs, len(jobs))), maxtasksperchild=1) as pool:
        for rec in pool.imap_unordered(_safe_job, jobs):
            if "error" in rec:
                fails += 1
                print("FAILED", rec["job"], rec["trace"], file=sys.stderr, flush=True)
                if efd is None:
                    efd = os.open(os.path.join(RESULTS_DIR, f"{a.worker}.errors.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
                rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
                os.write(efd, (json.dumps(rec) + "\n").encode())
                continue
            os.write(fd, (json.dumps(rec) + "\n").encode())  # one O_APPEND write per line: safe across invocations
            m = rec["metrics"]
            print(f"{rec['variant']} {json.dumps(rec['params'])} {rec['track']}: acc={m['accuracy']:.4f} "
                  f"mf1={m['macro_f1']:.4f} pts={m['points_per_row']:.4f} ece={m['ece10'] if m['ece10'] is None else round(m['ece10'], 4)} "
                  f"cov={m['coverage']:.4f} run={rec['runtime_s']:.1f}s load={rec['load_s']:.1f}s rss={rec['peak_rss_mb']}MB",
                  flush=True)
    print(f"{len(jobs) - fails}/{len(jobs)} jobs -> {out}")
    sys.exit(1 if fails else 0)


def _safe_job(args):
    try:
        return job(args)
    except Exception as e:  # a broken variant must not kill the other jobs
        import traceback
        return {"job": list(args), "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


if __name__ == "__main__":
    main()
