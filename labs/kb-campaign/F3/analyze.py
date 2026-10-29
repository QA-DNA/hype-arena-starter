"""Summarise F3 results: selection = mean points over P80 and P10 (latest line per variant/params/track).
python analyze.py [results.jsonl ...] [--top N] [--filter key=value ...] [--suite]"""
import json
import os
import sys
from collections import defaultdict

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(paths):
    rec = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in open(p):
            r = json.loads(line)
            key = (r["variant"], json.dumps(r["params"], sort_keys=True), r["track"])
            rec[key] = r
    return rec


def table(rec, flt=(), top=40, suite=False):
    by = defaultdict(dict)
    for (v, p, t), r in rec.items():
        by[(v, p)][t] = r
    rows = []
    for (v, p), ts in by.items():
        if "P80" not in ts or "P10" not in ts:
            continue
        prm = json.loads(p)
        if any(str(prm.get(k)) != val for k, val in flt):
            continue
        a, b = ts["P80"]["metrics"], ts["P10"]["metrics"]
        sel = (a["points_per_row"] + b["points_per_row"]) / 2
        rows.append((sel, v, prm, a, b, ts))
    rows.sort(key=lambda x: (-x[0], (x[3]["ece10"] or 1) + (x[4]["ece10"] or 1)))
    print(f"{len(rows)} configs with P80+P10")
    print("| # | sel | P80 pts | P80 acc | P80 ECE | P80 Brier | P80 F-P/R | P10 pts (sd) | P10 acc | P10 ECE | P10 Brier | P10 F-P/R | variant | params |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for n, (sel, v, prm, a, b, ts) in enumerate(rows[:top]):
        sd = ts["P10"].get("metrics_std", {}).get("points_per_row")
        f = lambda x: "-" if x is None else f"{x:.3f}"  # noqa
        print(f"| {n+1} | {sel:.4f} | {a['points_per_row']:.4f} | {a['accuracy']:.3f} | {f(a['ece10'])} | {f(a['brier'])} | "
              f"{f(a['false_precision'])}/{f(a['false_recall'])} | {b['points_per_row']:.4f} ({f(sd)}) | {b['accuracy']:.3f} | "
              f"{f(b['ece10'])} | {f(b['brier'])} | {f(b['false_precision'])}/{f(b['false_recall'])} | {v.split('/')[-1]} | "
              f"`{json.dumps(prm, separators=(',', ':'))}` |")
        if suite:
            st = {t: r["metrics"]["points_per_row"] for t, r in ts.items() if t not in ("P80", "P10")}
            if st:
                print("|  | suite: " + " ".join(f"{t}={x:.3f}" for t, x in sorted(st.items())) + " |")
    return rows


if __name__ == "__main__":
    args = sys.argv[1:]
    top, flt, suite, paths = 40, [], False, []
    i = 0
    while i < len(args):
        if args[i] == "--top":
            top = int(args[i + 1]); i += 2; continue
        if args[i] == "--filter":
            k, _, val = args[i + 1].partition("="); flt.append((k, val)); i += 2; continue
        if args[i] == "--suite":
            suite = True; i += 1; continue
        paths.append(args[i]); i += 1
    if not paths:
        paths = [os.path.join(KBC, "results", f) for f in ("F3-remote.jsonl", "F3.jsonl")]
    table(load(paths), flt, top, suite)
