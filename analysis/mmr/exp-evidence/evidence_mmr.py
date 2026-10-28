"""MMR vs top-k evidence retrieval experiment. Run: venv/bin/python evidence_mmr.py"""
import json, re, time, os
import numpy as np, pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "..", "data")
FETCH = 100
KS = (5, 10, 20)
LAMS = (0.3, 0.5, 0.7, 0.9)
LABELS = ("true", "false", "unsure")

df = pd.read_csv(f"{DATA}/practice.csv")
lex = json.load(open(f"{DATA}/lexicon.json"))
N = len(df)
days = pd.to_datetime(df.date).map(lambda t: t.toordinal()).to_numpy()
labels = df.label.to_numpy()

# ---- gold structures (forms = oracle only)
def vnorm(v):
    return json.dumps({k: x for k, x in v.items() if k != "op"}, sort_keys=True)
rowkeys = []  # per row: dict key -> list of (valnorm, hasop)
for f in df.form:
    d = {}
    for it in json.loads(f):
        d.setdefault((it["subject"], it["attribute"]), []).append((vnorm(it["value"]), "op" in it["value"]))
    rowkeys.append(d)
bykey = {}
for i, d in enumerate(rowkeys):
    for k in d:
        bykey.setdefault(k, []).append(i)

R = [set() for _ in range(N)]
D = [set() for _ in range(N)]
for q in range(N):
    for k in rowkeys[q]:
        others = [j for j in bykey[k] if j != q]
        R[q].update(others)
        tr = [j for j in others if labels[j] == "true"]
        past = [j for j in tr if days[j] <= days[q]]
        fut = [j for j in tr if days[j] > days[q]]
        if past:
            m = max(days[j] for j in past); D[q].update(j for j in past if days[j] == m)
        if fut:
            m = min(days[j] for j in fut); D[q].update(j for j in fut if days[j] == m)

# ---- representations
aliases = []
for s in lex["subjects"]:
    for a in s.get("aliases", []):
        aliases.append((a, s["name"]))
aliases.sort(key=lambda x: -len(x[0]))
def alias_norm(t):
    for a, n in aliases:
        t = re.sub(r"(?<!\w)" + re.escape(a) + r"(?!\w)", n, t, flags=re.I)
    return t
texts = df.text.tolist()
texts_n = [alias_norm(t) for t in texts]
REPS = {
    "a word 1-2g tfidf": (TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True), texts),
    "b char_wb 3-5g tfidf": (TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True), texts),
    "c word 1-2g + alias norm": (TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True), texts_n),
}
XS = {n: v.fit_transform(t).tocsr() for n, (v, t) in REPS.items()}
SIMS = {}
for n, X in XS.items():
    S = (X @ X.T).toarray(); np.fill_diagonal(S, -np.inf); SIMS[n] = S

# ---- retrieval
def mmr(rel, div, lam, k):
    """rel: (P,), div: (P,P). returns list of pool positions (greedy, prefix-consistent)."""
    P = len(rel); sel = []; mx = np.zeros(P); avail = np.ones(P, bool)
    for t in range(min(k, P)):
        sc = lam * rel - (1 - lam) * mx if t else rel.copy()
        sc[~avail] = -np.inf
        j = int(np.argmax(sc)); sel.append(j); avail[j] = False
        mx = np.maximum(mx, div[j]) if t else div[j].copy()
    return sel

def retrieve(S, q, strat, k=20):
    row = S[q]
    pool = np.argpartition(-row, FETCH)[:FETCH]
    pool = pool[np.argsort(-row[pool], kind="stable")]
    c = row[pool]
    if strat == "T":
        return pool[:k]
    kind = strat[0]
    div = None
    sub = None
    if kind == "M":
        lam = float(strat[1:]); rel = c
    elif kind == "D":  # date-aware MMR: "D0.5"
        lam = float(strat[1:]); rel = c
    else:  # "R30" temporal relevance + MMR 0.7
        tau = float(strat[1:]); lam = 0.7
        rel = c * np.exp(-np.abs(days[q] - days[pool]) / tau)
    return pool, rel, lam, kind

_cache = {}
def run(S, q, strat, k=20):
    row = S[q]
    pool = np.argpartition(-row, FETCH)[:FETCH]
    pool = pool[np.argsort(-row[pool], kind="stable")]
    if strat == "T":
        return pool[:k]
    c = row[pool]
    cc = np.clip(S[np.ix_(pool, pool)], -1, 1)
    kind = strat[0]; v = float(strat[1:])
    if kind == "M":
        sel = mmr(c, cc, v, k)
    elif kind == "D":
        same = (days[pool][:, None] == days[pool][None, :]).astype(float)
        sel = mmr(c, 0.5 * cc + 0.5 * same, v, k)
    else:  # R: temporal relevance, plain cos diversity
        rel = c * np.exp(-np.abs(days[q] - days[pool]) / v)
        sel = mmr(rel, cc, 0.7, k)
    return pool[sel]

