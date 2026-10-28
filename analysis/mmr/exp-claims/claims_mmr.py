"""MMR / diversity selection vs top-k on the practice data, under correlated base-fact failures.

Run: <venv python> claims_mmr.py   (writes results.md + CSVs next to this file)
Read-only on the repo data/ folder. Seed fixed. See REPORT.md for interpretation.
"""
import json, math, re, time
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

T0 = time.time()
SEED = 20261029
DRAWS = 5000
ASOF = date(2026, 10, 29)
DATA = Path(__file__).resolve().parents[3] / "data"
OUT = Path(__file__).resolve().parent
TYPES = ["fact", "compare", "change", "at_event", "relation"]

# ---------------------------------------------------------------- lexicon + rows
lex = json.loads((DATA / "lexicon.json").read_text())
alias = {}
for s in lex["subjects"]:
    for nm in [s["name"], *s["aliases"]]:
        alias[nm.casefold()] = s["name"]
EVENTS = set(lex["events"])
rows = pd.read_csv(DATA / "practice.csv", dtype=str)

UNIT = {  # quantity unit -> (dimension, factor); anything else is a counted noun
    **{u: ("data", f) for u, f in [("B", 1), ("KB", 1e3), ("MB", 1e6), ("GB", 1e9), ("TB", 1e12)]},
    **{u: ("length", f) for u, f in [("mm", 1e-3), ("cm", 1e-2), ("m", 1), ("km", 1e3), ("in", 0.0254), ("inch", 0.0254)]},
    **{u: ("mass", f) for u, f in [("g", 1), ("kg", 1e3), ("tonne", 1e6)]},
    **{u: ("freq", f) for u, f in [("Hz", 1), ("kHz", 1e3), ("MHz", 1e6), ("GHz", 1e9)]},
    **{u: ("power", f) for u, f in [("mW", 1e-3), ("W", 1), ("kW", 1e3)]},
    "mAh": ("mAh", 1),
}
DUR = {"ms": ("time", 1e-3), "s": ("time", 1), "min": ("time", 60), "h": ("time", 3600), "day": ("time", 86400),
       "week": ("time", 604800), "month": ("cal", 1), "year": ("cal", 12)}


def canon(v):
    """-> (canonical id, compare dimension or None, comparable magnitude)."""
    k, x = v["kind"], v["value"]
    if k == "quantity":
        dim, f = UNIT.get(v.get("unit"), ("count:" + str(v.get("unit")).lower(), 1))
        n = float(x) * f
        return f"q|{dim}|{n:.9g}", "q|" + dim, n
    if k == "money":
        dim = f"money|{v.get('currency')}|{v.get('per') or ''}"
        return f"{dim}|{float(x):.9g}", dim, float(x)
    if k == "duration":
        dim, f = DUR[v["unit"]]
        n = float(x) * f
        return f"d|{dim}|{n:.9g}", "d|" + dim, n
    if k == "percent":
        return f"pct|{float(x):.9g}", "percent", float(x)
    if k == "version":
        t = tuple(int(d) for d in re.findall(r"\d+", str(x)))
        return "v|" + ".".join(map(str, t)), "version", t
    if k == "date":
        return "dt|" + str(x), "date", str(x)
    if k == "name":
        return "n|" + str(x).casefold(), None, None
    return "b|" + str(x).lower(), None, None  # boolean


def cmp(dim, a, b):
    """gt/lt/eq, or None if not decidable (dates of overlapping precision)."""
    if dim == "date":
        if len(a) != len(b):
            m = min(len(a), len(b))
            if a[:m] == b[:m]:
                return None  # ponytail: '2026-06' vs '2026-06-09' overlap -> skip, not guess
            a, b = a[:m], b[:m]
    elif dim == "version":
        m = max(len(a), len(b))
        a, b = a + (0,) * (m - len(a)), b + (0,) * (m - len(b))
    elif math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12):
        return "eq"
    return "gt" if a > b else "lt" if a < b else "eq"


# exploded assertions
A = []
for r in rows.itertuples():
    for v in json.loads(r.form):
        val = v["value"]
        subj = alias.get(v["subject"].casefold(), v["subject"])
        cid, dim, num = canon(val)
        A.append(dict(row=r.id, label=r.label, date=date.fromisoformat(r.date), key=(subj, v["attribute"]),
                      kind=val["kind"], op=val.get("op", "eq"), cid=cid, dim=dim, num=num, raw=val))
