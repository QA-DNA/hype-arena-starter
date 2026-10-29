"""Shared pieces of the judging benchmark: data, folds, value compatibility, metrics.

Judge interface (see judges/prior.py):
    class Judge:
        name = "x"
        def fit(self, train, unlabelled): ...
        def predict(self, rows) -> list[float]     # p(true) per row, 0..1
`train`: rows with a label in {"true","false","unsure"}. `unlabelled`: the held-out fold's rows, label
blanked (their text, date and facts are visible, as the ~18k unlabelled rows are in the real run). `rows` to
predict are the same held-out rows. A row is a dict: id, text, date, label, facts, idx (position in file).
A fact is {"subject", "attribute", "value": {"kind", ...}}.
"""
import csv, json, math, os, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRACTICE = os.path.join(ROOT, "data", "practice.csv")
LEXICON = os.path.join(ROOT, "data", "lexicon.json")
PARSED = {s: os.path.join(os.path.dirname(os.path.abspath(__file__)), f"parsed_{s}.json") for s in ("date", "row")}
K = 5


def load(forms="gold", split="date"):
    rows = []
    with open(PRACTICE, encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f)):
            rows.append({"id": r["id"], "text": r["text"], "date": r["date"], "label": r["label"],
                         "facts": json.loads(r["form"]), "idx": i})
    if forms == "parsed":
        with open(PARSED[split]) as f:   # {row id: facts}, produced out-of-fold by the parser
            parsed = json.load(f)
        for r in rows:
            r["gold"] = r["facts"]
            r["facts"] = parsed.get(r["id"], [])
    return rows


def fold_of(rows, split="date"):
    """Fold number (0..K-1) per row. 'date': whole dates together (unseen pages). 'row': every K-th row (like check.sh)."""
    if split == "row":
        return [r["idx"] % K for r in rows]
    dates = sorted({r["date"] for r in rows})
    random.Random(0).shuffle(dates)
    d = {x: i % K for i, x in enumerate(dates)}
    return [d[r["date"]] for r in rows]


def folds(rows, split="date"):
    """Yield (train, test) with the test labels blanked in `unlabelled`/`test`."""
    f = fold_of(rows, split)
    for k in range(K):
        train = [r for r, g in zip(rows, f) if g != k]
        test = [dict(r, label="") for r, g in zip(rows, f) if g == k]
        yield k, train, test


def key(fact):
    return (fact["subject"], fact["attribute"])


def compat(claimed, observed):
    """Does the claimed value agree with an observed (true) value? Precision, alias and `op` aware."""
    if claimed["kind"] != observed["kind"]:
        return False
    k = claimed["kind"]
    x, y = claimed["value"], observed["value"]
    if k == "date":
        x, y = str(x), str(y)
        return x.startswith(y) or y.startswith(x)
    if k == "name":
        x, y = x.lower(), y.lower()
        return x == y or x in y or y in x
    if k in ("boolean", "version"):
        return x == y
    if any(claimed.get(u) != observed.get(u) for u in ("unit", "currency", "per")):
        return False
    op = claimed.get("op")
    return {None: x == y, "eq": x == y, "gt": y > x, "ge": y >= x, "lt": y < x, "le": y <= x}[op]


def scored(rows):
    return [r for r in rows if r["label"] in ("true", "false")]


def metrics(p, y):
    """p: p(true) per row; y: bool per row. cw is a PROXY of the confidence-weighted score (formula unpublished)."""
    n = len(y)
    pc = [min(max(x, 1e-3), 1 - 1e-3) for x in p]
    right = [(x >= 0.5) == t for x, t in zip(p, y)]
    conf = [max(x, 1 - x) for x in p]
    ll = -sum(math.log(a if t else 1 - a) for a, t in zip(pc, y)) / n
    br = sum((x - t) ** 2 for x, t in zip(p, y)) / n
    ece = 0.0
    for b in range(5):  # confidence bins 0.5-0.6 ... 0.9-1.0
        idx = [i for i, c in enumerate(conf) if 0.5 + b * 0.1 <= c < 0.6 + b * 0.1 + (1e-9 if b == 4 else 0)]
        if idx:
            ece += len(idx) / n * abs(sum(right[i] for i in idx) / len(idx) - sum(conf[i] for i in idx) / len(idx))
    hi = [i for i, c in enumerate(conf) if c >= 0.9]
    return {"n": n, "acc": sum(right) / n, "logloss": ll, "brier": br, "ece": ece,
            "hi_cov": len(hi) / n, "hi_acc": (sum(right[i] for i in hi) / len(hi)) if hi else float("nan"),
            "cw": sum((2 * c - 1) * (1 if r else -1) for c, r in zip(conf, right)) / n}
