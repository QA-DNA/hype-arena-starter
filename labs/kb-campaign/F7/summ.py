"""Summarise F7 results: one row per (variant, params) with P80 / P10 points, accuracy, ECE, false P/R,
selection = mean points over P80 and P10, then any suite tracks. Latest line per (variant, params, track) wins.
  python -I F7/summ.py [results files...] [--tracks Sdev-jt,Sdev-jr,...]"""
import glob
import json
import os
import sys

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
tracks = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--tracks=")), [])
files = args or sorted(glob.glob(os.path.join(KBC, "results", "F7*.jsonl")))
rec = {}
for f in files:
    for line in open(f):
        r = json.loads(line)
        k = (r["variant"], json.dumps(r["params"], sort_keys=True))
        rec.setdefault(k, {})[r["track"]] = r
rows = []
for (v, p), t in rec.items():
    if "P80" in t and "P10" in t:
        sel = (t["P80"]["metrics"]["points_per_row"] + t["P10"]["metrics"]["points_per_row"]) / 2
    else:
        sel = float("nan")
    rows.append((sel, v, p, t))
rows.sort(key=lambda x: -x[0] if x[0] == x[0] else 9)
f3 = lambda x: "  -  " if x is None else f"{x:.3f}"  # noqa: E731
print(f"{'sel':>6} {'P80pts':>6} {'acc':>5} {'ece':>5} {'fP':>5} {'fR':>5} | {'P10pts':>6} {'acc':>5} {'ece':>5} {'fP':>5} {'fR':>5} | "
      + " ".join(f"{t:>10}" for t in tracks) + "  variant params")
for sel, v, p, t in rows:
    cells = []
    for tr in ("P80", "P10"):
        m = t.get(tr, {}).get("metrics")
        cells.append(" ".join(f3(m[k]) if m else "  -  " for k in ("points_per_row", "accuracy", "ece10", "false_precision", "false_recall")))
    sx = " ".join(f"{t[tr]['metrics']['points_per_row']:>10.3f}" if tr in t else f"{'-':>10}" for tr in tracks)
    name = v.replace("F7/", "").replace(".py:Variant", "")
    print(f"{f3(sel) if sel == sel else '  -  ':>6} {cells[0]} | {cells[1]} | {sx}  {name} {p}")
