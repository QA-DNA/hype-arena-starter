"""Summaries of results/F5*.jsonl (last line per (variant, params, track) wins).

  python -I F5/summ.py rules            rule precision / recall table (P80, P10)
  python -I F5/summ.py models [filter]  model table: P80, P10, mean points, ECE, false P/R
"""
import json
import os
import sys

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(files=("F5.jsonl",)):
    out = {}
    for fn in files:
        p = os.path.join(KBC, "results", fn)
        if not os.path.exists(p):
            continue
        for line in open(p):
            r = json.loads(line)
            out[(r["variant"], json.dumps(r["params"], sort_keys=True), r["track"])] = r
    return out


def rules(R):
    rows = {}
    for (v, p, t), r in R.items():
        if not v.endswith("rules.py"):
            continue
        rule = json.loads(p)["rule"]
        m = r["metrics"]
        rows.setdefault(rule, {})[t] = m
    print(f"{'rule':40s} | {'P80 fires':>9s} {'prec':>6s} {'rec':>6s} | {'P10 fires':>9s} {'prec':>6s} {'rec':>6s}")
    for rule, d in rows.items():
        line = f"{rule:40s}"
        for t in ("P80", "P10"):
            m = d.get(t)
            if not m:
                line += " | " + " " * 23; continue
            tgt = "unsure" if rule.startswith("U_") else "true" if rule.startswith(("restate", "event")) else "false"
            if tgt == "true":
                prec, rec = (m["points_per_row"] / m["coverage"] + 1) / 2 if m["coverage"] else 0, float("nan")
                fires = m["coverage"] * m["n"]
            else:
                prec, rec = m[tgt + "_precision"] or 0, m[tgt + "_recall"] or 0
                fires = m["n"] * (m["coverage"] if tgt == "unsure" else 0) if tgt == "unsure" else float("nan")
                if tgt == "unsure":
                    fires = m["n"] * (1 - m["coverage"])
            line += f" | {fires:9.1f} {prec:6.3f} {rec:6.3f}"
        print(line)


def models(R, filt=""):
    by = {}
    for (v, p, t), r in R.items():
        if v.endswith("rules.py") or filt not in v + p:
            continue
        by.setdefault((v, p), {})[t] = r["metrics"]
    rows = []
    for (v, p), d in by.items():
        if "P80" in d and "P10" in d:
            rows.append(((d["P80"]["points_per_row"] + d["P10"]["points_per_row"]) / 2, v, p, d))
    rows.sort(key=lambda x: -x[0])
    for s, v, p, d in rows:
        a, b = d["P80"], d["P10"]
        print(f"{s:.4f} P80 {a['points_per_row']:.4f} ece {a['ece10']:.3f} fP {a['false_precision'] or 0:.3f} fR {a['false_recall'] or 0:.3f}"
              f" | P10 {b['points_per_row']:.4f} ece {b['ece10']:.3f} fP {b['false_precision'] or 0:.3f} fR {b['false_recall'] or 0:.3f}"
              f" | {os.path.basename(v)} {p[:150]}")


if __name__ == "__main__":
    R = load(("F5.jsonl", "F5-remote.jsonl"))
    if sys.argv[1] == "rules":
        rules(R)
    else:
        models(R, sys.argv[2] if len(sys.argv) > 2 else "")
