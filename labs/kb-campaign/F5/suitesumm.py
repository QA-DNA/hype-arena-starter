"""Suite (test-only) summary: python -I F5/suitesumm.py [variant] [cfg.json]. Points per row per track, deltas vs the
first config; never used for selection."""
import json, os, sys
import numpy as np
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = sys.argv[1] if len(sys.argv) > 1 else "F5/f5v.py"
CFG = json.load(open(sys.argv[2] if len(sys.argv) > 2 else os.path.join(KBC, "F5", "suite_cfg.json")))
R = {}
for fn in ("F5.jsonl", "F5-remote.jsonl"):
    p = os.path.join(KBC, "results", fn)
    for line in open(p):
        r = json.loads(line)
        if r["variant"] == VAR and r["track"][0] in "SX":
            R[(json.dumps(r["params"], sort_keys=True), r["track"])] = r
tracks = sorted({t for _, t in R})
keys = [json.dumps(c, sort_keys=True) for c in CFG]
W = sorted({t[1:].split("-")[0] for t in tracks})
print("track-group means of points per row (n tracks); config index order as in the cfg file")
for i, k in enumerate(keys):
    print(i, k)
hdr = "group".ljust(14) + "".join(f"{i:>9d}" for i in range(len(keys)))
print(hdr)
def row(name, ts):
    vals = []
    for k in keys:
        v = [R[(k, t)]["metrics"]["points_per_row"] for t in ts if (k, t) in R]
        vals.append(f"{np.mean(v):9.4f}" if len(v) == len(ts) else "      n/a")
    print(name.ljust(14) + "".join(vals) + f"  ({len(ts)})")
for pre in "SX":
    for w in W:
        for reg in ("jt", "jr", "nt", "nr"):
            ts = [t for t in tracks if t == f"{pre}{w}-{reg}"]
            if ts:
                row(f"{pre}{w}-{reg}", ts)
row("S all", [t for t in tracks if t[0] == "S"])
row("S transfer t", [t for t in tracks if t[0] == "S" and t.endswith("t")])
row("S refit r", [t for t in tracks if t[0] == "S" and t.endswith("r")])
row("X all", [t for t in tracks if t[0] == "X"])