A = pd.DataFrame(A)
false_rows = A[A.label == "false"].groupby("key").row.nunique().to_dict()
unsure_rows = A[A.label == "unsure"].groupby("key").row.nunique().to_dict()
O = A[(A.label == "true") & (A.op == "eq")].copy()
# ponytail: date keys with any day-precision obs keep only day-precision obs ('2026' then '2026-06-09' is a refinement, not a change)
dayk = set(O[(O.kind == "date") & (O.raw.map(lambda v: len(str(v["value"])) == 10))].key)
O = O[~((O.kind == "date") & O.key.isin(dayk) & O.raw.map(lambda v: len(str(v["value"])) != 10))]
O = O.sort_values(["key", "date", "row"]).reset_index(drop=True)
support = O.groupby(["key", "cid"]).row.nunique().to_dict()

# per-key chronology: one value per date (dates with conflicting true values dropped), consecutive duplicates collapsed
KS = {}
for key, g in O.groupby("key", sort=False):
    per_date = g.groupby("date").cid.agg(lambda s: sorted(set(s)))
    seq = [(d, c[0]) for d, c in per_date.items() if len(c) == 1]
    runs = [x for i, x in enumerate(seq) if i == 0 or x[1] != seq[i - 1][1]]
    info = {c: (g[g.cid == c].iloc[0].raw, g[g.cid == c].iloc[0].dim, g[g.cid == c].iloc[0].num) for c in g.cid.unique()}
    KS[key] = dict(seq=seq, runs=runs, info=info, n_distinct=g.cid.nunique(), first=g.date.min(), last=g.date.max(),
                   latest_conflict=len(per_date.iloc[-1]) > 1, latest_date=per_date.index[-1], latest=per_date.iloc[-1][0])


# ---------------------------------------------------------------- reliability proxy
A_PRIOR, B_PRIOR = 4.0, 1.0  # Beta(4,1) prior: mean 0.8 for an unchallenged single observation


def p_val(key, s):
    """P(the value we use for `key` is right), s = #true rows supporting it. Monotone: up in s, down in false/unsure/volatility."""
    f, u = false_rows.get(key, 0), unsure_rows.get(key, 0)
    vol = 1.0 / (1.0 + 0.1 * (KS[key]["n_distinct"] - 1))
    return (s + A_PRIOR) / (s + A_PRIOR + B_PRIOR + f + 0.5 * u) * vol


def p_fresh(key, days):
    """P(value unchanged after `days`): Poisson change hazard h = (changes + 0.5) / (span + 365 days)."""
    k = KS[key]
    h = (len(k["runs"]) - 1 + 0.5) / ((k["last"] - k["first"]).days + 365.0)
    return math.exp(-h * max(days, 0))


# ---------------------------------------------------------------- candidate pool
C = []  # dict(type, keys:[k1,k2], pu:[..], ps:[..], form)


def add(t, keys, pu, ps, form):
    C.append(dict(type=t, keys=keys, pu=pu, ps=ps, form=form))


facts = {}
for key, k in KS.items():
    if k["latest_conflict"]:
        continue
    c = k["latest"]
    raw, dim, num = k["info"][c]
    pu, ps = p_val(key, support[(key, c)]), p_fresh(key, (ASOF - k["latest_date"]).days)
    facts[key] = (c, dim, num, pu, ps)
    add("fact", [key], [pu], [ps], dict(subject=key[0], attribute=key[1], value=raw))

# change: consecutive distinct values
for key, k in KS.items():
    seen = set()
    for (d0, c0), (d1, c1) in zip(k["runs"], k["runs"][1:]):
        if (c0, c1) in seen:
            continue
        seen.add((c0, c1))
        s = min(support[(key, c0)], support[(key, c1)])
        add("change", [key], [p_val(key, s)], [1.0],
            dict(subject=key[0], attribute=key[1], **{"from": k["info"][c0][0], "to": k["info"][c1][0]}))

