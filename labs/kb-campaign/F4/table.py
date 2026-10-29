"""Markdown tables for the F4 report from results jsonl (latest line per (variant, params, track) wins)."""
import json
import sys

NAMES = {}
rows = {}
for fn in [a for a in sys.argv[1:] if a.endswith(".jsonl")]:
    for l in open(fn):
        r = json.loads(l)
        rows[(r["variant"].split("/")[-1], json.dumps(r["params"], sort_keys=True), r["track"])] = r


def cfgs():
    seen = []
    for v, p, t in rows:
        if (v, p) not in seen:
            seen.append((v, p))
    return seen


def sel_table(keys):
    print("| config | P80 pts | P80 acc | P80 ECE | P80 F-prec / F-rec | P10 pts | P10 acc | P10 ECE | P10 F-prec / F-rec | mean pts |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, (v, p) in keys:
        a, b = rows.get((v, p, "P80")), rows.get((v, p, "P10"))
        if not a or not b:
            continue
        ma, mb = a["metrics"], b["metrics"]
        f = lambda m, k: "-" if m[k] is None else f"{m[k]:.3f}"  # noqa: E731
        print(f"| {name} | {ma['points_per_row']:.4f} | {f(ma,'accuracy')} | {f(ma,'ece10')} | {f(ma,'false_precision')} / {f(ma,'false_recall')} "
              f"| {mb['points_per_row']:.4f} | {f(mb,'accuracy')} | {f(mb,'ece10')} | {f(mb,'false_precision')} / {f(mb,'false_recall')} "
              f"| {(ma['points_per_row'] + mb['points_per_row']) / 2:.4f} |")


def suite_table(keys, tracks):
    print("| track | " + " | ".join(n for n, _ in keys) + " |")
    print("|---|" + "---|" * len(keys))
    for t in tracks:
        cells = []
        for _, (v, p) in keys:
            r = rows.get((v, p, t))
            cells.append("-" if r is None else f"{r['metrics']['points_per_row']:.3f}")
        print(f"| {t} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    spec = json.loads(open(sys.argv[sys.argv.index("--keys") + 1]).read()) if "--keys" in sys.argv else None
    keys = [(k["name"], (k["variant"], json.dumps(k["params"], sort_keys=True))) for k in spec]
    if "--suite" in sys.argv:
        W = ["dev", "diag", "cal", "sealed", "syn", "pilot", "prac", "extdev", "extcal", "extsealed"]
        suite_table(keys, [f"{f}{w}-{m}{t}" for f in "SX" for w in W for m in "jn" for t in "tr"])
    else:
        sel_table(keys)
