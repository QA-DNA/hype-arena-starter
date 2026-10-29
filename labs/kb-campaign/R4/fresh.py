"""Independent check of P3's fresh-split result. (1) my own split construction (F5 rule re-implemented), page
grouping and overlap with the harness splits; (2) my own page-cluster bootstrap from P3's recorded per-row points;
(3) rerun mode: `fresh.py rerun SPLIT...` re-runs configs a, c, dedup on given splits and diffs row points."""
import json, os, random, sys
import numpy as np
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness"))
import world as W
A = ("P3/p3.py:Stack", {"oofmap": False})
CFG = {"a": A, "c": ("P3/p3.py:Stack", {"C": 1.0, "feats": ["F1/plugins.py:td_post#0", "F5/fp.py:w_nds"]}),
       "b": ("P3/p3.py:Stack", {"C": 1.0, "feats": ["F1/plugins.py:td_post#0"]}),
       "f": ("P3/p3.py:Stack", {"C": 1.0, "feats": ["F5/fp.py:w_nds"], "oofmap": False}),
       "dedup": ("P3/p3.py:Stack", {"dedup": True, "oofmap": False})}
_, base, gold = W.practice_full()
npg = base.n_pages
def my_splits():
    out = {}
    for r in range(1, 4):
        perm = np.random.RandomState(100 + r).permutation(npg)
        for f in range(5):
            lab = np.ones(npg, bool); lab[perm[f::5]] = False; out[f"P80R{r}f{f}"] = lab
    for s in range(10, 30):
        rng = random.Random(s); lab = np.zeros(npg, bool)
        lab[rng.sample(range(npg), max(1, round(0.1 * npg)))] = True; out[f"P10s{s}"] = lab
    return out
S = my_splits()
key = lambda s, p: (s, json.dumps(p, sort_keys=True))
if sys.argv[1:2] == ["rerun"]:
    os.chdir(KBC)
    from api import check_prediction, resolve, run_variant
    rec = {}
    for l in open(os.path.join(KBC, "results", "P3-denoise2.jsonl")):
        r = json.loads(l); rec[key(r["variant"], r["params"]) + (r["split"],)] = np.array(r["row_points"])
    for sp in sys.argv[2:]:
        lab = S[sp][base.page]; w = base.with_labels(lab, gold); sc = np.where(~lab)[0]
        for name in ("a", "c", "dedup"):
            s, p = CFG[name]
            pr = check_prediction(w, run_variant(resolve(s, "Variant")[0](**p), w))
            rp = np.where(pr.labels[sc] == gold[sc], 1, np.where(pr.labels[sc] != "unsure", -1, 0))
            old = rec[key(s, p) + (sp,)]
            print(sp, name, "rerun pts %.4f recorded %.4f identical rows %s" % (rp.mean(), old.mean(), np.array_equal(rp, old)), flush=True)
    sys.exit()
# split hygiene
harn80 = [lp for lp in W.practice_splits(npg, "P80")]; harn10 = [lp for lp in W.practice_splits(npg, "P10")]
D = {}
for l in open(os.path.join(KBC, "results", "P3-denoise2.jsonl")):
    r = json.loads(l)
    D.setdefault(key(r["variant"], r["params"]), {})[r["split"]] = (np.array(r["row_points"], float), np.array(r["row_page"], int))
any_cfg = next(iter(D.values()))
bad = 0
for sp, (pts, pg) in any_cfg.items():
    want = set(np.flatnonzero(~S[sp]).tolist())
    got = set(pg.tolist())
    whole = all(((base.page == q).sum() == (pg == q).sum()) for q in got)
    bad += (want != got) or not whole
print("splits recorded:", len(any_cfg), "| scored pages == complement of my independently built labelled mask, whole pages:", bad == 0)
mx80 = max(max((~S[sp] & ~h).sum() / (~S[sp]).sum() for h in harn80) for sp in S if sp.startswith("P80"))
mx10 = max(max((S[sp] == h).all() for h in harn10) for sp in S if sp.startswith("P10"))
print("max share of a fresh P80 fold's scored pages inside one harness fold: %.3f (random 0.2); any P10 fresh seed equal to a harness seed: %s" % (mx80, mx10))
# my bootstrap
sp80 = sorted(s for s in any_cfg if s.startswith("P80")); sp10 = sorted(s for s in any_cfg if s.startswith("P10"))
def sel(d, w):
    a = sum((w[d[s][1]] * d[s][0]).sum() for s in sp80) / sum(w[d[s][1]].sum() for s in sp80)
    b = np.mean([(w[d[s][1]] * d[s][0]).sum() / w[d[s][1]].sum() for s in sp10])
    return np.array([(a + b) / 2, a, b])
rng = np.random.RandomState(7)
Wb = [np.bincount(rng.randint(0, npg, npg), minlength=npg).astype(float) for _ in range(2000)]
da = D[key(*CFG["a"])]
SA = np.array([sel(da, w) for w in Wb]); A0 = sel(da, np.ones(npg))
print("a (Stack oofmap=false) fresh sel %.4f P80 %.4f P10 %.4f" % tuple(A0))
for name in ("c", "b", "f", "dedup"):
    d = D.get(key(*CFG[name]))
    if d is None: print(name, "missing"); continue
    S0 = sel(d, np.ones(npg)); SB = np.array([sel(d, w) for w in Wb]); dd = SB - SA
    lo, hi = np.percentile(dd[:, 0], [2.5, 97.5])
    print("%-5s sel %.4f diff %+.4f SE %.4f CI [%+.4f, %+.4f] | P80 %+.4f P10 %+.4f" % (name, S0[0], S0[0] - A0[0], dd[:, 0].std(), lo, hi, S0[1] - A0[1], S0[2] - A0[2]))
