"""Page-cluster bootstrap over the practice pages for the top-30 configs (per-fold dumps out/af-*.npz):
SE of selection scores, paired differences, argmax frequency and winner's-curse optimism."""
import glob, json, os, sys
import numpy as np
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness"))
from world import load_track
JF, PF = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("af_jobs.txt", "af")
jobs = [l.rstrip("\n").split("\t") for l in open(JF)]
T = {tn: load_track(tn) for tn in ("P80", "P10")}
page = T["P80"].folds[0][0].page; npg = page.max() + 1
C = len(jobs)
pts = {}  # (track, k) -> (C x n_sc) points
for tn, t in T.items():
    for k, (w, gold, sc) in enumerate(t.folds):
        M = np.zeros((C, len(sc)))
        for c in range(C):
            d = np.load(f"out/{PF}-{c}.npz")
            p = d[f"{tn}_{k}_lab"][sc]
            M[c] = np.where(p == gold, 1, np.where(p != "unsure", -1, 0))
        pts[tn, k] = (M, page[sc])
def sel(wp):
    num80 = sum((M * wp[pg]).sum(1) for (tn, k), (M, pg) in pts.items() if tn == "P80")
    den80 = sum(wp[pg].sum() for (tn, k), (M, pg) in pts.items() if tn == "P80")
    p10 = np.mean([(M * wp[pg]).sum(1) / wp[pg].sum() for (tn, k), (M, pg) in pts.items() if tn == "P10"], 0)
    return (num80 / den80 + p10) / 2, num80 / den80, p10
S0, a0, b0 = sel(np.ones(npg))
print("orig sel (Mac recompute) top5:", [(int(i), round(S0[i], 4)) for i in np.argsort(-S0)[:5]])
rng = np.random.RandomState(0); B = 2000
SB = np.zeros((B, C))
for b in range(B):
    SB[b] = sel(np.bincount(rng.randint(0, npg, npg), minlength=npg).astype(float))[0]
ch = int(np.argmax(S0)); lead = [i for i, j in enumerate(jobs) if "f2var.py:Chain" in j[1]][0]
print("configs", C, "selected idx", ch, jobs[ch][2], "F2 chain idx", lead, jobs[lead][2])
print("sel SE: selected %.4f, F2 chain %.4f" % (SB[:, ch].std(), SB[:, lead].std()))
d = SB[:, ch] - SB[:, lead]
print("selected - F2 chain: orig %+.4f, boot mean %+.4f, SE %.4f, 95%% CI [%+.4f, %+.4f], P(<=0) %.3f" % (
    S0[ch] - S0[lead], d.mean(), d.std(), *np.percentile(d, [2.5, 97.5]), (d <= 0).mean()))
am = SB.argmax(1)
fr = np.bincount(am, minlength=C) / B
print("argmax frequency (top 8):", [(int(i), round(fr[i], 3)) for i in np.argsort(-fr)[:8]])
opt = SB[np.arange(B), am] - S0[am]
print("winner's-curse optimism (mean S_b(argmax_b) - S_orig(argmax_b)): %+.4f (sd %.4f)" % (opt.mean(), opt.std()))
print("top - median of these 30 near-top configs: %.4f; top - 20th: %.4f" % (S0.max() - np.median(S0), S0.max() - np.sort(S0)[-20]))
# paired SE of the selected vs the runner-up
ru = int(np.argsort(-S0)[1]); d2 = SB[:, ch] - SB[:, ru]
print("selected - runner-up (%d): orig %+.4f SE %.4f" % (ru, S0[ch] - S0[ru], d2.std()))
