"""Write bench/parsed_date.json and bench/parsed_row.json (out-of-fold parser output) and report fact-level quality.
    ./.venv/bin/python -m bench.make_parsed [--no-write]
"""
import argparse, json, os, sys, time
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench import common
from hype import parse


def ck(v):
    d = dict(v)
    if isinstance(d["value"], float):
        d["value"] = round(d["value"], 9)
    if d["kind"] == "name":
        d["value"] = d["value"].lower()
    return json.dumps(d, sort_keys=True)


def prf(tp, np_, ng):
    p = tp / np_ if np_ else 0.0
    r = tp / ng if ng else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def evaluate(rows, pred):
    views = {"fact": lambda f: (f["subject"], f["attribute"], ck(f["value"])),
             "subject": lambda f: (f["subject"],), "subj+attr": lambda f: (f["subject"], f["attribute"]),
             "value": lambda f: (ck(f["value"]),)}
    cnt = {k: [0, 0, 0] for k in views}
    kinds = {}
    exact = 0
    for r in rows:
        g, p = r["facts"], pred.get(r["id"], [])
        for k, fn in views.items():
            G, P = Counter(map(fn, g)), Counter(map(fn, p))
            cnt[k][0] += sum((G & P).values()); cnt[k][1] += sum(P.values()); cnt[k][2] += sum(G.values())
        gk, pk = Counter(map(views["fact"], g)), Counter(map(views["fact"], p))
        exact += gk == pk
        for kind in {f["value"]["kind"] for f in g + p}:
            a = Counter(views["fact"](f) for f in g if f["value"]["kind"] == kind)
            b = Counter(views["fact"](f) for f in p if f["value"]["kind"] == kind)
            c = kinds.setdefault(kind, [0, 0, 0])
            c[0] += sum((a & b).values()); c[1] += sum(b.values()); c[2] += sum(a.values())
    return cnt, kinds, exact / len(rows)


def report(split, rows, pred):
    cnt, kinds, ex = evaluate(rows, pred)
    print(f"== split={split}: rows={len(rows)}  row-all-exact={ex:.3f}")
    for k, (tp, n, g) in cnt.items():
        p, r, f = prf(tp, n, g)
        print(f"  {k:10s} P={p:.3f} R={r:.3f} F1={f:.3f}  (pred {n}, gold {g})")
    for k, (tp, n, g) in sorted(kinds.items()):
        p, r, f = prf(tp, n, g)
        print(f"  kind {k:9s} P={p:.3f} R={r:.3f} F1={f:.3f}  (gold {g})")


def load_synth(path):
    out = {}
    if path:
        for l in open(path):
            d = json.loads(l)
            out.setdefault(d["src"], []).append(d)
    return out


HYPS = {}


def oof(split, rows, lexicon, synth=None):
    pred = {}
    date = {r["id"]: r["date"] for r in rows}
    for k, train, test in common.folds(rows, split):
        extra = [{"id": f"s-{s}-{i}", "text": d["text"], "date": date[s], "label": "", "facts": d["facts"], "idx": -1}
                 for s in (r["id"] for r in train) for i, d in enumerate((synth or {}).get(s, []))]  # synthetic rows of TRAIN rows only
        model = parse.train(train + extra, lexicon)
        pred.update(parse.parse_all(rows, lexicon, model, only={r['id'] for r in test}))
        HYPS.update(parse.LAST_HYPS)
    return pred


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-write", action="store_true"); ap.add_argument("--splits", default="date,row"); ap.add_argument("--synth"); ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    lexicon = json.load(open(common.LEXICON))
    rows = common.load()
    for split in a.splits.split(","):
        t = time.time()
        pred = oof(split, rows, lexicon, load_synth(a.synth))
        report(split, rows, pred)
        print(f"  ({time.time()-t:.0f}s)")
        if not a.no_write:
            json.dump(pred, open(common.PARSED[split].replace(".json", a.suffix + ".json"), "w"))
            json.dump(HYPS, open(common.PARSED[split].replace("parsed_", "hyps_").replace(".json", a.suffix + ".json"), "w"))


if __name__ == "__main__":
    main()
