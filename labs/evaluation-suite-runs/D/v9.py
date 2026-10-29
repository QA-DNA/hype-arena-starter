"""[Worker D copy of labs/kb-experiments/v9.py. Only change: decide() stores 'unsure' unclipped (the original wrote it
into a numpy '<U5' array, giving 'unsur' = always wrong); env FIXU=0 restores the original behaviour for reproduction.]
V9: fact-level bracket features (prev/next anchor match, gaps, negatives, votes, page suspicion)
-> classifier P(fact true) trained on labelled facts (inner GroupKFold OOF for threshold + isotonic),
row P(true) = product over facts.  Run: .venv/bin/python v9.py [hgb|lr]"""
import sys
from exp import *
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

KINDS = ['quantity', 'money', 'duration', 'name', 'percent', 'boolean', 'date', 'version']
FIDX = [(i, j) for i, r in enumerate(ROWS) for j in range(len(r['facts']))]
L1 = lambda x: math.log1p(abs(x))


def fact_feats(lab, interval=True, role=None):
    """role: optional per-row pseudo label for unlabelled rows ('true'/'false'), used only as evidence."""
    cons = Fact.consistent if interval else Fact.same
    pr = dict(BASE, interval=interval)
    R = roles(lab, pr)
    if role is None:
        role = np.where(lab[PAGE], Y, '')
    else:
        role = np.where(lab[PAGE], Y, role)
    marg = {}
    for i, j in FIDX:
        sp, sm, _ = fact_scores(i, j, R, pr); marg[i, j] = (sp - sm) / (sp + sm) if sp + sm else 0.0
    X = []
    for i, j in FIDX:
        r = ROWS[i]; f = r['facts'][j]; D = r['date']
        an, ng, vo = [], [], []
        for k, l in OBS[f.key]:
            o = ROWS[k]
            if o['page'] == r['page']:
                continue
            c = cons(f, o['facts'][l]); d = o['date'] - D
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
        own = [marg[i, q] for q in range(len(r['facts']))]
        pg_other = [marg[k, q] for k in np.where(PAGE == r['page'])[0] if k != i for q in range(len(ROWS[k]['facts']))]
        X.append([pm, pg, nm, ngap, sm_, float(bool(match)), L1(min(match)) if match else 9, L1(min(miss)) if miss else 9,
                  len({o for o in []}) or len(an), float(len(negm)), L1(min(negm)) if negm else 9,
                  sum(vs), sum(vd), len(vs), len(vd), marg[i, j],
                  float(np.mean([m < 0 for m in pg_other])) if pg_other else 0.0, len(pg_other),
                  len(r['facts']), float(f.op != 'eq'), float(f.kind == 'date' and len(f.raw['value']) < 10),
                  KINDS.index(f.kind),
                  float(any(a[1] for a in prev)), float(any(a[1] for a in nxt)),  # value ever true before / after D
                  float(pm == 0 and any(a[1] for a in prev)),  # stale: was true earlier, not at latest prev
                  float(nm == 0 and any(a[1] for a in nxt)),   # premature: true later, not at next
                  len({id(a) for a in an}), float(len(set((a[0] > 0, a[1]) for a in an)))] + bracket(an + vo)
                 + numeric(f, an if an else vo))
    return np.array(X, float)


def bracket(obs):
    """Bracket features over (dt, consistent) observations: nearest-before / same-day / nearest-after match."""
    prev = [a for a in obs if a[0] < 0]; same = [a for a in obs if a[0] == 0]; nxt = [a for a in obs if a[0] > 0]
    def grp(g, pick):
        if not g: return -1, 9.0
        d0 = pick(a[0] for a in g); m = [a[1] for a in g if a[0] == d0]
        return sum(m) / len(m), L1(d0)
    pm, pg = grp(prev, max); nm, ng = grp(nxt, min)
    sm = float(np.mean([a[1] for a in same])) if same else -1
    eb = float(any(a[1] for a in prev)); ea = float(any(a[1] for a in nxt))
    return [pm, pg, nm, ng, sm, eb, ea, float(pm == 0 and eb), float(nm == 0 and ea),
            float(np.mean([a[1] for a in obs])) if obs else -1, len(obs)]


