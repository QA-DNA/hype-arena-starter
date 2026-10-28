"""w6: does a neural text layer add anything to V9 (per-fact bracket-feature LR) / V11 (V9 + one self-training round)?
E1 fusion_text (row p_text from bge-small or TF-IDF, nested OOF), E2 fusion_copy (embedding near-duplicate features),
E3 fusion_dedup (collapse near-duplicate / same key-value-day observations to one vote), E4 arena, E5 MLP fusion.
Works on the COPY of labs/kb-experiments in ./kb (only change there: DATA path, and v9._v9_rest stashes prow_tr).
Run (from anywhere):  python -I fusion.py base            -> cache/base.json   (R80 + R10, all variants)
                      python -I fusion.py base R10x       -> cache/base_R10x.json (50 extra R10 seeds 10..59)
                      python -I fusion.py hlie|hctrl SEED -> cache/<scen>_<seed>.json (one R10 split, tell-free copies)
                      python -I fusion.py hpara SEED      -> hlie copies with a reworded prefix (exact text no longer matches)
                      python -I fusion.py check           -> asserts: ff == v9.fact_feats, p_text nesting, dedup sanity
"""
import os, sys, json, math, time
SCEN = sys.argv[1] if len(sys.argv) > 1 else 'base'
SEED = int(sys.argv[2]) if len(sys.argv) > 2 and SCEN in ('hlie', 'hctrl', 'hpara') else None
if SCEN in ('hlie', 'hctrl', 'hpara'):
    os.environ['KB_COPY'] = f"{'hlie' if SCEN == 'hpara' else SCEN}:{SEED}"
W = '/tmp/veridyct-emb/w6'
sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, W + '/kb')
import harness as H
H.set_threads(int(os.environ.get('W6_THREADS', '1')))
import numpy as np
import v9 as V9M
from v9 import *  # noqa: ROWS PAGE Y OBS NP FIDX FROW FPAGE YF BASE roles kern Fact metrics GroupKFold random C
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

COPY = np.array([bool(r.get('copy')) for r in ROWS])
NP_ORIG = int(PAGE[~COPY].max()) + 1
PR = dict(BASE, interval=True)
PARA = {1: 'Reportedly, ', 7: 'According to one report, ', 30: 'Sources say that '}  # hpara: copy at +d days gets this prefix
if SCEN == 'hpara':  # same copies as hlie (same facts, dates, pages); only the wording changes, so exact-text matching misses them
    for r in ROWS:
        if r.get('copy'):
            t = r['text']; r['text'] = PARA[int(r['id'][2:].split('-', 1)[0])] + t
TEXT = [r['text'] for r in ROWS]

# ---------------------------------------------------------------- embeddings (cached by embed.py, mapped by text)
_c = json.load(open(W + '/cache/texts.json')); _E = np.load(W + '/cache/bge_small.npy').astype(np.float64)
_ti = {t: n for n, t in enumerate(_c['texts'])}
_miss = sorted({t for t in TEXT if t not in _ti})
if _miss:  # hpara only: encode the reworded copies with the same model (normalised, as embed.py)
    import torch; torch.set_num_threads(1)
    from sentence_transformers import SentenceTransformer
    _E2 = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu').encode(_miss, batch_size=32, normalize_embeddings=True,
                                                                              show_progress_bar=False).astype(np.float64)
    _E = np.r_[_E, _E2]; _ti.update({t: len(_c['texts']) + n for n, t in enumerate(_miss)})
EMB = _E[[_ti[t] for t in TEXT]]  # hlie/hctrl copies share their source's text, hence its vector
S = EMB @ EMB.T
S_OTHER = np.where(PAGE[:, None] != PAGE[None, :], S, -1.0)  # other-page cosine only
KEYS = [{(f.key[0], f.key[1]) for f in r['facts']} for r in ROWS]  # harness key = (subject, attribute)


def copy_feats():
    """E2, label-free, per row: max other-page cosine, log1p #other-page rows >= .90 / >= .95, nearest shares a key."""
    nn = S_OTHER.argmax(1)
    return np.c_[S_OTHER.max(1), np.log1p((S_OTHER >= 0.90).sum(1)), np.log1p((S_OTHER >= 0.95).sum(1)),
                 [float(bool(KEYS[i] & KEYS[nn[i]])) for i in range(len(ROWS))]]


