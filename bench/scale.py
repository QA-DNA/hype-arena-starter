"""Time each judge and the parser on a ~20k-row input (practice rows replicated with new ids): python -m bench.scale"""
import json, time, copy, sys, resource
from . import common, run
from hype import parse

N = 10
rows = common.load("parsed", "date")
train = rows
big = []
for k in range(N):
    for r in rows:
        big.append(dict(r, id=f"{r['id']}~{k}", label="", idx=r["idx"] + k * len(rows)))
print(f"train {len(train)} rows, predict {len(big)} rows")
print(f"{'judge':16s} {'fit s':>7s} {'predict s':>10s} {'total s':>8s} {'peak MB':>8s}")
for name, cls in sorted(run.discover().items()):
    j = cls(); t = time.time(); j.fit(train, big); a = time.time() - t
    t = time.time(); p = j.predict(big); b = time.time() - t
    assert len(p) == len(big)
    print(f"{name:16s} {a:7.1f} {b:10.1f} {a+b:8.1f} {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:8.0f}", flush=True)
lexicon = json.load(open(common.LEXICON)); gold = common.load("gold")
t = time.time(); m = parse.train(gold, lexicon); a = time.time() - t
bigg = [dict(r, id=f"{r['id']}~{k}") for k in range(N) for r in gold]
t = time.time(); out = parse.parse_all(bigg, lexicon, m); b = time.time() - t
print(f"{'parser':16s} {a:7.1f} {b:10.1f} {a+b:8.1f}  ({len(bigg)} rows parsed)")