def numeric(f, obs):
    """Magnitude/trend features vs nearest-before and nearest-after observed values (numeric kinds only)."""
    if not isinstance(f.canon, float) or f.op != 'eq':
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    v = f.canon
    def near(g, pick):
        if not g: return None
        d0 = pick(a[0] for a in g); vals = [a[2] for a in g if a[0] == d0 and isinstance(a[2], float)]
        return vals[0] if vals else None
    pv = near([a for a in obs if a[0] < 0], max); nv = near([a for a in obs if a[0] > 0], min)
    lr = lambda a: max(-10.0, min(10.0, math.log10((abs(v) + 1e-9) / (abs(a) + 1e-9)))) if a is not None else 0.0
    rp, rn = lr(pv), lr(nv)
    p10 = float(any(a is not None and a != v and abs(abs(x) - round(abs(x))) < 0.01 and round(abs(x)) >= 1
                    for a, x in ((pv, rp), (nv, rn))))
    btw = float(pv is not None and nv is not None and pv != nv and min(pv, nv) <= v <= max(pv, nv))
    return [rp, rn, abs(rp) + abs(rn), p10, btw, float(v == 0.0)]


def fact_targets():
    y = np.full(len(FIDX), -1)
    for n, (i, j) in enumerate(FIDX):
        if Y[i] == 'true': y[n] = 1
        elif Y[i] == 'false' and len(ROWS[i]['facts']) == 1: y[n] = 0
    return y


YF = fact_targets(); FROW = np.array([i for i, _ in FIDX]); FPAGE = PAGE[FROW]


def make(model):
    if model.startswith('lrC'):
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=float(model[3:])))
    if model == 'hgb':
        return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=8,
                                              categorical_features=[21])
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5))


def row_prob(pf):
    out = np.ones(len(ROWS))
    for n, i in enumerate(FROW): out[i] *= pf[n]
    return out


def decide(pt, t, band):
    out = np.where(pt >= t, 'true', 'false')
    if os.environ.get('FIXU', '1') == '1': out = out.astype('<U6')  # D fix: '<U5' clipped 'unsure' to 'unsur'
    out[np.abs(pt - t) < band] = 'unsure'; return out


STAGE2 = True
ONEHOT = False
GAPU = False


def row_gap():
    """Per row: max over facts of the distance (days) to the nearest other-page observation of the key."""
    g = np.zeros(len(ROWS))
    for i, r in enumerate(ROWS):
        for f in r['facts']:
            ds = [abs(ROWS[k]['date'] - r['date']) for k, _ in OBS[f.key] if ROWS[k]['page'] != r['page']]
            g[i] = max(g[i], min(ds) if ds else 1e9)
    return g


GAP = row_gap()  # label-free: uses only dates of observations, never labels


def page_susp(p1):
    """Leave-row-out mean/max of stage-1 P(false) over the other facts on the same page."""
    out = np.zeros((len(FIDX), 2))
    for n, (i, j) in enumerate(FIDX):
        o = (FPAGE == FPAGE[n]) & (FROW != i)
        out[n] = (float(np.mean(1 - p1[o])), float(np.max(1 - p1[o]))) if o.any() else (0.15, 0.15)
    return out


def pick_C(X, trf, g):
    """Inner GroupKFold log-loss on labelled facts only -> LR regularisation strength."""
    from sklearn.metrics import log_loss
    idx = np.where(trf)[0]; best = None
    for Cv in (0.01, 0.03, 0.1, 0.3, 1.0):
        oof = np.full(len(idx), YF[idx].mean())
        for a, b in GroupKFold(min(4, len(set(g)))).split(idx, groups=g):
            if len(set(YF[idx[a]])) < 2: continue
            oof[b] = make('lrC%g' % Cv).fit(X[idx[a]], YF[idx[a]]).predict_proba(X[idx[b]])[:, 1]
        ll = log_loss(YF[idx], np.clip(oof, 1e-4, 1 - 1e-4))
        if best is None or ll < best[0]: best = (ll, Cv)
    return 'lrC%g' % best[1]


def v9(model, calib=True):
    def fn(lab):
        chosen_model = model
        X = fact_feats(lab); trf = lab[FPAGE] & (YF >= 0)
        if model == 'lrcv':
            chosen_model = pick_C(X, trf, FPAGE[trf]); CHOSEN_C.append(chosen_model)
        return _v9_rest(chosen_model, calib, lab, X, trf)
    return fn


CHOSEN_C = []