COPYF = copy_feats()
NCL, CL = connected_components(csr_matrix(S_OTHER >= 0.95), directed=False)  # near-dup clusters (single linkage, other-page edges)
CL90 = connected_components(csr_matrix(S_OTHER >= 0.90), directed=False)[1]
_tn = {}
CLT = np.array([_tn.setdefault(' '.join(t.casefold().split()), len(_tn)) for t in TEXT])  # exact normalised text, no embedding
CLS = {'cos95': CL, 'cos90': CL90, 'txt': CLT}

# ---------------------------------------------------------------- E1: nested out-of-fold text score
def _fitpred(kind, a, b, y):
    if len(set(y[a])) < 2:
        return np.full(len(b), float(y[a].mean()))
    if kind == 'bge':
        return LogisticRegression(class_weight='balanced', C=1.0, max_iter=3000).fit(EMB[a], y[a]).predict_proba(EMB[b])[:, 1]
    Xa, Xb = H._tfidf([TEXT[i] for i in a], [TEXT[i] for i in b])  # harness TF-IDF (char_wb 2-5 + word 1-2), fit on train
    return LogisticRegression(class_weight='balanced', C=3.0, max_iter=3000).fit(Xa, y[a]).predict_proba(Xb)[:, 1]


def p_text(lab, kind):
    """P(false) per row. Hidden rows: model fit on ALL labelled rows. Labelled rows: inner 5-fold GroupKFold-by-page OOF,
    so the V9 LR never trains on an in-sample text score. Hidden pages never enter any text fit."""
    trn, hid = np.where(lab[PAGE])[0], np.where(~lab[PAGE])[0]
    y = (Y == 'false').astype(int); out = np.full(len(ROWS), np.nan)
    out[hid] = _fitpred(kind, trn, hid, y)
    for a, b in GroupKFold(5).split(trn, groups=PAGE[trn]):
        out[trn[b]] = _fitpred(kind, trn[a], trn[b], y)
    assert not np.isnan(out).any()
    return out


# ---------------------------------------------------------------- E3: v9.fact_feats with an observation filter
PRI = {'true': 0, 'false': 1, 'unsure': 2, '': 3}


def cands(i, f, role, dd):
    """Other-page observations of f.key; dd collapses copies to ONE observation (the representative row: labelled first,
    then earliest, then lowest index; all of that row's facts on the key are kept).
    cos95: group by near-dup cluster; cos95x: same, and the row's OWN cluster is dropped (copies of itself are not evidence);
    cos90x: same at cosine .90; txt / txtx: exact normalised text instead of the embedding (no-neural control);
    kv0: group by exact (date, value, op), i.e. same key-value on different pages within 0 days;
    kv30 (extra, KB-only control): same (value, op) chained within 30 days."""
    c = [(k, l) for k, l in OBS[f.key] if PAGE[k] != PAGE[i]]
    if dd is None or not c:
        return c
    cl = CLS.get(dd.rstrip('x'))
    if dd.endswith('x'):  # the row's own cluster on other pages = copies of itself, not evidence
        c = [(k, l) for k, l in c if cl[k] != cl[i]]
    g = {}
    if dd == 'kv30':  # same (value, op), chained while within 30 days of the group's first observation
        st = {}
        for k, l in sorted(c, key=lambda m: (ROWS[m[0]]['date'], m[0])):
            o = ROWS[k]['facts'][l]; v = (o.canon, o.op); d = ROWS[k]['date']
            if v not in st or d - st[v][0] > 30:
                st[v] = (d, len(g))
            g.setdefault(st[v][1], []).append((k, l))
    else:
        for k, l in c:
            o = ROWS[k]['facts'][l]
            g.setdefault(cl[k] if cl is not None else (ROWS[k]['date'], o.canon, o.op), []).append((k, l))
    out = []
    for v in g.values():
        rep = min({k for k, _ in v}, key=lambda k: (PRI[role[k]], ROWS[k]['date'], k))
        out += [(k, l) for k, l in v if k == rep]
    return out


def _marg(i, j, R, cand):
    """exp.fact_scores margin for PR (sym window, no reliability) over an explicit candidate list."""
    f = ROWS[i]['facts'][j]; D = ROWS[i]['date']; sp = sm = 0.0
    for k, l in cand:
        w, sg = R[k, l]
        if sg == 0 or w == 0:
            continue
        kw = kern(D - ROWS[k]['date'], PR)
        if kw == 0.0:
            continue
        c = Fact.consistent(f, ROWS[k]['facts'][l])
        if sg > 0:
            if c: sp += w * kw
            else: sm += w * kw
        elif c:
            sm += w * kw
    return (sp - sm) / (sp + sm) if sp + sm else 0.0


