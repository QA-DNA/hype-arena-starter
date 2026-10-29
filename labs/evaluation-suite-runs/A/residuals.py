"""Residual error classes for a prediction file: group wrong targets by (gold, pred,
answerability, atom reasons) with counts and two examples. Reads gold (evaluator side).
Usage: python -I residuals.py --world prac --pred preds.csv"""
import argparse, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score, suite  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--world", required=True)
ap.add_argument("--pred", required=True)
ap.add_argument("--examples", type=int, default=2)
a = ap.parse_args()
targets, labels, meta = score.load_gold(a.world)
preds, _ = score.read_preds(a.pred)
rows = {r["id"]: r for r in suite.read_jsonl(suite.gold_path(a.world, "rows.jsonl"))}
groups = defaultdict(list)
for t in targets:
    p = preds.get(t, ("unsure", None))[0]
    if p != labels[t]:
        r = rows[t]
        reasons = ",".join(sorted({av["reason"] for av in r["assertion_verdicts"]}))
        groups[(labels[t], p, r["answerability"], reasons)].append(r)
print(f"{a.world}: {sum(map(len, groups.values()))} wrong of {len(targets)}")
for k, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f"  gold={k[0]} pred={k[1]} answerability={k[2]} reasons={k[3]}: {len(rs)}")
    for r in rs[:a.examples]:
        print(f"    {r['id']} {r['date']} {r['text'][:140]!r} form={json.dumps(r['form'])[:160]} evidence={r['evidence_ids'][:3]}")
