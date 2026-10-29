"""Paired per-fold points on the selection tracks (P80 5 folds, P10 10 seeds), exactly the harness splits and
scoring (world.load_track, metrics.compute). One line per (config, track) in results/P3-paired.jsonl with
track 'pairedP80' / 'pairedP10' (pooled metrics as run.py computes them) and 'fold_points' (per fold / seed).

  python -I P3/paired.py run CONFIGS.json [--jobs 2]      # CONFIGS: list of [spec, params]
  python -I P3/paired.py se BASE_INDEX CONFIGS.json         # paired SE of the selection-score difference
"""
import json
import multiprocessing as mp
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KBC = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(KBC, "harness"))
OUT = os.path.join(KBC, "results", "P3-paired.jsonl")


def job(a):
    spec, params, tname = a
    os.chdir(KBC)
    import numpy as np
    import metrics as M
    from api import check_prediction, resolve, run_variant
    from world import load_track
    t = load_track(tname)
    cls, _ = resolve(spec, "Variant")
    pts, G, P, C, per = [], [], [], [], []
    for w, gold, sc in t.folds:
        p = check_prediction(w, run_variant(cls(**params), w, t.train))
        m = M.compute(gold, p.labels[sc], p.conf[sc])
        per.append(m); pts.append(m["points_per_row"])
        G.append(gold); P.append(p.labels[sc]); C.append(p.conf[sc])
    met = M.compute(np.concatenate(G), np.concatenate(P), np.concatenate(C)) if tname == "P80" else M.mean_std(per)[0]
    return {"worker": "P3-paired", "variant": spec, "params": params, "track": "paired" + tname,
            "metrics": met, "fold_points": pts, "fold_n": [len(g) for g in G]}


def djob(a):
    """Denoise check: one extra split (F5/paired.py splits: P80 reps 1.. = permuted page folds, P10 seeds 10..)."""
    spec, params, sname, lab_pages = a
    os.chdir(KBC)
    import numpy as np
    import metrics as M
    from api import check_prediction, resolve, run_variant
    from world import practice_full
    _, base, gold = practice_full()
    lab = lab_pages[base.page]
    w = base.with_labels(lab, gold)
    sc = np.where(~lab)[0]
    p = check_prediction(w, run_variant(resolve(spec, "Variant")[0](**params), w))
    m = M.compute(gold[sc], p.labels[sc], p.conf[sc])
    rp = np.where(p.labels[sc] == gold[sc], 1, np.where(p.labels[sc] != "unsure", -1, 0))
    return {"worker": "P3-paired", "variant": spec, "params": params, "track": "denoise", "split": sname,
            "metrics": m, "fold_points": [m["points_per_row"]], "fold_n": [len(sc)],
            "row_points": rp.tolist(), "row_page": base.page[sc].tolist()}


def load():
    rows = {}
    for line in open(OUT):
        r = json.loads(line)
        rows[(r["variant"], json.dumps(r["params"], sort_keys=True), r["track"])] = r
    return rows


def sel_points(r80, r10):
    return (r80["metrics"]["points_per_row"] + r10["metrics"]["points_per_row"]) / 2