L1 = V9M.L1
ROWS_OF_PAGE = C.defaultdict(list)
for _i in range(len(ROWS)):
    ROWS_OF_PAGE[PAGE[_i]].append(_i)


def ff(lab, role=None, dd=None):
    """v9.fact_feats(lab, interval=True, role) with cands() as the observation source (dd=None reproduces it exactly)."""
    R = roles(lab, PR)
    role = np.where(lab[PAGE], Y, '') if role is None else np.where(lab[PAGE], Y, role)
    CAND = {(i, j): cands(i, ROWS[i]['facts'][j], role, dd) for i, j in FIDX}
    marg = {(i, j): _marg(i, j, R, CAND[i, j]) for i, j in FIDX}
    X = []
    for i, j in FIDX:
        r = ROWS[i]; f = r['facts'][j]; D = r['date']
        an, ng, vo = [], [], []
        for k, l in CAND[i, j]:
            o = ROWS[k]
            c = Fact.consistent(f, o['facts'][l]); d = o['date'] - D
            if role[k] in ('true', 'false', 'unsure'):
                if role[k] == 'true': an.append((d, c, o['facts'][l].canon))
                elif role[k] == 'false': ng.append((d, c, len(o['facts'])))
                else: vo.append((d, c, o['facts'][l].canon))
            else:
                vo.append((d, c, o['facts'][l].canon))
        prev = [a for a in an if a[0] < 0]; same = [a for a in an if a[0] == 0]; nxt = [a for a in an if a[0] > 0]

        def grp(g, pick):
            if not g: return -1, 0.0
            d0 = pick(a[0] for a in g); m = [a[1] for a in g if a[0] == d0]
            return float(sum(m) * 2 > len(m)), L1(d0)
        pm, pg = grp(prev, max); nm, ngap = grp(nxt, min)
        sm_ = float(any(a[1] for a in same)) if same else -1
        match = [abs(a[0]) for a in an if a[1]]; miss = [abs(a[0]) for a in an if not a[1]]
        negm = [abs(a[0]) for a in ng if a[1] and a[2] == 1]
        vs = [math.exp(-abs(a[0]) / 30) for a in vo if a[1]]; vd = [math.exp(-abs(a[0]) / 30) for a in vo if not a[1]]
        pg_other = [marg[k, q] for k in ROWS_OF_PAGE[PAGE[i]] if k != i for q in range(len(ROWS[k]['facts']))]
        X.append([pm, pg, nm, ngap, sm_, float(bool(match)), L1(min(match)) if match else 9, L1(min(miss)) if miss else 9,
                  len(an), float(len(negm)), L1(min(negm)) if negm else 9,
                  sum(vs), sum(vd), len(vs), len(vd), marg[i, j],
                  float(np.mean([m < 0 for m in pg_other])) if pg_other else 0.0, len(pg_other),
                  len(r['facts']), float(f.op != 'eq'), float(f.kind == 'date' and len(f.raw['value']) < 10),
                  V9M.KINDS.index(f.kind),
                  float(any(a[1] for a in prev)), float(any(a[1] for a in nxt)),
                  float(pm == 0 and any(a[1] for a in prev)), float(nm == 0 and any(a[1] for a in nxt)),
                  len(an), float(len(set((a[0] > 0, a[1]) for a in an)))] + V9M.bracket(an + vo)
                 + V9M.numeric(f, an if an else vo))
    return np.array(X, float)


# ---------------------------------------------------------------- models
_make = V9M.make


def make(model):
    if model == 'mlp':  # E5: nonlinear fusion over the same features
        return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64,), early_stopping=True, max_iter=500,
                                                             alpha=1e-3, random_state=0))
    if model == 'mlpreg':  # sensitivity: no early stopping (tiny R10 validation split), stronger L2
        return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64,), alpha=1e-1, max_iter=300, random_state=0))
    return _make(model)


V9M.make = make  # _v9_rest resolves make() from v9's globals at call time


def fit(lab, X0, model='lr', E=None, dd=None, st=False):
    """V9 (st=False) or V11 one self-training round (st=True, hi .95 lo .2, as v9.selftrain). E: per-row extras."""
    trf = lab[FPAGE] & (YF >= 0)
    add = (lambda X: X) if E is None else (lambda X: np.c_[X, E[FROW]])
    X = X0 if dd is None else ff(lab, dd=dd)
    out, conf = V9M._v9_rest(model, True, lab, add(X), trf, keep=True)
    if st:
        prow = V9M.LAST['prow']; role = np.full(len(ROWS), '', dtype=object)
        role[prow >= 0.95] = 'true'; role[prow <= 0.2] = 'false'
        out, conf = V9M._v9_rest(model, True, lab, add(ff(lab, role=role.astype(str), dd=dd)), trf, keep=True)
    return out, conf, V9M.LAST['prow'].copy(), V9M.LAST['prow_tr'].copy()