def selftrain(model, rounds=1, hi=0.95, lo=0.2):
    """V11: V9 + self-training: confident hidden rows become pseudo anchors / negatives, features recomputed."""
    def fn(lab):
        X = fact_feats(lab); trf = lab[FPAGE] & (YF >= 0)
        out, conf = _v9_rest(model, True, lab, X, trf, keep=True)
        for _ in range(rounds):
            prow = LAST['prow']; role = np.full(len(ROWS), '', dtype=object)
            role[prow >= hi] = 'true'; role[prow <= lo] = 'false'
            X = fact_feats(lab, role=role.astype(str))
            out, conf = _v9_rest(model, True, lab, X, trf, keep=True)
        return out, conf
    return fn


LAST = {}


def _v9_rest(model, calib, lab, X, trf, keep=False):
    if True:
        if ONEHOT:  # one-hot bracket categories (coarse + fine) so a linear model gets the interactions
            cats = [catf(x) for x in X]; seen = sorted({c for n in np.where(trf)[0] for c in cats[n]}, key=str)
            X = np.c_[X, np.array([[float(c in cats[n]) for c in seen] for n in range(len(X))])]
        # inner OOF on labelled pages
        lp = np.where(lab)[0]; oof = np.full(len(FIDX), np.nan)
        g = FPAGE[trf]; k = min(4, len(set(g)))
        for a, b in GroupKFold(k).split(X[trf], YF[trf], g):
            idx = np.where(trf)[0]
            if len(set(YF[idx[a]])) < 2: continue
            m = make(model).fit(X[idx[a]], YF[idx[a]]); oof[idx[b]] = m.predict_proba(X[idx[b]])[:, 1]
        mfull = make(model).fit(X[trf], YF[trf]); pf = mfull.predict_proba(X)[:, 1]
        if STAGE2:
            p1 = np.where(np.isnan(oof), pf, oof)
            X = np.c_[X, page_susp(p1)]; oof[:] = np.nan
            for a, b in GroupKFold(k).split(X[trf], YF[trf], g):
                idx = np.where(trf)[0]
                if len(set(YF[idx[a]])) < 2: continue
                m = make(model).fit(X[idx[a]], YF[idx[a]]); oof[idx[b]] = m.predict_proba(X[idx[b]])[:, 1]
            mfull = make(model).fit(X[trf], YF[trf]); pf = mfull.predict_proba(X)[:, 1]
        # training rows: OOF fact probs where available (facts of labelled rows not in trf use full model)
        pf_tr = np.where(np.isnan(oof), pf, oof)
        prow_tr = row_prob(pf_tr); prow = row_prob(pf)
        tr = lab[PAGE]
        iso = None
        if calib:
            m = tr & np.isin(Y, ['true', 'false'])
            iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(prow_tr[m], (Y[m] == 'true').astype(float))
            prow_tr = iso.predict(prow_tr); prow = iso.predict(prow)
        best = None
        gaps = (INF,) if not GAPU else (60, 90, 120, 180, 365, INF)
        for t in (0.3, 0.4, 0.5, 0.6, 0.7):
            for band in (0.0, 0.05, 0.1):
                for G in gaps:
                    o = decide(prow_tr, t, band); o[(GAP > G) & (o == 'true')] = 'unsure'
                    sc = f1_score(Y[tr], o[tr], labels=LABELS, average='macro', zero_division=0)
                    if os.environ.get('SELPTS') == '1':  # D option: choose (t, band) on train arena points, not macro-F1
                        sc = float(np.mean(np.where(o[tr] == 'unsure', 0, np.where(o[tr] == Y[tr], 1, -1))))
                    if best is None or sc > best[0]: best = (sc, t, band, G)
        CHOSEN.append(best[1:])
        out = decide(prow, best[1], best[2]); out[(GAP > best[3]) & (out == 'true')] = 'unsure'
        if keep: LAST['prow'] = prow
        conf = np.where(out == 'true', prow, 1 - prow)
        return out, conf


def nostage2(model):
    def fn(lab):
        global STAGE2
        STAGE2 = False
        try: return v9(model)(lab)
        finally: STAGE2 = True
    return fn


def bkt(v):
    return 'none' if v < 0 else ('Y' if v > 0.5 else 'N')


