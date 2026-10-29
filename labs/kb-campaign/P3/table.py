"""Report tables from results/P3-remote.jsonl (latest line per (variant, params, track)).
  python -I P3/table.py sel        # P80 / P10 full metrics for the finalists + references
  python -I P3/table.py suite      # every S / X track (points per row), jt and jr side by side
  python -I P3/table.py f6         # F6 cells (points) for the P3 configs
"""
import json
import os
import sys

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = {"d0": 0.03, "engine": "viterbi", "eps_a": 0.0005, "mono": "fit", "mono_a": 10, "pi_o": 1, "vote_lr": 48}
D, W = "F1/plugins.py:td_post#0", "F5/fp.py:w_nds"
CFG = [  # (short name, variant, params)
    ("a  F2#1 chain", "F2/f2var.py:Chain", CH),
    ("a' Stack chain", "P3/p3.py:Stack", {"oofmap": False}),
    ("b  +dyn", "P3/p3.py:Stack", {"C": 1.0, "feats": [D]}),
    ("c  +dyn+wnds", "P3/p3.py:Stack", {"C": 1.0, "feats": [D, W]}),
    ("d  c+dedup", "P3/p3.py:Stack", {"C": 1.0, "dedup": True, "feats": [D, W]}),
    ("e  chain+dedup", "P3/p3.py:Stack", {"oofmap": False, "dedup": True}),
    ("f  chain+wnds", "P3/p3.py:Stack", {"C": 1.0, "feats": [W], "oofmap": False}),
    ("c2 c iso:arena3", "P3/p3.py:Stack", {"C": 1.0, "dec": "iso:arena3", "feats": [D, W]}),
    ("c3 c C=3", "P3/p3.py:Stack", {"C": 3.0, "feats": [D, W]}),
    ("c4 c offset", "P3/p3.py:Stack", {"C": 1.0, "feats": [D, W], "offset": True}),
    ("R  F1 D1", "F1/f1var.py:Variant", {"E0": 0.85, "Ea": 0.999, "F0": 0.03, "back": 0.005, "lam": 120.0, "method": "dynworld", "select": "arena"}),
    ("R  F1 D2 dedup", "F1/f1var.py:Variant", {"E0": 0.85, "Ea": 0.999, "F0": 0.03, "back": 0.005, "lam": 120.0, "method": "dynworld", "select": "arena", "dedup": True}),
    ("R  always_true", "always_true", {}),
    ("R  v9 arena", "v9", {"select": "arena"}),
]
R = {}
for line in open(os.path.join(KBC, "results", "P3-remote.jsonl")):
    r = json.loads(line)
    k = (r["variant"], json.dumps(r["params"], sort_keys=True), r["track"])
    if k not in R or r["ts"] >= R[k]["ts"]:
        R[k] = r


def get(v, p, t):
    return R.get((v, json.dumps(p, sort_keys=True), t))


f = lambda x: "-" if x is None else f"{x:.4f}"  # noqa: E731
mode = sys.argv[1] if len(sys.argv) > 1 else "sel"
if mode == "sel":
    print("config | track | points | acc | ECE | macroF1 | false P | false R | coverage")
    for n, v, p in CFG:
        for t in ("P80", "P10"):
            r = get(v, p, t)
            if r:
                m = r["metrics"]
                print(f"{n} | {t} | {f(m['points_per_row'])} | {f(m['accuracy'])} | {f(m['ece10'])} | {f(m['macro_f1'])} | "
                      f"{f(m['false_precision'])} | {f(m['false_recall'])} | {f(m['coverage'])}")
elif mode == "suite":
    worlds = ["dev", "cal", "sealed", "syn", "diag", "pilot", "prac", "extdev", "extcal", "extsealed"]
    for fam in ("S", "X"):
        cols = [f"{fam}{w}-{m}" for w in worlds for m in ("jt", "jr", "nt", "nr")]
        print(f"\n{fam} tracks (points per row): config | " + " | ".join(c[1:] for c in cols))
        for n, v, p in CFG:
            vals = [get(v, p, c) for c in cols]
            print(n + " | " + " | ".join(f(x["metrics"]["points_per_row"]) if x else "-" for x in vals))
elif mode == "f6":
    rows = {}
    for (v, p, t), r in R.items():
        if t.startswith("F6/"):
            rows.setdefault(t, {})[(v, p)] = r["metrics"]["points_per_row"]
    names = [(n, v, json.dumps(p, sort_keys=True)) for n, v, p in CFG]
    filt = sys.argv[2] if len(sys.argv) > 2 else ""
    print("cell | " + " | ".join(n for n, _, _ in names))
    for t in sorted(rows):
        if filt and filt not in t:
            continue
        print(t + " | " + " | ".join(f(rows[t].get((v, p))) for _, v, p in names))