STRATS = ["T"] + [f"M{l}" for l in LAMS] + [f"D{l}" for l in LAMS] + ["R30", "R90"]

# ---- metrics
def metrics_for(S, q, ret, k):
    r = list(ret[:k]); rs = set(r)
    keys = list(rowkeys[q])
    hit = bool(rs & R[q])
    cov = np.mean([any(k_ in rowkeys[j] for j in r) for k_ in keys])
    dq = D[q]
    dall = (dq <= rs) if dq else np.nan
    dany = bool(dq & rs) if dq else np.nan
    dates = len({days[j] for j in r if j in R[q]})
    conf = False
    for j in r:
        for k_ in keys:
            if k_ in rowkeys[j] and rowkeys[j][k_][0][0] != rowkeys[q][k_][0][0]:
                conf = True
    sub = S[np.ix_(r, r)]; iu = np.triu_indices(len(r), 1)
    red = float(np.mean(sub[iu]))
    return dict(recall=hit, keycov=cov, dec_all=dall, dec_any=dany, dates=dates, conflict=conf, redund=red)

def verify(q, ret):
    """oracle verifier over retrieved true-labelled rows."""
    differs = False; allfound = True; compared = 0
    for k_, vals in rowkeys[q].items():
        qv, qop = vals[0]
        obs = [j for j in ret if labels[j] == "true" and k_ in rowkeys[j] and days[j] <= days[q]]
        if not obs:
            allfound = False; continue
        m = max(days[j] for j in obs)
        latest = [rowkeys[j][k_] for j in obs if days[j] == m]
        vs = [x for lst in latest for x in lst]
        if qop or all(op for _, op in vs):
            continue  # not comparable: skip key
        vs = [v for v, op in vs if not op]
        compared += 1
        if qv not in vs:
            differs = True
    if differs: return "false"
    if allfound and compared > 0: return "true"
    return "unsure"

def macro_f1(y, p):
    f = []
    for c in LABELS:
        tp = sum((a == c) and (b == c) for a, b in zip(y, p)); fp = sum((a != c) and (b == c) for a, b in zip(y, p))
        fn = sum((a == c) and (b != c) for a, b in zip(y, p))
        f.append(0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))

# ---- representation comparison (T only)
rep_rows = []
for n in SIMS:
    for k in KS:
        ms = [metrics_for(SIMS[n], q, run(SIMS[n], q, "T", k), k) for q in range(N)]
        rep_rows.append((n, k, np.mean([m["recall"] for m in ms]), np.mean([m["keycov"] for m in ms]),
                         np.nanmean([m["dec_all"] for m in ms]), np.nanmean([m["dec_any"] for m in ms])))
best = max((r for r in rep_rows if r[1] == 10), key=lambda r: r[2])[0]
S = SIMS[best]

# ---- run all strategies
RES = {}   # (strat,k) -> list of metric dicts ; VER[(strat,k)] -> preds
VER = {}
rets = {s: [run(S, q, s, 20) for q in range(N)] for s in STRATS}
for s in STRATS:
    for k in KS:
        RES[(s, k)] = [metrics_for(S, q, rets[s][q], k) for q in range(N)]
        if k in (10, 20):
            VER[(s, k)] = [verify(q, rets[s][q][:k]) for q in range(N)]
# ceiling: every true row in corpus retrieved
VER[("ALL", 0)] = [verify(q, [j for j in range(N) if j != q]) for q in range(N)]

# ---- timing (ms/query), single-query sparse path
X = XS[best]
def time_path(strat, Xc, nq=200):
    t = time.perf_counter()
    for q in range(nq):
        row = (Xc[q] @ Xc.T).toarray().ravel()
        row[q] = -np.inf
        pool = np.argpartition(-row, FETCH)[:FETCH]; pool = pool[np.argsort(-row[pool])]
        if strat == "T": continue
        sub = (Xc[pool] @ Xc[pool].T).toarray()
        mmr(row[pool], sub, 0.7, 20)
    return (time.perf_counter() - t) / nq * 1000
X10 = sp.vstack([X] * 10).tocsr()  # 19k-row corpus, same density (duplicated rows: cost proxy only)
timing = {(s, name): time_path(s, Xc) for s in ("T", "M") for name, Xc in (("1.9k corpus", X), ("19k corpus (10x tiled)", X10))}

# ---- report
def agg(ms, idx, key):
    v = [ms[i][key] for i in idx]; v = [x for x in v if not (isinstance(x, float) and np.isnan(x))]
    return float(np.mean(v)) if v else float("nan")