# compare: unordered pairs of fact candidates of one dimension (one orientation per pair)
by_dim = defaultdict(list)
for key, (c, dim, num, pu, ps) in facts.items():
    if isinstance(dim, str):  # name/boolean have no dimension (pandas turns None into NaN)
        by_dim[dim].append(key)
n_cmp_skipped = 0
for dim, keys in by_dim.items():
    keys = sorted(keys)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = facts[keys[i]], facts[keys[j]]
            op = cmp("date" if dim == "date" else "version" if dim == "version" else "num", a[2], b[2])
            if op is None:
                n_cmp_skipped += 1
                continue
            add("compare", [keys[i], keys[j]], [a[3], b[3]], [a[4], b[4]],
                dict(left=dict(subject=keys[i][0], attribute=keys[i][1]),
                     right=dict(subject=keys[j][0], attribute=keys[j][1]), op=op))

# at_event: every key x every event with a day-precision date <= as-of; value = latest unique obs at/before event date
ev_dates = {}
for e in EVENTS:
    ek = (e, "date")
    if ek in facts and len(facts[ek][2]) == 10 and date.fromisoformat(facts[ek][2]) <= ASOF:
        ev_dates[e] = date.fromisoformat(facts[ek][2])
for e, D in sorted(ev_dates.items()):
    ek = (e, "date")
    epu, eps = facts[ek][3], facts[ek][4]
    for key, k in KS.items():
        if key[1] == "date" and key[0] in EVENTS:
            continue  # ponytail: an event's date at another event is degenerate, skipped
        prior = [x for x in k["seq"] if x[0] <= D]
        if not prior:
            continue
        d, c = prior[-1]
        add("at_event", [key, ek], [p_val(key, support[(key, c)]), epu], [p_fresh(key, (D - d).days), eps],
            dict(subject=key[0], attribute=key[1], event=e, value=k["info"][c][0]))

# relation: name-valued link keys resolving to a lexicon subject; target obs dated inside the link's run
for lkey, k in KS.items():
    runs = k["runs"]
    for i, (d0, c) in enumerate(runs):
        raw = k["info"][c][0]
        if raw["kind"] != "name" or str(raw["value"]).casefold() not in alias:
            continue
        T = alias[str(raw["value"]).casefold()]
        d1 = runs[i + 1][0] if i + 1 < len(runs) else date.max
        lp = p_val(lkey, support[(lkey, c)])
        for tkey, tk in KS.items():
            if tkey[0] != T:
                continue
            for tc in {c2 for d, c2 in tk["seq"] if d0 <= d < d1}:
                add("relation", [lkey, tkey], [lp, p_val(tkey, support[(tkey, tc)])], [1.0, 1.0],
                    dict(subject=lkey[0], link=lkey[1], target=T, attribute=tkey[1], value=tk["info"][tc][0]))

# dedupe relation dups across runs of the same target (A->B->A)
seen, C2 = set(), []
for c in C:
    sig = (c["type"], json.dumps(c["form"], sort_keys=True))
    if sig not in seen:
        seen.add(sig)
        C2.append(c)
C = C2

# ---------------------------------------------------------------- arrays
rng = np.random.default_rng(SEED)
perm = rng.permutation(len(C))  # random tie-break order, fixed seed
C = [C[i] for i in perm]
n = len(C)
keys_all = sorted({k for c in C for k in c["keys"]})
KID = {k: i for i, k in enumerate(keys_all)}
K = len(keys_all)
subj_all = sorted({k[0] for k in keys_all})
SID = {s: i for i, s in enumerate(subj_all)}
ctype = np.array([TYPES.index(c["type"]) for c in C])
k1 = np.array([KID[c["keys"][0]] for c in C])
k2 = np.array([KID[c["keys"][1]] if len(c["keys"]) > 1 and c["keys"][1] != c["keys"][0] else -1 for c in C])
pu = np.array([[c["pu"][0], c["pu"][1] if len(c["pu"]) > 1 else 1.0] for c in C])
ps = np.array([[c["ps"][0], c["ps"][1] if len(c["ps"]) > 1 else 1.0] for c in C])
P = (pu * ps).prod(axis=1)
nkeys = 1 + (k2 >= 0)
subjs = [sorted({SID[k[0]] for k in c["keys"]}) for c in C]
cand_of_key = defaultdict(list)
cand_of_subj = defaultdict(list)
for i in range(n):
    cand_of_key[k1[i]].append(i)
    if k2[i] >= 0:
        cand_of_key[k2[i]].append(i)
    for s in subjs[i]:
        cand_of_subj[s].append(i)