def arena_at(y, p, t):
    """harness three_class_metrics arena at one threshold: +1 right, -1 wrong, 0 abstain (max(p,1-p) < t) or unsure truth."""
    conf = np.maximum(p, 1 - p); guess = np.where(p >= 1 - p, 'true', 'false'); scored = y != 'unsure'
    return float((((conf >= t) & scored) * np.where(guess == y, 1, -1)).sum() / len(y))


TS = [round(0.5 + 0.05 * i, 2) for i in range(10)]


def split_metrics(lab, out, conf, prow, prow_tr):
    hid = ~lab[PAGE] & ~COPY; tr = lab[PAGE] & ~COPY
    m = {k: float(v) for k, v in metrics(Y[hid], out[hid], conf[hid]).items() if k != 'cm'}
    P = np.c_[prow[hid], 1 - prow[hid], np.zeros(hid.sum())]
    t3 = H.three_class_metrics(list(Y[hid]), P)
    t_tr = max(TS, key=lambda t: arena_at(Y[tr], prow_tr[tr], t))  # abstention threshold chosen on labelled rows
    assert abs(arena_at(Y[hid], prow[hid], t3['arena_best_t']) - t3['arena_best']) < 1e-9
    m.update({'p3_' + k: v for k, v in t3.items() if k != 'n'}, arena_train_t=t_tr,
             arena_at_train_t=arena_at(Y[hid], prow[hid], t_tr), n=int(hid.sum()))
    b = H.binary_metrics((Y[hid] == 'false').astype(int), 1 - prow[hid])  # threshold-free: does P(false) rank false rows?
    m.update(auc_false=b['auc'], ap_false=b['ap'])
    return m


def my_splits(regime):
    """exp.splits over the ORIGINAL pages (identical RNG draws), padded False for copy pages (as v12.splits_orig)."""
    pages = np.arange(NP_ORIG)
    if regime == 'R80':
        for tr, te in GroupKFold(5).split(pages, groups=pages):
            lab = np.zeros(NP, bool); lab[:NP_ORIG] = True; lab[te] = False; yield lab
    else:
        for seed in (range(10) if regime == 'R10' else range(10, 60)):
            rng = random.Random(seed); lab = np.zeros(NP, bool)
            lab[rng.sample(range(NP_ORIG), max(1, round(0.1 * NP_ORIG)))] = True; yield lab


# name -> (model, extras, dd, selftrain)
VARIANTS = {
    'V9': ('lr', None, None, False),
    'V9+pt_bge': ('lr', 'pt_bge', None, False),
    'V9+pt_tfidf': ('lr', 'pt_tfidf', None, False),
    'V9+copy': ('lr', 'copy', None, False),
    'V9+pt_bge+copy': ('lr', 'pt_bge+copy', None, False),
    'V9+dd_cos95': ('lr', None, 'cos95', False),
    'V9+dd_cos95x': ('lr', None, 'cos95x', False),
    'V9+dd_kv0': ('lr', None, 'kv0', False),
    'V9+dd_kv30': ('lr', None, 'kv30', False),
    'V9+dd_cos90x': ('lr', None, 'cos90x', False),
    'V9+dd_txt': ('lr', None, 'txt', False),
    'V9+dd_txtx': ('lr', None, 'txtx', False),
    'V11': ('lr', None, None, True),
    'V11+pt_bge': ('lr', 'pt_bge', None, True),
    'V11+copy': ('lr', 'copy', None, True),
    'V11+dd_cos95': ('lr', None, 'cos95', True),
    'V11+dd_cos95x': ('lr', None, 'cos95x', True),
    'V11+dd_kv0': ('lr', None, 'kv0', True),
    'V11+dd_kv30': ('lr', None, 'kv30', True),
    'V11+dd_cos90x': ('lr', None, 'cos90x', True),
    'V11+dd_txtx': ('lr', None, 'txtx', True),
    'MLP': ('mlp', None, None, False),
    'MLP+pt_bge': ('mlp', 'pt_bge', None, False),
    'MLPreg+pt_bge': ('mlpreg', 'pt_bge', None, False),
}
STRESS_SKIP = {'V9+pt_tfidf', 'MLP', 'MLP+pt_bge', 'MLPreg+pt_bge'}


