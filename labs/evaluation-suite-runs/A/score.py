"""Score a prediction CSV (id,label[,confidence]) on a world's hidden targets.

Usage: python -I score.py --world dev --pred preds.csv [--json-out m.json]
Only targets (public label empty) are scored. Missing targets count as unsure,
the first duplicate id counts, a non-empty confidence on unsure is an error.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite  # noqa: E402

CLASSES = ("true", "false", "unsure")


class PredError(ValueError):
    pass


def load_gold(world):
    """Target ids -> gold label, plus slice metadata from rows.jsonl."""
    targets = [r["id"] for r in suite.read_universe(world) if r["label"] == ""]
    labels = {r["id"]: r["label"] for r in suite.read_csv(suite.gold_path(world, "labeled.csv"))}
    meta = {}
    with open(suite.gold_path(world, "rows.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            kinds = sorted({a["value"]["kind"] for a in r["form"]})
            ops = sorted({a["value"].get("op") for a in r["form"] if a["value"].get("op")})
            n = len(r["form"])
            meta[r["id"]] = {
                "arity": "1" if n == 1 else "2" if n == 2 else "3+",
                "has_distractor": str(bool(r.get("distractors"))),
                "genre": r.get("genre"),
                "track": r.get("track"),
                "answerability": r.get("answerability"),
                "value_kind": kinds[0] if len(kinds) == 1 else "mixed",
                "has_op": str(bool(ops)),
            }
    return targets, labels, meta


def read_preds(path):
    """id -> (label, confidence|None). Raises PredError on invalid rows."""
    preds, dup, errors = {}, 0, []
    for i, r in enumerate(suite.read_csv(path), start=2):
        rid = (r.get("id") or "").strip()
        lab = (r.get("label") or "").strip().lower()
        cs = (r.get("confidence") or "").strip()
        if lab not in CLASSES:
            errors.append(f"line {i}: bad label {lab!r}")
            continue
        conf = None
        if cs:
            if lab == "unsure":
                errors.append(f"line {i}: confidence {cs!r} on unsure ({rid})")
                continue
            try:
                conf = float(cs)
            except ValueError:
                errors.append(f"line {i}: bad confidence {cs!r}")
                continue
            if not 0.0 <= conf <= 1.0:
                errors.append(f"line {i}: confidence {conf} outside [0,1]")
                continue
        if rid in preds:
            dup += 1
            continue
        preds[rid] = (lab, conf)
    if errors:
        raise PredError(f"{len(errors)} invalid prediction rows, e.g. " + "; ".join(errors[:5]))
    return preds, dup


def basic(gold, pred):
    n = len(gold)
    conf = {g: Counter() for g in CLASSES}
    for g, p in zip(gold, pred):
        conf[g][p] += 1
    per_class, f1s, recalls = {}, [], []
    for c in CLASSES:
        tp = conf[c][c]
        npred = sum(conf[g][c] for g in CLASSES)
        ngold = sum(conf[c].values())
        prec = tp / npred if npred else 0.0
        rec = tp / ngold if ngold else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_class[c] = {"precision": prec, "recall": rec, "f1": f1, "n_gold": ngold, "n_pred": npred}
        f1s.append(f1)
        if ngold:
            recalls.append(rec)
    points = sum(1 if p == g else (-1 if p != "unsure" else 0) for g, p in zip(gold, pred))
    return {
        "n": n,
        "accuracy": sum(g == p for g, p in zip(gold, pred)) / n if n else 0.0,
        "macro_f1": sum(f1s) / 3,
        "balanced_accuracy": sum(recalls) / len(recalls) if recalls else 0.0,
        "points": points,
        "points_per_row": points / n if n else 0.0,
        "coverage": sum(p != "unsure" for p in pred) / n if n else 0.0,
        "per_class": per_class,
        "confusion": {g: {p: conf[g][p] for p in CLASSES} for g in CLASSES},
    }


def ece(gold, pred, confs, bins=10):
    rows = [(c, g == p) for g, p, c in zip(gold, pred, confs) if p != "unsure" and c is not None]
    if not rows:
        return None, 0
    acc_b, conf_b, n_b = [0.0] * bins, [0.0] * bins, [0] * bins
    for c, ok in rows:
        b = min(int(c * bins), bins - 1)
        acc_b[b] += ok
        conf_b[b] += c
        n_b[b] += 1
    total = sum(abs(acc_b[b] - conf_b[b]) for b in range(bins) if n_b[b])
    return total / len(rows), len(rows)


def score(world, pred_path, slices=True):
    targets, labels, meta = load_gold(world)
    preds, dup = read_preds(pred_path)
    tset = set(targets)
    gold = [labels[t] for t in targets]
    pred = [preds.get(t, ("unsure", None))[0] for t in targets]
    confs = [preds.get(t, ("unsure", None))[1] for t in targets]
    m = basic(gold, pred)
    m["ece10"], m["ece_n"] = ece(gold, pred, confs)
    m["n_missing"] = sum(t not in preds for t in targets)
    m["n_duplicate_ignored"] = dup
    m["n_non_target_ignored"] = sum(rid not in tset for rid in preds)
    m["n_decided_without_conf"] = sum(p != "unsure" and c is None for p, c in zip(pred, confs))
    if slices:
        out = defaultdict(dict)
        groups = defaultdict(lambda: ([], []))
        for t, g, p in zip(targets, gold, pred):
            for dim, val in meta[t].items():
                gs, ps = groups[(dim, val)]
                gs.append(g)
                ps.append(p)
        for (dim, val), (gs, ps) in sorted(groups.items(), key=str):
            b = basic(gs, ps)
            out[dim][val] = {k: b[k] for k in ("n", "accuracy", "macro_f1", "points_per_row", "coverage")}
            out[dim][val]["gold_mix"] = dict(Counter(gs))
        m["slices"] = out
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--world", required=True, choices=sorted(suite.WORLDS))
    ap.add_argument("--pred", required=True)
    ap.add_argument("--json-out")
    a = ap.parse_args()
    try:
        m = score(a.world, a.pred)
    except PredError as e:
        sys.exit(f"ERROR: {e}")
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(m, f, indent=1)
    keys = ("n", "accuracy", "macro_f1", "balanced_accuracy", "points_per_row", "coverage", "ece10")
    print(json.dumps({k: m[k] for k in keys}))
    pc = m["per_class"]
    print("per-class P/R:", {c: (round(pc[c]["precision"], 4), round(pc[c]["recall"], 4)) for c in CLASSES})


if __name__ == "__main__":
    main()