cand_of_key = {k: np.array(v) for k, v in cand_of_key.items()}
cand_of_subj = {s: np.array(v) for s, v in cand_of_subj.items()}
setid = pd.factorize(pd.Series([tuple(sorted(c["keys"])) for c in C]))[0]


def sim_row(j):
    """sim(j, .) = min(1, Jaccard(base keys) + 0.3*[share a subject] + 0.1*[same type])."""
    inter = np.zeros(n)
    for k in (k1[j], k2[j]):
        if k >= 0:
            inter[cand_of_key[k]] += 1
    jac = inter / (nkeys + nkeys[j] - inter)
    ss = np.zeros(n, bool)
    for s in subjs[j]:
        ss[cand_of_subj[s]] = True
    return np.minimum(1.0, jac + 0.3 * ss + 0.1 * (ctype == ctype[j]))


# ---------------------------------------------------------------- strategies
def top_k(k):
    return np.argsort(-P, kind="stable")[:k]


def mmr(k, lam, quota=None, cap_C=None, agg="max"):
    """MMR greedy. cap_C: skip candidates whose base key already has cap_C picks (S6/S7).
    agg='max': penalty = max sim to selected (S1); agg='top3': mean of the 3 largest sims to selected (S7)."""
    maxsim, sel, taken = np.zeros(n), [], np.zeros(n, bool)
    top3 = np.zeros((n, 3))  # 3 largest sims to selected, ascending
    used, blocked = np.zeros(K, int), np.zeros(n, bool)
    cnt, diag = np.zeros(len(TYPES), int), []
    for t in range(k):
        if t in (50, 100, 500):  # saturation diagnostic: median penalty of the not-yet-selected pool
            diag.append(f"med_pen@{t}={np.median(maxsim[~taken]):.2f}")
        sc = lam * P - (1 - lam) * maxsim
        sc[taken | blocked] = -np.inf
        if quota is not None:
            sc[cnt[ctype] >= quota[ctype]] = -np.inf
        j = int(np.argmax(sc))
        assert np.isfinite(sc[j]), "pool exhausted under cap"
        sel.append(j); taken[j] = True; cnt[ctype[j]] += 1
        if cap_C is not None:
            for x in (k1[j], k2[j]):
                if x >= 0:
                    used[x] += 1
                    if used[x] >= cap_C:
                        blocked[cand_of_key[x]] = True
        row = sim_row(j)
        if agg == "max":
            np.maximum(maxsim, row, out=maxsim)
        else:
            top3 = np.sort(np.column_stack([top3, row]), axis=1)[:, 1:]
            maxsim = top3.sum(1) / min(t + 1, 3)  # mean over the top-3 (fewer while |S| < 3)
    return np.array(sel), " ".join(diag)


def cap(k, C_):
    used, sel = np.zeros(K, int), []
    for j in np.argsort(-P, kind="stable"):
        ks = [x for x in (k1[j], k2[j]) if x >= 0]
        if all(used[x] < C_ for x in ks):
            sel.append(j)
            for x in ks:
                used[x] += 1
            if len(sel) == k:
                break
    return np.array(sel)