COLS = [("recall", "Rec@k"), ("keycov", "KeyCov"), ("dec_all", "Dec-all"), ("dec_any", "Dec>=1"),
        ("dates", "Dates"), ("conflict", "Conflict"), ("redund", "Redund")]
def table(idx, ks):
    out = ["| strat | k | " + " | ".join(c[1] for c in COLS) + " |", "|" + "---|" * (len(COLS) + 2)]
    for k in ks:
        for s in STRATS:
            out.append(f"| {s} | {k} | " + " | ".join(f"{agg(RES[(s, k)], idx, c[0]):.3f}" for c in COLS) + " |")
    return "\n".join(out)
allidx = list(range(N))
byl = {l: [i for i in range(N) if labels[i] == l] for l in LABELS}
Dn = sum(1 for q in range(N) if D[q])
md = []
md.append("# Evidence retrieval: MMR vs top-k (practice data)\n")
md.append(f"Queries: {N} practice rows (true {len(byl['true'])}, false {len(byl['false'])}, unsure {len(byl['unsure'])}). "
          f"Corpus per query: the other {N-1} practice rows. Queries with non-empty D(q): {Dn}. "
          f"Mean |R(q)| = {np.mean([len(r) for r in R]):.1f}, mean |D(q)| = {np.mean([len(d) for d in D if d]):.2f}.\n")
md.append("Strategy codes: T = top-k cosine; M<l> = MMR lambda l; D<l> = date-aware MMR (diversity 0.5 cos + 0.5 same-date); "
          "R<tau> = temporal relevance cos*exp(-|dd|/tau) then MMR lambda 0.7. Columns: Rec@k = >=1 retrieved row in R(q); "
          "KeyCov = mean fraction of q keys covered; Dec-all / Dec>=1 = decisive set fully / partly retrieved (queries with non-empty D); "
          "Dates = distinct dates among retrieved relevant rows; Conflict = retrieved relevant row with differing value on a shared key; "
          "Redund = mean pairwise cosine in retrieved set.\n")
md.append("## Representation comparison (strategy T)\n")
md.append("| representation | k | Rec@k | KeyCov | Dec-all | Dec>=1 |\n|---|---|---|---|---|---|")
for r in rep_rows:
    md.append(f"| {r[0]} | {r[1]} | {r[2]:.3f} | {r[3]:.3f} | {r[4]:.3f} | {r[5]:.3f} |")
md.append(f"\nBest by Recall@10: **{best}** (used for everything below).\n")
md.append("## Strategies, overall\n"); md.append(table(allidx, KS))
for l in LABELS:
    md.append(f"\n## Strategies, queries with gold label = {l} (n={len(byl[l])}), k=10 and 20\n"); md.append(table(byl[l], (10, 20)))
md.append("\n## Oracle verifier (perfect parser, retrieved true-labelled rows only)\n")
md.append("Rule: per key of q, latest retrieved true row with date <= q.date; any differing value -> false; else all keys found and >=1 comparable key and all equal -> true; else unsure. "
          "Keys where q's value or all latest observations carry an op are skipped (not comparable). Ties on the latest date: key equal if q's value is among them. "
          "ALL = ceiling, every other true row visible.\n")
md.append("| strat | k | acc | macroF1 | acc(true) | acc(false) | acc(unsure) |\n|---|---|---|---|---|---|---|")
for key in [("ALL", 0)] + [(s, k) for k in (10, 20) for s in STRATS]:
    p = VER[key]
    accs = [np.mean([p[i] == labels[i] for i in byl[l]]) for l in LABELS]
    md.append(f"| {key[0]} | {key[1] or '-'} | {np.mean(p == labels):.3f} | {macro_f1(labels, p):.3f} | " + " | ".join(f"{a:.3f}" for a in accs) + " |"
              if False else
              f"| {key[0]} | {key[1] or '-'} | {np.mean([p[i]==labels[i] for i in range(N)]):.3f} | {macro_f1(list(labels), p):.3f} | " + " | ".join(f"{a:.3f}" for a in accs) + " |")
md.append("\n## Timing (ms/query, fetch_k=100, k=20, one core, includes sparse q-vs-corpus product)\n")
md.append("| strat | corpus | ms/query |\n|---|---|---|")
for (s, name), v in timing.items():
    md.append(f"| {s if s=='T' else 'M0.7'} | {name} | {v:.2f} |")
md.append("\nAt 18,000 queries: ms/query x 18 = seconds total (single core). 19k tiled corpus duplicates rows, so it is a cost proxy for the matmul, not a quality test.\n")
open(f"{HERE}/REPORT_body.md", "w").write("\n".join(md))
print("\n".join(md))
