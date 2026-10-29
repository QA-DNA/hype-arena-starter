"""Results table from $KBC/results/F2*.jsonl: python -I table.py [--top N] [--filter substr] [--suite] [--md]
Rows = (variant, params, src_hash); selection = mean points P80, P10; suite columns = points per row."""
import argparse
import glob
import json
import os

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = [f"S{w}-{m}{f}" for w in ("dev", "cal", "sealed", "diag", "syn", "pilot", "prac", "extdev", "extcal",
                                  "extsealed") for m in "jn" for f in "tr"]


def load():
    R = {}
    for p in sorted(glob.glob(os.path.join(KBC, "results", "F2*.jsonl"))):
        if p.endswith("errors.jsonl"):
            continue
        for line in open(p):
            r = json.loads(line)
            k = (r["variant"].split(":")[-1], json.dumps(r["params"], sort_keys=True), r["src_hash"])
            R.setdefault(k, {})[r["track"]] = r
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--filter", default="")
    ap.add_argument("--suite", action="store_true")
    ap.add_argument("--tracks", default="")
    a = ap.parse_args()
    R = load()
    rows = []
    for k, t in R.items():
        if "P80" not in t or "P10" not in t or a.filter not in k[0] + k[1]:
            continue
        m8, m1 = t["P80"]["metrics"], t["P10"]["metrics"]
        rows.append(((m8["points_per_row"] + m1["points_per_row"]) / 2, k, t))
    rows.sort(key=lambda x: -x[0])
    tracks = a.tracks.split(",") if a.tracks else (SUITE if a.suite else [])
    hdr = "| # | sel | P80 pts | P80 acc | P80 ECE | P80 fP/fR | P10 pts | P10 acc | P10 ECE | P10 fP/fR | variant params [hash] |"
    if tracks:
        hdr += " " + " | ".join(tracks) + " |"
    print(hdr)
    for n, (s, k, t) in enumerate(rows[:a.top], 1):
        m8, m1 = t["P80"]["metrics"], t["P10"]["metrics"]
        line = (f"| {n} | {s:.4f} | {m8['points_per_row']:.4f} | {m8['accuracy']:.4f} | {m8['ece10']:.4f} | "
                f"{m8['false_precision']:.2f}/{m8['false_recall']:.2f} | {m1['points_per_row']:.4f} | {m1['accuracy']:.4f} | "
                f"{m1['ece10']:.4f} | {m1['false_precision']:.2f}/{m1['false_recall']:.2f} | {k[0]} {k[1]} [{k[2][:6]}] |")
        if tracks:
            line += " " + " | ".join(f"{t[x]['metrics']['points_per_row']:.4f}" if x in t else "" for x in tracks) + " |"
        print(line)


if __name__ == "__main__":
    main()
