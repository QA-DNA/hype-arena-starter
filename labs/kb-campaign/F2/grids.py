"""Prints run.py --variant arguments (one per line) for a named grid: python3 grids.py g1"""
import json
import sys

V = "F2/f2var.py:"


def arg(cls, grid):
    return f"{V}{cls}={json.dumps(grid, separators=(',', ':'))}"


def g1():
    out = []
    core = {"vote_lr": [1.5, 3, 6, 12], "eps_a": [0.002, 0.02, 0.1], "lam_scale": [0.5, 1, 2],
            "pi_o": [0.1, 0.5, 2]}
    out.append(arg("Chain", dict(core, engine="hmm")))
    out.append(arg("Chain", dict(core, engine="viterbi")))
    extra = []
    for eng in ("hmm", "viterbi"):
        extra += [dict(engine=eng, eps_f=e) for e in (0.05, 0.5, 1.0)]
        extra += [dict(engine=eng, mono=m) for m in (0.3, 0.1)]
        extra += [dict(engine=eng, wm=w) for w in (0.5, 1.0)]
        extra += [dict(engine=eng, lam_by=b) for b in ("global", "token", "attr")]
        extra += [dict(engine=eng, lam=l) for l in (0.002, 0.01, 0.03)]
        extra += [dict(engine=eng, fmap="platt"), dict(engine=eng, rcal="platt"), dict(engine=eng, agg="min")]
    out.append(arg("Chain", extra))
    pts = [dict(mode=m, wu=w) for m in ("latest", "nearest", "bracket") for w in (0.05, 0.3, 1.0)]
    out.append(arg("Point", pts))
    out.append(arg("Point", {"kernel": ["exp", "tri", "box"], "tau": [7, 30, 90, 365], "beta": [0.25, 0.5, 1.0],
                             "wu": [0.1, 0.3, 1.0]}))
    out.append(arg("Point", [dict(wf=0.5), dict(wf=1.0), dict(wa=3.0), dict(wa=10.0)]))
    out.append(arg("Bracket", {"vote_fallback": [True, False], "gapb": [0, 14, 60, 180], "alpha": [1, 4, 16]}))
    out.append(arg("Chain", {"engine": "tecore", "w_v": [0.25, 0.5, 1, 2], "C": [0.5, 1, 2, 4, 8],
                             "C_o": [0.5, 2, 5], "mono_pen": [0, 1]}))
    out.append(arg("Chain", {"engine": "seg", "c": [0.1, 0.25, 0.5, 1, 2, 4], "vote_lr": [2, 4, 8]}))
    out.append(arg("Chain", [dict(engine="seg", sweep=[0.25, 0.5, 1, 2, 4])]))
    return out


def g2():
    core = {"vote_lr": [12, 24, 48], "eps_a": [0.0005, 0.002], "lam_scale": [0.7, 1, 1.4], "pi_o": [1, 2, 4],
            "mono": [1.0, 0.3, 0.1]}
    return [arg("Chain", dict(core, engine="hmm")), arg("Chain", dict(core, engine="viterbi")),
            arg("Chain", {"engine": "tecore", "w_v": [2, 4, 8], "C": [0.5, 1, 2], "mono_pen": [1, 2, 4],
                          "C_o": [0.5]}),
            arg("Point", [dict(kernel="box", tau=7, wu=0.1), dict(), dict(mode="latest", wu=0.3)]),
            arg("Bracket", [dict(alpha=1, gapb=14, vote_fallback=False), dict()]),
            arg("Chain", [dict(engine="seg", c=1, vote_lr=8)])]


def g4():
    core = {"vote_lr": [48, 100, 200], "eps_a": [0.0005, 0.0001], "lam_scale": [0.7, 1], "pi_o": [1, 2],
            "mono": [0.1, 0.03, 0.01]}
    return [arg("Chain", dict(core, engine="hmm")), arg("Chain", dict(core, engine="viterbi"))]


def g5():
    core = {"vote_lr": [24, 48, 100], "eps_a": [0.0005, 0.0001], "pi_o": [1, 2], "mono": ["fit"],
            "mono_a": [3, 10, 30], "d0": [0.03, 0.1, 0.3]}
    fixed = {"vote_lr": [48], "eps_a": [0.0005], "pi_o": [1, 2], "mono": [0.1, 0.03], "mono_all": [True]}
    return [arg("Chain", dict(core, engine="hmm")), arg("Chain", dict(core, engine="viterbi")),
            arg("Chain", dict(fixed, engine="hmm")), arg("Chain", dict(fixed, engine="viterbi")),
            arg("BracketHMM", {"nb": [5, 10, 20], "backoff": ["cell"], "alpha": [1, 4]})]


TOP = {
    "A": ("Chain", dict(engine="viterbi", d0=0.03, eps_a=0.0005, mono="fit", mono_a=10, pi_o=1, vote_lr=48)),
    "B": ("Chain", dict(engine="hmm", d0=0.1, eps_a=0.0001, mono="fit", mono_a=3, pi_o=1, vote_lr=48)),
    "C": ("Chain", dict(engine="tecore", C=2, C_o=0.5, mono_pen=2, w_v=4)),
    "D": ("Chain", dict(engine="viterbi", eps_a=0.0005, lam_scale=1, mono=0.1, pi_o=2, vote_lr=48)),
    "E": ("Chain", dict(engine="hmm", eps_a=0.002, lam_scale=1, pi_o=2, vote_lr=12)),
    "F": ("Point", dict(kernel="box", tau=7, wu=0.1, beta=1.0)),
    "G": ("Bracket", dict(alpha=1, gapb=14, vote_fallback=False)),
    "H": ("Chain", dict(engine="seg", c=1, vote_lr=8)),
    "I": ("Combo", dict(blocks=["hmm", "viterbi"], C=1.0)),
    "K": ("BracketHMM", dict(alpha=4, backoff="hmm", nb=20)),
}


def g6():
    out = [arg(c, [p]) for c, p in TOP.values()]
    out.append("v9=" + json.dumps([dict(select="arena", extra_features=["F2/f2feat.py:all"]),
                                   dict(select="arena", extra_features=["F2/f2feat.py:core"])], separators=(",", ":")))
    return out


def g6x():
    return [arg(*TOP[k]) .replace("=", "=[", 1) + "]" if False else arg(TOP[k][0], [TOP[k][1]]) for k in "ABC"]


def g3():
    F = "F2/f2feat.py:"
    combo = [dict(blocks=b, C=c) for b in (["hmm", "viterbi", "stale", "bracket"], ["hmm", "viterbi"],
                                           ["hmm", "bracket"], ["viterbi", "stale"],
                                           ["hmm", "viterbi", "tecore", "seg", "stale", "bracket"])
             for c in (0.1, 0.3, 1.0)]
    v9 = [dict(select="arena")] + [dict(select="arena", extra_features=[F + x for x in xs]) for xs in
                                   (["core"], ["all"], ["hmm"], ["viterbi"], ["stale"], ["hmm", "viterbi"])]
    v9 += [dict(select="arena", model="hgb", extra_features=[F + "all"])]
    return [arg("Combo", combo),
            arg("BracketHMM", {"nb": [5, 10, 20], "backoff": ["hmm", "cell"], "alpha": [1, 4]}),
            "v9=" + json.dumps(v9, separators=(",", ":")),
            arg("Chain", {"engine": ["hmm", "viterbi"], "vote_lr": [1.0], "eps_a": [0.002],
                          "lam_by": ["kind", "global"]})]


if __name__ == "__main__":
    for a in globals()[sys.argv[1]]():
        print(a)
