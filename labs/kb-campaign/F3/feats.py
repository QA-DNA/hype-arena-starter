"""F3 feature plugins wrapping F2's per-key chain scores (F2/f2var.py Chain, F2's best P80+P10 parameters as
published in results/F2-remote.jsonl at 02:00). Each fact's score excludes its own page (F2's contract); the hazard
is fitted on the world's labelled anchors. Columns: [score with NaN -> 0, 1 if NaN (no other-page evidence)]."""
import os
import sys

import numpy as np

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F2 = os.path.join(KBC, "F2")
if F2 not in sys.path:
    sys.path.insert(0, F2)

VIT = dict(engine="viterbi", eps_a=0.0005, lam_scale=1, mono=0.1, pi_o=2, vote_lr=48)
HMM = dict(engine="hmm", eps_a=0.0005, lam_scale=1, mono=0.1, pi_o=2, vote_lr=48)


def _chain(world, prm, role=None):
    import f2var
    key = ("_f3_chain", tuple(sorted(prm.items())), np.packbits(world.labelled).tobytes())
    c = world.__dict__.setdefault("_f3_cache", {})
    if key not in c:
        ch = f2var.Chain(**prm)
        ch.prep(world)
        s = np.asarray(ch.scores(world), float)
        if prm["engine"] == "hmm":
            s = np.log(np.clip(s, 1e-4, 1 - 1e-4)) - np.log1p(-np.clip(s, 1e-4, 1 - 1e-4))
        nan = np.isnan(s)
        c[key] = np.c_[np.where(nan, 0.0, s), nan.astype(float)]
    return c[key]


def chain_vit(world):
    return _chain(world, VIT)


def chain_hmm(world):
    return _chain(world, HMM)
