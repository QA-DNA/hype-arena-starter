"""Descriptive analyses on practice with every label visible (own page excluded as evidence):
hazard fit per class, premature (N-Y) and late-old-value (Y-N) patterns. Not used for selection.
Run: python -I analysis.py > analysis.txt"""
import collections as C
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from world import practice_full  # noqa: E402
import f2core as K  # noqa: E402

w = practice_full()[0]
print("== 1. hazard: P(value unchanged | gap) between consecutive labelled-true anchors of a key")
P = K.anchor_pairs(w)
g = np.array([x[0] for x in P]); s = np.array([x[1] for x in P])
lam = K.mle_lambda(g, s)
print(f"pairs {len(P)}, same {s.mean():.3f}, global lambda {lam:.5f}/day (mean life {1/lam:.0f} d)")
print("gap bucket | pairs | empirical same | exp(-lambda g) at bucket median")
for lo, hi in ((1, 7), (8, 30), (31, 90), (91, 180), (181, 400)):
    m = (g >= lo) & (g <= hi)
    if m.any():
        print(f"{lo}-{hi} d | {m.sum()} | {s[m].mean():.3f} | {math.exp(-lam * np.median(g[m])):.3f}")
hz = K.Hazard("attr").fit(w)
print("per kind lambda:", {c: round(v, 5) for (l, c), v in hz.tab.items() if l == "kind"})
print("per token lambda (>= 8 pairs):", {c: round(v, 5) for (l, c), v in sorted(hz.tab.items()) if l == "token"})
kc = C.Counter(x[2] for x in P)
print("pairs per kind:", dict(kc))

print("\n== 2. premature vs lie: single-fact rows, latest anchor before D disagrees, next anchor after agrees (N-Y)")
y = K.fact_targets(w)
rows = []
for k in K.keys_of(w):
    other = k.page[:, None] != k.page[None, :]
    isA = k.role == "A"
    for x in range(k.n):
        if y[k.g[x]] < 0:
            continue
        D = k.date[x]
        b = np.flatnonzero(isA & other[x] & (k.date < D)); a = np.flatnonzero(isA & other[x] & (k.date > D))
        if not len(b) or not len(a):
            continue
        db = k.date[b].max(); da = k.date[a].min()
        bm = k.cons[x, b[k.date[b] == db]].mean() > 0.5
        am = k.cons[x, a[k.date[a] == da]].mean() > 0.5
        f = w.flat[k.g[x]]
        prevv = [w.flat[k.g[j]].canon for j in b[k.date[b] == db]][0]
        up = None
        if isinstance(f.canon, float) and isinstance(prevv, float) and f.canon != prevv:
            up = f.canon > prevv
        ever_b = bool((k.cons[x, b]).any())
        rows.append(dict(pat=("Y" if bm else "N") + ("Y" if am else "N"), y=int(y[k.g[x]]), gb=int(D - db),
                         ga=int(da - D), pos=(D - db) / max(1, da - db), up=up, ever_b=ever_b, kind=f.kind))
for pat in ("NY", "YN", "NN", "YY"):
    R = [r for r in rows if r["pat"] == pat]
    print(f"pattern {pat}: n={len(R)} true rate {np.mean([r['y'] for r in R]):.3f}")
for pat in ("NY", "YN"):
    R = [r for r in rows if r["pat"] == pat]
    print(f"-- {pat} split by candidate discriminators (true / false counts, true rate)")
    def show(name, f):
        cnt = C.defaultdict(lambda: [0, 0])
        for r in R:
            cnt[f(r)][r["y"]] += 1
        for kk in sorted(cnt, key=str):
            t, fl = cnt[kk][1], cnt[kk][0]
            print(f"   {name}={kk}: {t} / {fl}  rate {t / max(1, t + fl):.3f}")
    show("gap_after", lambda r: "<=14" if r["ga"] <= 14 else "15-60" if r["ga"] <= 60 else ">60")
    show("gap_before", lambda r: "<=14" if r["gb"] <= 14 else "15-60" if r["gb"] <= 60 else ">60")
    show("position", lambda r: "first third" if r["pos"] < 1 / 3 else "middle" if r["pos"] < 2 / 3 else "last third")
    show("direction_up", lambda r: r["up"])
    show("value_seen_before_D", lambda r: r["ever_b"])
    show("kind", lambda r: r["kind"])

print("\n== 3. P80 hidden facts: does the HMM posterior separate true from false inside each anchor pattern?")
from sklearn.metrics import roc_auc_score  # noqa: E402
from world import load_track  # noqa: E402
import f2var  # noqa: E402
from world import practice_full as _pf  # noqa: E402
full = _pf()[0]
yfull = K.fact_targets(full)
cells_full = None
pat, sc, yy, rel = [], [], [], []
for wld, gold, scd in load_track("P80").folds:
    v = f2var.Chain(engine="hmm", eps_a=0.002, pi_o=2, vote_lr=12); v.prep(wld)
    s = v.scores(wld)
    cells = K.bracket_cells(wld, vote_fallback=False)
    hid = ~wld.labelled[wld.frow]
    for n in np.flatnonzero(hid & (yfull >= 0)):
        pat.append(cells[n][0] + cells[n][2]); sc.append(s[n]); yy.append(yfull[n])
pat, sc, yy = np.array(pat), np.array(sc), np.array(yy)
print("pattern (before, after anchors) | n | true rate | AUC of HMM posterior within pattern")
for p in ("YY", "NY", "YN", "NN", "Y-", "N-", "-Y", "-N", "--"):
    m = (pat == p) & ~np.isnan(sc)
    if m.sum() >= 10 and 0 < yy[m].sum() < m.sum():
        print(f"{p} | {m.sum()} | {yy[m].mean():.3f} | {roc_auc_score(yy[m], sc[m]):.3f}")
    elif m.sum():
        print(f"{p} | {m.sum()} | {yy[m].mean():.3f} | n/a")
m = ~np.isnan(sc)
print(f"all hidden facts with evidence | {m.sum()} | {yy[m].mean():.3f} | {roc_auc_score(yy[m], sc[m]):.3f}")