def quotas(k):
    avail = np.bincount(ctype, minlength=len(TYPES))
    q = np.zeros(len(TYPES), int)
    left = k
    while left > 0:  # water-filling: equal share, capped by availability
        open_ = np.where(q < avail)[0]
        share = max(1, left // len(open_))
        for t in open_:
            add_ = min(share, avail[t] - q[t], left)
            q[t] += add_; left -= add_
            if left == 0:
                break
    return q


def coverage(k, mu):
    newk, taken, sel = nkeys.astype(float), np.zeros(n, bool), []
    covered = np.zeros(K, bool)
    for _ in range(k):
        sc = P + mu * newk
        sc[taken] = -np.inf
        j = int(np.argmax(sc))
        sel.append(j); taken[j] = True
        for x in (k1[j], k2[j]):
            if x >= 0 and not covered[x]:
                covered[x] = True
                newk[cand_of_key[x]] -= 1
    return np.array(sel)


def dpp(k, eps=1e-3):
    """Greedy DPP MAP (Chen et al. 2018), L = diag(q) (S + eps I) diag(q), q = P. Fills by P once gains go <= 0."""
    Cm = np.zeros((k, n))
    d2 = P ** 2 * (1 + eps)
    taken, sel = np.zeros(n, bool), []
    for t in range(k):
        d2m = np.where(taken, -np.inf, d2)
        j = int(np.argmax(d2m))
        if d2m[j] <= 1e-12:
            break
        sel.append(j); taken[j] = True
        Lj = P[j] * P * sim_row(j)
        Lj[j] = P[j] ** 2 * (1 + eps)
        e = (Lj - Cm[:t].T @ Cm[:t, j]) / math.sqrt(d2[j])
        Cm[t] = e
        d2 = d2 - e ** 2
    n_dpp = len(sel)
    if n_dpp < k:
        rest = [j for j in np.argsort(-P, kind="stable") if not taken[j]][: k - n_dpp]
        sel += rest
    return np.array(sel), f"dpp_picked={n_dpp}" 


# ---------------------------------------------------------------- Monte Carlo (common random numbers for all strategies)
U = rng.random((DRAWS, K))  # value-correctness draw per key
V = rng.random((DRAWS, K))  # still-current draw per key (comonotone across candidates sharing the key)


def simulate(sel, pu_=pu, ps_=ps, force_wrong=()):
    ok = np.ones((DRAWS, len(sel)), bool)
    Uf = U
    if force_wrong:
        Uf = U.copy(); Uf[:, list(force_wrong)] = 2.0
    for slot, kk in ((0, k1[sel]), (1, k2[sel])):
        m = kk >= 0
        idx = np.where(m)[0]
        ok[:, idx] &= (Uf[:, kk[m]] < pu_[sel[m], slot]) & (V[:, kk[m]] < ps_[sel[m], slot])
    return ok


def exposure(sel):
    cnt = np.bincount(np.concatenate([k1[sel], k2[sel][k2[sel] >= 0]]), minlength=K)
    return cnt


def metrics(sel, k, ok):
    tot = ok.sum(1)
    cnt = exposure(sel)
    mix = np.bincount(ctype[sel], minlength=5)
    g = pd.factorize(setid[sel])[0]
    ind = sp.csr_matrix((np.ones(len(sel)), (g, np.arange(len(sel)))))
    h2 = ((ind @ ok.T.astype(np.float32)) > 0).sum(0)
    dk = int((cnt > 0).sum())
    return dict(E=tot.mean(), sd=tot.std(), p5=np.percentile(tot, 5), p1=np.percentile(tot, 1),
                P95=(tot >= 0.95 * k).mean(), maxexp=int(cnt.max()), keys=dk,
                subj=len({s for j in sel for s in subjs[j]}),
                mix="/".join(map(str, mix)), sumP=P[sel].sum(),
                H1=tot.mean() / k, H2=h2.mean() / k, H3=tot.mean() * math.sqrt(dk / k) / k)


# scenario thresholds
flag = np.array([false_rows.get(k, 0) > 0 for k in keys_all])
pu_lie = pu.copy()
for slot, kk in ((0, k1), (1, k2)):
    m = (kk >= 0) & flag[np.maximum(kk, 0)]
    pu_lie[m, slot] = 0.5
comb = pu * ps
pu_shr = np.minimum(1.0, (0.5 + 0.7 * (comb - 0.5)) / ps)

results, stress, adv = [], [], []
for k in (1000, 100):
    q = quotas(k)
    strategies = [("S0 top-k", lambda: top_k(k))]
    strategies += [(f"S1 MMR l={lam}", (lambda lam=lam: mmr(k, lam))) for lam in (0.5, 0.7, 0.85, 0.95)]
    strategies += [(f"S2 cap C={c_}", (lambda c_=c_: cap(k, c_))) for c_ in (3, 5, 10)]
    strategies += [("S3 quota+MMR .85", lambda: mmr(k, 0.85, q))]
    strategies += [(f"S4 cover mu={mu}", (lambda mu=mu: coverage(k, mu))) for mu in (0.1, 0.3)]
    strategies += [("S5 DPP greedy", lambda: dpp(k))]
    strategies += [(f"S6 cap C={c_}+MMR l={lam}", (lambda c_=c_, lam=lam: mmr(k, lam, cap_C=c_)))
                   for c_ in (5, 10) for lam in (0.5, 0.7, 0.85)]
    strategies += [(f"S7 cap C=10+top3 l={lam}", (lambda lam=lam: mmr(k, lam, cap_C=10, agg="top3"))) for lam in (0.7, 0.85)]
    for name, fn in strategies:
        t = time.time()
        sel = fn()
        note = ""
        if isinstance(sel, tuple):
            sel, note = sel
        assert len(sel) == k and len(set(sel.tolist())) == k, name
        if "cap C=" in name:
            assert exposure(sel).max() <= int(name.split("C=")[1].split("+")[0]), name
        ok = simulate(sel)
        m = metrics(sel, k, ok)
        assert abs(m["E"] - m["sumP"]) < 4 * m["sd"] / math.sqrt(DRAWS) + 1e-6, (name, m["E"], m["sumP"])  # MC == analytic mean
        results.append(dict(k=k, strategy=name, secs=round(time.time() - t, 2), note=note, **m))
        for scen, pu_ in (("lying-page", pu_lie), ("shrink30", pu_shr)):
            tot = simulate(sel, pu_=pu_).sum(1)
            stress.append(dict(k=k, strategy=name, scenario=scen, E=tot.mean(), sd=tot.std(),
                               p5=np.percentile(tot, 5), p1=np.percentile(tot, 1), P95=(tot >= 0.95 * k).mean()))
        cnt = exposure(sel)
        top = np.argsort(-cnt, kind="stable")
        for nk in (1, 5):
            hit = np.isin(k1[sel], top[:nk]) | np.isin(k2[sel], top[:nk])
            Ec = simulate(sel, force_wrong=top[:nk].tolist()).sum(1).mean()
            adv.append(dict(k=k, strategy=name, worst_keys=nk, lost_claims=int(hit.sum()),
                            E_given_wrong=Ec, drop_vs_E=m["E"] - Ec,
                            keys=", ".join(f"{keys_all[x][0]}.{keys_all[x][1]}({cnt[x]})" for x in top[:nk])))
        print(f"k={k} {name}: E={m['E']:.1f} sd={m['sd']:.1f} ({time.time() - T0:.0f}s)", flush=True)

R, S, AD = pd.DataFrame(results), pd.DataFrame(stress), pd.DataFrame(adv)
R.to_csv(OUT / "results.csv", index=False); S.to_csv(OUT / "stress.csv", index=False); AD.to_csv(OUT / "adversarial.csv", index=False)

# ---------------------------------------------------------------- pool + dependency stats
pool = pd.Series(ctype).map(dict(enumerate(TYPES))).value_counts().reindex(TYPES)
deg = np.bincount(np.concatenate([k1, k2[k2 >= 0]]), minlength=K)
top10 = np.argsort(-deg)[:10]
cmp_m = ctype == 1
share_top10 = (np.isin(k1[cmp_m], top10) | np.isin(k2[cmp_m], top10)).mean()
P_by_type = pd.Series(P).groupby(pd.Series(ctype).map(dict(enumerate(TYPES)))).describe()[["mean", "min", "25%", "50%", "75%", "max"]]


def md(df, ff=".3f"):
    """Minimal markdown table (no tabulate dependency)."""
    f = lambda x: format(x, ff) if isinstance(x, (float, np.floating)) else str(x)
    rows_ = [list(map(str, df.columns))] + [[f(x) for x in r] for r in df.itertuples(index=False)]
    return "\n".join(["| " + " | ".join(rows_[0]) + " |", "|" + "---|" * len(df.columns)] + ["| " + " | ".join(r) + " |" for r in rows_[1:]])


lines = [f"# results (seed {SEED}, {DRAWS} draws, {time.time() - T0:.0f}s)", "",
         f"observations: {len(O)} true exact assertions over {O.key.nunique()} keys; fact candidates {len(facts)}; "
         f"compare pairs skipped as date-overlap-undecidable: {n_cmp_skipped}; events with usable date: {len(ev_dates)} "
         f"({', '.join(f'{e} {d}' for e, d in sorted(ev_dates.items()))})", "",
         "## pool", "", md(pool.rename("candidates").reset_index().rename(columns={"index": "type"})),
         f"\ntotal {n}; distinct base keys {K}; distinct subjects {len(subj_all)}", "",
         "## candidate p by type", "", md(P_by_type.reset_index()), "",
         "## dependency (pool)", "",
         f"candidates per base key: max {deg.max()}, p90 {np.percentile(deg, 90):.0f}, mean {deg.mean():.1f}, median {np.median(deg):.0f}",
         f"share of compare candidates touching the 10 most-connected keys: {share_top10:.3f}",
         "top-10 keys: " + ", ".join(f"{keys_all[x][0]}.{keys_all[x][1]}({deg[x]})" for x in top10), ""]
cols = ["strategy", "E", "sd", "p5", "p1", "P95", "maxexp", "keys", "subj", "mix", "H1", "H2", "H3", "note"]
for k in (1000, 100):
    lines += [f"## strategies k={k} (mix = fact/compare/change/at_event/relation)", "",
              md(R[R.k == k][cols]), ""]
for k in (1000, 100):
    piv = S[S.k == k].pivot(index="strategy", columns="scenario", values=["E", "sd", "p5", "p1"])
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    lines += [f"## stress k={k}", "", md(piv.reindex(R[R.k == k].strategy).reset_index(), ".1f"), ""]
    lines += [f"## adversarial k={k}", "", AD[AD.k == k][["strategy", "worst_keys", "lost_claims", "E_given_wrong", "drop_vs_E", "keys"]]
              .pipe(md, ".1f"), ""]
# ---------------------------------------------------------------- follow-up: hybrids S6/S7 vs references, maximin over H1-H3
for h in ("H1", "H2", "H3"):  # best = best strategy at that k over ALL strategies S0-S7
    R[h + "_rel"] = R[h] / R.groupby("k")[h].transform("max")
R["maximin"] = R[["H1_rel", "H2_rel", "H3_rel"]].min(1)
R.to_csv(OUT / "results.csv", index=False)
focus = lambda df: df[df.strategy.str.match(r"S0|S1 MMR l=0\.[57]$|S2 cap C=10|S6|S7")]
lines += ["# follow-up: S6 (cap + max-sim MMR), S7 (cap + top3-mean MMR)", ""]
for k in (1000, 100):
    Rk, Sk, Ak = focus(R[R.k == k]), focus(S[S.k == k]), focus(AD[AD.k == k])
    lines += [f"## hybrid main k={k}", "", md(Rk[["strategy", "E", "sd", "p5", "p1", "maxexp", "keys", "subj", "mix"]], ".1f"), ""]
    st = Sk.assign(cell=Sk.E.map("{:.1f}".format) + " / " + Sk.p5.map("{:.0f}".format) + " / " + Sk.p1.map("{:.0f}".format))
    st = st.pivot(index="strategy", columns="scenario", values="cell").reindex(Rk.strategy).reset_index()
    lines += [f"## hybrid stress k={k} (E / p5 / p1)", "", md(st), ""]
    av = Ak.assign(cell=Ak.lost_claims.astype(str) + " / " + Ak.E_given_wrong.map("{:.1f}".format))
    av = av.pivot(index="strategy", columns="worst_keys", values="cell").reindex(Rk.strategy).reset_index()
    av.columns = ["strategy", "worst 1 (lost / E|wrong)", "worst 5 (lost / E|wrong)"]
    lines += [f"## hybrid adversarial k={k}", "", md(av), ""]
    lines += [f"## hybrid scoring k={k} (rel = value / best over all S0-S7 at this k; maximin = min rel)", "",
              md(Rk[["strategy", "H1", "H2", "H3", "H1_rel", "H2_rel", "H3_rel", "maximin"]]), ""]
    lines += [f"## maximin ranking, all strategies, k={k}", "",
              md(R[R.k == k].sort_values("maximin", ascending=False)[["strategy", "maximin", "H1_rel", "H2_rel", "H3_rel", "p1"]]), ""]
(OUT / "results.md").write_text("\n".join(lines))
print("\n".join(lines))
