"""Leak-free evaluation of one parser component (e.g. booleans, quantity assignment) on top of the out-of-fold parse.

    from bench.eval_component import evaluate
    evaluate("name", train_fn, apply_fn, kinds={"boolean"}, split="date")

train_fn(train_rows, lexicon) -> model      # train_rows: dicts with id,text,date,label,facts(GOLD),idx. TRAIN FOLDS ONLY.
apply_fn(model, test_rows, lexicon, facts_by_id, hyps_by_id, all_rows) -> {id: facts}
    test_rows: held-out rows WITHOUT labels or gold facts (id,text,date,idx only).
    facts_by_id / hyps_by_id: the existing out-of-fold parse (bench/parsed_<split>.json, bench/hyps_<split>.json) of those rows.
    all_rows: id,text,date,idx of EVERY row (text only, no facts): neighbours give context, as in the real run.
    Return the full facts list for each test row (start from the existing facts and replace/add yours).
Prints fact-level precision/recall for `kinds` before and after, and the judge (t1_soft, gold evidence) accuracy / log-loss before and after.
"""
import json
from collections import Counter
from . import common, run
from .judges import t1_soft as T
from .make_parsed import ck


def _prf(rows, pred, kinds):
    tp = n = g = 0
    for r in rows:
        G = Counter((f["subject"], f["attribute"], ck(f["value"])) for f in r["gold"] if f["value"]["kind"] in kinds)
        P = Counter((f["subject"], f["attribute"], ck(f["value"])) for f in pred.get(r["id"], []) if f["value"]["kind"] in kinds)
        tp += sum((G & P).values()); n += sum(P.values()); g += sum(G.values())
    p, rc = tp / n if n else 0.0, tp / g if g else 0.0
    return p, rc, (2 * p * rc / (p + rc) if p + rc else 0.0), n, g


def _judge(rows, facts, split):
    T.GOLD_EVIDENCE, T.TRUST, T.SOFT = True, False, False
    rr = [dict(r, facts=facts.get(r["id"], [])) for r in rows]
    m = run.evaluate(T.Judge, rr, split)
    return m["acc"], m["logloss"]


def evaluate(name, train_fn, apply_fn, kinds, split="date"):
    rows = common.load("parsed", split)           # r["facts"] = out-of-fold parse, r["gold"] = gold facts
    lex = json.load(open(common.LEXICON))
    parsed = json.load(open(common.PARSED[split]))
    hyps = json.load(open(common.PARSED[split].replace("parsed_", "hyps_")))
    T.load_hyps(split)
    bare = [{"id": r["id"], "text": r["text"], "date": r["date"], "idx": r["idx"]} for r in rows]
    new = {}
    for k, train, test in common.folds(common.load("gold"), split):
        model = train_fn(train, lex)
        ids = {r["id"] for r in test}
        tb = [b for b in bare if b["id"] in ids]
        new.update(apply_fn(model, tb, lex, {i: parsed.get(i, []) for i in ids}, {i: hyps.get(i, []) for i in ids}, bare))
    for r in rows:
        new.setdefault(r["id"], parsed.get(r["id"], []))
    b, a = _prf(rows, parsed, kinds), _prf(rows, new, kinds)
    print(f"[{name}] split={split} kinds={sorted(kinds)}")
    print(f"  fact P/R/F1 before {b[0]:.3f}/{b[1]:.3f}/{b[2]:.3f} (pred {b[3]}, gold {b[4]})  after {a[0]:.3f}/{a[1]:.3f}/{a[2]:.3f} (pred {a[3]})")
    ba, bl = _judge(rows, parsed, split); aa, al = _judge(rows, new, split)
    print(f"  judge acc/logloss before {ba:.3f}/{bl:.3f}  after {aa:.3f}/{al:.3f}")
    return new