def main():
    cmd = sys.argv[1]
    if cmd == "run":
        cfgs = json.load(open(sys.argv[2]))
        jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 2
        todo = [(s, p, t) for s, p in cfgs for t in ("P80", "P10")]
        fd = os.open(OUT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        with mp.get_context("spawn").Pool(jobs, maxtasksperchild=1) as pool:
            for rec in pool.imap_unordered(job, todo):
                os.write(fd, (json.dumps(rec) + "\n").encode())
                print(rec["variant"], json.dumps(rec["params"]), rec["track"], round(rec["metrics"]["points_per_row"], 4), flush=True)
    elif cmd == "drun":  # python -I P3/paired.py drun CONFIGS.json --jobs 2 [--reps 4 --seeds 30]
        sys.path.insert(0, os.path.join(KBC, "F5"))
        from paired import splits as f5splits  # noqa: F401 (F5/paired.py, read-only)
        cfgs = json.load(open(sys.argv[2]))
        arg = lambda k, d: int(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
        from world import practice_full
        _, base, _ = practice_full()
        sp = [(n, l) for n, l in f5splits(base.n_pages, arg("--reps", 4), arg("--seeds", 30))
              if not n.startswith("P80r0") and not (n.startswith("P10s") and int(n[4:]) < 10)]  # fresh splits only
        todo = [(s_, p_, n, l) for s_, p_ in cfgs for n, l in sp]
        fd = os.open(OUT.replace("P3-paired", "P3-denoise2"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        with mp.get_context("spawn").Pool(arg("--jobs", 2), maxtasksperchild=8) as pool:
            for rec in pool.imap_unordered(djob, todo):
                os.write(fd, (json.dumps(rec) + "\n").encode())
    elif cmd == "dse":  # python -I P3/paired.py dse BASE_INDEX CONFIGS.json
        import numpy as np
        b = int(sys.argv[2]); cfgs = json.load(open(sys.argv[3]))
        R = {}
        for line in open(OUT.replace("P3-paired", "P3-denoise")):
            r = json.loads(line)
            R[(r["variant"], json.dumps(r["params"], sort_keys=True), r["split"])] = r["metrics"]["points_per_row"]
        key = lambda c: (c[0], json.dumps(c[1], sort_keys=True))  # noqa: E731
        sb = {sp: v for (s_, p_, sp), v in R.items() if (s_, p_) == key(cfgs[b])}
        for c in cfgs:
            sc = {sp: v for (s_, p_, sp), v in R.items() if (s_, p_) == key(c)}
            out = []
            for pre in ("P80", "P10"):
                common = sorted(k for k in sc if k in sb and k.startswith(pre))
                d = np.array([sc[k] - sb[k] for k in common])
                m = np.array([sc[k] for k in common])
                out.append((pre, len(d), m.mean() if len(m) else float("nan"), d.mean() if len(d) else float("nan"),
                            d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else float("nan")))
            sel = (out[0][2] + out[1][2]) / 2; dd = (out[0][3] + out[1][3]) / 2; se = 0.5 * np.hypot(out[0][4], out[1][4])
            print(f"sel {sel:.4f} diff {dd:+.4f} se {se:.4f} | " + " ".join(f"{p} n{n} {m:.4f} {d:+.4f}+-{e:.4f}" for p, n, m, d, e in out)
                  + f" | {c[0]} {json.dumps(c[1], sort_keys=True)}")
    else:
        import numpy as np
        b = int(sys.argv[2]); cfgs = json.load(open(sys.argv[3])); rows = load()

        def get(s, p, t):
            return rows.get((s, json.dumps(p, sort_keys=True), "paired" + t))
        bs, bp = cfgs[b]
        B80, B10 = get(bs, bp, "P80"), get(bs, bp, "P10")
        for s, p in cfgs:
            r80, r10 = get(s, p, "P80"), get(s, p, "P10")
            if not (r80 and r10):
                print("missing", s, p); continue
            n80 = np.array(r80["fold_n"], float)
            d80 = np.array(r80["fold_points"]) - np.array(B80["fold_points"])
            d10 = np.array(r10["fold_points"]) - np.array(B10["fold_points"])
            # pooled P80 diff = n-weighted mean of fold diffs; SE from the weighted per-fold spread
            w = n80 / n80.sum()
            m80 = float(w @ d80); se80 = float(np.sqrt(np.sum(w ** 2 * (d80 - m80) ** 2) * len(w) / (len(w) - 1)))
            m10 = float(d10.mean()); se10 = float(d10.std(ddof=1) / np.sqrt(len(d10)))
            diff = (m80 + m10) / 2; se = 0.5 * np.sqrt(se80 ** 2 + se10 ** 2)
            print(f"{sel_points(r80, r10):.4f} diff {diff:+.4f} se {se:.4f} (P80 {m80:+.4f}+-{se80:.4f}, "
                  f"P10 {m10:+.4f}+-{se10:.4f}) {s} {json.dumps(p, sort_keys=True)}")


if __name__ == "__main__":
    main()