def catf(x):
    """Bracket category of a fact: anchors if the key has any anchor, else all other-page observations."""
    if x[8] > 0:
        src, pm, nm, sm, st, pr = 'A', x[0], x[2], x[4], x[24], x[25]
    else:
        src, pm, nm, sm, st, pr = 'V', x[28], x[30], x[32], x[35], x[36]
    fine = (src, bkt(pm), bkt(nm), bkt(sm), int(st), int(pr), int(x[9] > 0))
    return fine, fine[:3]


def v10(alpha=2.0):
    """V10: smoothed P(fact true | bracket category) table with backoff; row P = product; threshold on train."""
    def fn(lab):
        X = fact_feats(lab); trf = lab[FPAGE] & (YF >= 0)
        cats = [catf(x) for x in X]
        g0 = YF[trf].mean(); cf = C.defaultdict(lambda: [0, 0]); cc = C.defaultdict(lambda: [0, 0])
        for n in np.where(trf)[0]:
            fi, co = cats[n]; cf[fi][0] += YF[n]; cf[fi][1] += 1; cc[co][0] += YF[n]; cc[co][1] += 1
        pf = np.zeros(len(FIDX)); pl = np.zeros(len(FIDX))
        for n, (fi, co) in enumerate(cats):
            own = (YF[n], 1) if trf[n] else (0, 0)
            for out, (y0, n0) in ((pf, (0, 0)), (pl, own)):  # pl = leave-own-fact-out estimate for train rows
                t, m = cc[co][0] - y0, cc[co][1] - n0; pc = (t + alpha * g0) / (m + alpha)
                t, m = cf[fi][0] - y0, cf[fi][1] - n0; out[n] = (t + alpha * pc) / (m + alpha)
        prow, prow_tr = row_prob(pf), row_prob(pl)
        tr = lab[PAGE]; m = tr & np.isin(Y, ['true', 'false'])
        iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(prow_tr[m], (Y[m] == 'true').astype(float))
        prow_tr, prow = iso.predict(prow_tr), iso.predict(prow)
        best = None
        for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
            for band in (0.0, 0.05, 0.1):
                sc = f1_score(Y[tr], decide(prow_tr[tr], t, band), labels=LABELS, average='macro', zero_division=0)
                if best is None or sc > best[0]: best = (sc, t, band)
        CHOSEN.append(best[1:])
        out = decide(prow, best[1], best[2])
        return out, np.where(out == 'true', prow, 1 - prow)
    return fn


V['V10table'] = lambda: v10()
V['V9lrcv'] = lambda: v9('lrcv')


def gapu(model):
    def fn(lab):
        global GAPU
        GAPU = True
        try: return v9(model)(lab)
        finally: GAPU = False
    return fn


V['V9lr+gapU'] = lambda: gapu('lr')
V['V11lr-self1'] = lambda: selftrain('lr', 1)
V['V11lr-self2'] = lambda: selftrain('lr', 2)
V['V11lr-self1-loose'] = lambda: selftrain('lr', 1, 0.9, 0.3)


def onehot(model, stage2=False):
    def fn(lab):
        global ONEHOT, STAGE2
        ONEHOT, STAGE2 = True, stage2
        try: return v9(model)(lab)
        finally: ONEHOT, STAGE2 = False, True
    return fn


V['V9lr+cat'] = lambda: onehot('lr'); V['V9lr+cat+s2'] = lambda: onehot('lr', True)
V['V9hgb-s1'] = lambda: nostage2('hgb'); V['V9lr-s1'] = lambda: nostage2('lr')
V['V9hgb'] = lambda: v9('hgb'); V['V9lr'] = lambda: v9('lr'); V['V9hgb-nocal'] = lambda: v9('hgb', False)

if __name__ == '__main__':
    names = sys.argv[1:] or ['V9hgb-s1', 'V9lr-s1', 'V9hgb', 'V9lr', 'V9hgb-nocal', 'V9lrcv', 'V9lr+cat+s2', 'V9lr+gapU', 'V10table', 'V11lr-self1', 'V11lr-self2']
    for nm in names:
        for reg in ('R80', 'R10'):
            CHOSEN.clear(); m = run(nm, V[nm](), reg)
            print(fmt(nm, reg, m), flush=True)
            print('   cm:', m['cm'].tolist(), 'chosen(t,band)', C.Counter(CHOSEN), C.Counter(CHOSEN_C), flush=True)
            CHOSEN_C.clear()
