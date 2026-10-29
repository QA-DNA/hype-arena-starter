"""Chain scores with fixed hazard and mono (no label-fitted global parameter): own-page change must be exactly 0."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "F2"))
import f2var

def vit(world):
    s = f2var.Chain(engine="viterbi", lam=0.005, mono=0.1, eps_a=0.0005, pi_o=1, vote_lr=48).scores(world)
    return np.nan_to_num(s, nan=-99.0)

def hmm(world):
    s = f2var.Chain(engine="hmm", lam=0.005, mono=0.1, eps_a=0.0005, pi_o=1, vote_lr=48).scores(world)
    return np.nan_to_num(s, nan=-99.0)

def lead(world):  # the leader's own scores (hazard + mono fitted on labelled anchors)
    c = f2var.Chain(engine="viterbi", d0=0.03, eps_a=0.0005, mono="fit", mono_a=10, pi_o=1, vote_lr=48)
    c.prep(world)
    return np.nan_to_num(c.scores(world), nan=-99.0)