def run_split(lab, names):
    t0 = time.time(); X0 = ff(lab); ex = {}
    need = {VARIANTS[n][1] for n in names}
    if any(e and 'pt_bge' in e for e in need): ex['pt_bge'] = p_text(lab, 'bge')
    if 'pt_tfidf' in need: ex['pt_tfidf'] = p_text(lab, 'tfidf')
    hid = ~lab[PAGE] & ~COPY; yf = (Y[hid] == 'false').astype(int)
    res = {'_text_auc': {k: H.binary_metrics(yf, v[hid])['auc'] for k, v in ex.items()}}
    ex['copy'] = COPYF
    if 'pt_bge' in ex: ex['pt_bge+copy'] = np.c_[ex['pt_bge'], COPYF]
    for n in names:
        model, e, dd, st = VARIANTS[n]
        res[n] = split_metrics(lab, *fit(lab, X0, model, ex.get(e), dd, st))
    res['_secs'] = time.time() - t0
    return res


def check():
    lab = next(my_splits('R10'))
    t0 = time.time(); a = V9M.fact_feats(lab); t1 = time.time(); b = ff(lab); t2 = time.time()
    assert np.array_equal(a, b), 'ff != v9.fact_feats'
    role = np.where(np.arange(len(ROWS)) % 3 == 0, 'true', np.where(np.arange(len(ROWS)) % 3 == 1, 'false', ''))
    assert np.array_equal(V9M.fact_feats(lab, role=role), ff(lab, role=role)), 'ff(role) != v9.fact_feats(role)'
    print(f'ff == v9.fact_feats (with and without pseudo roles); v9 {t1 - t0:.1f}s, ff {t2 - t1:.1f}s')
    for dd in ('cos95', 'cos95x', 'kv0'):
        d = ff(lab, dd=dd); print(dd, 'changed facts', int((np.abs(d - b) > 1e-12).any(1).sum()), 'of', len(FIDX))
    sz = np.bincount(CL); print('near-dup clusters: rows in clusters of size>=2:', int((sz[CL] >= 2).sum()), 'max size', sz.max(),
                                 'rows with other-page cos>=.95:', int((S_OTHER >= .95).any(1).sum()), '>=.90:', int((S_OTHER >= .90).any(1).sum()))
    pt = p_text(lab, 'bge'); print('p_text ok, range', pt.min().round(3), pt.max().round(3))


if __name__ == '__main__':
    if SCEN == 'check':
        check(); sys.exit()
    names = [n for n in VARIANTS if SCEN == 'base' or n not in STRESS_SKIP]
    out = {}
    if SCEN == 'base':
        for reg in (('R80', 'R10') if len(sys.argv) < 3 else (sys.argv[2],)):
            for n, lab in enumerate(my_splits(reg)):
                out[f'{reg}:{n}'] = run_split(lab, names)
                print(reg, n, f"{out[f'{reg}:{n}']['_secs']:.0f}s", {k: round(v['frec'], 3) for k, v in out[f'{reg}:{n}'].items() if not k.startswith('_')}, flush=True)
        json.dump(out, open(W + f"/cache/base{'' if len(sys.argv) < 3 else '_' + sys.argv[2]}.json", 'w'))
    else:
        assert COPY.any()
        lab = list(my_splits('R10'))[SEED]
        assert not lab[PAGE[COPY]].any()
        src = {r['id']: n for n, r in enumerate(ROWS) if not r.get('copy')}
        if SCEN != 'hpara':
            assert all(CL[n] == CL[src[r['id'].split('-', 1)[1]]] for n, r in enumerate(ROWS) if r.get('copy'))  # copies cluster with their source
        out[f'R10:{SEED}'] = run_split(lab, names)
        print(SCEN, SEED, f"{out[f'R10:{SEED}']['_secs']:.0f}s", flush=True)
        json.dump(out, open(W + f'/cache/{SCEN}_{SEED}.json', 'w'))
        if SCEN == 'hpara':
            cp = np.where(COPY)[0]; src = {r['id']: n for n, r in enumerate(ROWS) if not r.get('copy')}
            cs = np.array([S[n, src[ROWS[n]['id'].split('-', 1)[1]]] for n in cp])
            print(f'hpara copy-vs-source cosine: min {cs.min():.3f} median {np.median(cs):.3f}; share >= .95 {np.mean(cs >= .95):.3f}, >= .90 {np.mean(cs >= .90):.3f}', flush=True)
