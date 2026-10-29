"""Stage-2 grid from stage-1 results: top configs per method rerun with select='arena' (the exact scorer rule),
plus each family's extensions around its best stage-1 config. Prints run.py --variant args, one per line.
  python -I stage2.py ../results/F1-remote.jsonl [../results/F1.jsonl ...]"""
import collections as C
import json
import sys

V = "F1/f1var.py:Variant"
R = C.defaultdict(dict)
for path in sys.argv[1:]:
    for line in open(path):
        r = json.loads(line)
        R[json.dumps(r["params"], sort_keys=True)][r["track"]] = r["metrics"]["points_per_row"]
best = C.defaultdict(list)
for p, t in R.items():
    if "P80" in t and "P10" in t:
        q = json.loads(p)
        best[q["method"]].append(((t["P80"] + t["P10"]) / 2, q))
for m in best:
    best[m].sort(key=lambda x: -x[0])
out = []


def add(p):
    p = dict(p); p["select"] = "arena"
    out.append(p)


for m, xs in best.items():
    for _, p in xs[:5]:
        add(p)
top = {m: xs[0][1] for m, xs in best.items()}
if "accu" in top:
    b = top["accu"]
    for ext in ([dict(copy=True, c=c, calpha=a) for c in (0.5, 0.8) for a in (0.05, 0.2)]
                + [dict(copy=True, wcopy=30)] + [dict(liar=True)]
                + [dict(dyna=[k, h]) for k in (3.0, 10.0) for h in (15, 45)]
                + [dict(dedup=True), dict(sup="contain", rho_partial=0.5), dict(softmax=False), dict(row="min"),
                   dict(calib="platt"), dict(inner=10)]):
        add({**b, **ext})
    for Cc in (0.1, 0.5):
        for lu in (0.1, 0.3, 1.0):
            add({**b, "method": "slimfast", "C": Cc, "lam_u": lu})
if "truthfinder" in top:
    b = top["truthfinder"]
    for ext in (dict(ta=0.99), dict(ta=0.9999), dict(wneg=0.5), dict(wneg=2.0), dict(selfw=0.0), dict(dedup=True),
                dict(beta=0.5), dict(row="min")):
        add({**b, **ext})
if "crh" in top:
    b = top["crh"]
    for ext in (dict(dedup=True), dict(beta=0.5), dict(row="min"), dict(iters=30)):
        add({**b, **ext})
for m in ("ds", "ltm"):
    if m in top:
        b = top[m]
        for ext in (dict(anchor_acc=0.9), dict(anchor_acc=0.995), dict(a0=[20.0, 1.0]), dict(a0=[2.0, 1.0]),
                    dict(k=6, pages_as="cluster"), dict(k=24, pages_as="cluster"), dict(dedup=True), dict(row="min"),
                    dict(pi0=0.8)):
            add({**b, **ext})
        if m == "ltm":
            add({**b, "burn": 50, "samples": 100})
if "sums" in top:
    add({**top["sums"], "dedup": True})
for m in ("avglog", "vote"):
    if m in top:
        add({**top[m], "dedup": True})
# vote sub-families: best unweighted, windowed, decayed
if "vote" in best:
    seen = set()
    for _, p in best["vote"]:
        kind = "decay" if p.get("tau") else "window" if p.get("win") else "plain"
        if kind not in seen:
            seen.add(kind); add(p)
uniq = []
for p in out:
    if p not in uniq:
        uniq.append(p)
print("\n".join(["--variant\n" + V + "=" + json.dumps(uniq)]))
print(len(uniq), file=sys.stderr)
