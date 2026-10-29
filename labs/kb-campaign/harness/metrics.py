"""One metrics function for every track. Reuses A/score.py basic() and ece() (vendored, unchanged)."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor_a"))
import score as S  # noqa: E402

KEYS = ("accuracy", "macro_f1", "points_per_row", "ece10", "brier", "false_precision", "false_recall",
        "unsure_precision", "unsure_recall", "coverage")


def compute(gold, pred, conf):
    """gold, pred: sequences of 'true'/'false'/'unsure'; conf: confidence of the predicted label (NaN/None on unsure).
    Arena points +1 right, -1 wrong true/false, 0 unsure (A/score.py). ECE: 10 bins over decided rows.
    Brier: mean (conf - correct)^2 over decided rows (exp.py)."""
    gold, pred = [str(g) for g in gold], [str(p) for p in pred]
    confs = [None if (c is None or p == "unsure" or (isinstance(c, float) and math.isnan(c))) else float(c)
             for c, p in zip(conf, pred)]
    b = S.basic(gold, pred)
    e, _ = S.ece(gold, pred, confs)
    dec = [(c, g == p) for g, p, c in zip(gold, pred, confs) if p != "unsure" and c is not None]
    pc = b["per_class"]
    return {"n": b["n"], "accuracy": b["accuracy"], "macro_f1": b["macro_f1"], "points": b["points"],
            "points_per_row": b["points_per_row"], "ece10": e,
            "brier": float(np.mean([(c - ok) ** 2 for c, ok in dec])) if dec else None,
            "false_precision": pc["false"]["precision"], "false_recall": pc["false"]["recall"],
            "unsure_precision": pc["unsure"]["precision"], "unsure_recall": pc["unsure"]["recall"],
            "coverage": b["coverage"], "confusion": b["confusion"]}


def mean_std(ms):
    out, sd = {}, {}
    for k in KEYS + ("n",):
        v = [m[k] for m in ms if m[k] is not None]
        out[k] = float(np.mean(v)) if v else None
        sd[k] = float(np.std(v)) if v else None
    return out, sd


def _selfcheck():
    m = compute(["true", "false", "unsure", "true"], ["true", "true", "unsure", "false"], [0.9, 0.6, None, 0.7])
    assert m["points"] == 0 and abs(m["accuracy"] - 0.5) < 1e-12 and m["coverage"] == 0.75
    assert abs(m["brier"] - (0.01 + 0.36 + 0.49) / 3) < 1e-12
    print("metrics selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
