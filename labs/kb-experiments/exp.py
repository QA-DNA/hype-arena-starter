"""Truth-timeline experiments on VERIDYCT practice.csv (V0-V8, R80/R10 regimes).
Run: .venv/bin/python exp.py [variants...]
"""
import csv, json, math, random, sys, datetime as dt, collections as C
import numpy as np
from sklearn.metrics import f1_score, confusion_matrix
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

DATA = str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'data') + '/'
LABELS = ['true', 'false', 'unsure']
INF = float('inf')

LEX = json.load(open(DATA + 'lexicon.json'))
ALIAS = {}
for s in LEX['subjects']:
    for a in [s['name']] + s['aliases']:
        ALIAS[a.casefold()] = s['name']
for e in LEX['events']:
    ALIAS.setdefault((e if isinstance(e, str) else e['name']).casefold(), e if isinstance(e, str) else e['name'])

CONV = {'KB': ('data', 1e-3), 'MB': ('data', 1), 'GB': ('data', 1e3), 'TB': ('data', 1e6),
        'ms': ('time', 1e-3), 's': ('time', 1), 'min': ('time', 60), 'h': ('time', 3600),
        'day': ('time', 86400), 'week': ('time', 604800)}


def date_interval(s):
    p = s.split('-')
    if len(p) == 3:
        d = dt.date.fromisoformat(s).toordinal(); return d, d
    if len(p) == 2:
        y, m = int(p[0]), int(p[1])
        a = dt.date(y, m, 1); b = dt.date(y + (m == 12), m % 12 + 1, 1)
        return a.toordinal(), b.toordinal() - 1
    y = int(p[0]); return dt.date(y, 1, 1).toordinal(), dt.date(y, 12, 31).toordinal()


class Fact:
    __slots__ = ('key', 'kind', 'canon', 'lo', 'hi', 'op', 'raw')

    def __init__(self, f):
        v = f['value']; kind = v['kind']; op = v.get('op', 'eq'); x = v['value']
        dim = None
        if kind in ('quantity', 'duration'):
            unit = v.get('unit')
            if unit in CONV:
                dim, mult = CONV[unit]; x = x * mult
            else:
                dim = unit
        elif kind == 'money':
            dim = (v.get('currency'), v.get('per'))
        self.key = (f['subject'], f['attribute'], kind, dim)
        self.kind, self.op, self.raw = kind, op, v
        if kind in ('quantity', 'duration', 'money', 'percent'):
            x = float(x); self.canon = round(x, 6)
            d = 1e-6 * max(1.0, abs(x))
            self.lo, self.hi = {'eq': (x, x), 'lt': (-INF, x - d), 'le': (-INF, x), 'gt': (x + d, INF),
                                'ge': (x, INF)}[op]
        elif kind == 'date':
            self.canon = x; self.lo, self.hi = date_interval(x)
        elif kind == 'name':
            self.canon = ALIAS.get(str(x).casefold(), str(x).casefold()); self.lo = self.hi = None
        else:
            self.canon = str(x).casefold() if kind == 'version' else x; self.lo = self.hi = None

    def same(self, o):  # exact (V1-V4)
        return self.canon == o.canon

    def consistent(self, o):  # V5: interval overlap
        if self.lo is None:
            return self.canon == o.canon
        tol = 1e-9 * max(1.0, abs(self.lo) if self.lo != -INF else 1.0)
        return max(self.lo, o.lo) <= min(self.hi, o.hi) + tol


def load():
    rows = list(csv.DictReader(open(DATA + 'practice.csv')))
    rows.sort(key=lambda r: int(r['id'][2:]))
    out, page, prev = [], -1, None
    for r in rows:
        n = int(r['id'][2:])
        if prev is None or r['date'] != prev[1] or n != prev[0] + 1:
            page += 1
        prev = (n, r['date'])
        out.append(dict(id=r['id'], text=r['text'], date=dt.date.fromisoformat(r['date']).toordinal(),
                        datestr=r['date'], label=r['label'], page=page,
                        facts=[Fact(f) for f in json.loads(r['form'])]))
    return out


ROWS = load()
NP = max(r['page'] for r in ROWS) + 1
PAGE = np.array([r['page'] for r in ROWS])
Y = np.array([r['label'] for r in ROWS])
OBS = C.defaultdict(list)  # key -> [(row_idx, fact_idx)]
for i, r in enumerate(ROWS):
    for j, f in enumerate(r['facts']):
        OBS[f.key].append((i, j))


# ---------------------------------------------------------------- evidence model
def roles(lab_pages, p):
    """Per (row,fact): (weight, sign). sign +1 positive vote, -1 negative evidence, 0 ignored."""
    R = {}
    for i, r in enumerate(ROWS):
        n = len(r['facts'])
        for j in range(n):
            if lab_pages[r['page']]:
                if r['label'] == 'true':
                    R[i, j] = (1.0, 1)
                elif r['label'] == 'false':
                    if p.get('neg') and n == 1:
                        R[i, j] = (p['neg'], -1)
                    elif p.get('neg_multi') == 'weak':
                        R[i, j] = (p['neg'] / n, -1)
                    else:
                        R[i, j] = (0.0, 0)  # filled by blame pass if enabled
                else:
                    R[i, j] = (p['wu'], 1)
            else:
                R[i, j] = (p['wu'], 1)
    return R


def kern(dtd, p):
    """dtd = D - d_obs (days). Positive => obs before D."""
    tau = p['tau']
    if tau == INF:
        return 1.0
    if dtd >= 0:
        return math.exp(-dtd / tau)
    if p['win'] == 'fwd':
        return 0.0
    return p.get('beta', 1.0) * math.exp(dtd / tau)


def fact_scores(i, j, R, p, rel=None):
    """Weighted support / contradiction for fact j of row i, own page excluded."""
    r = ROWS[i]; f = r['facts'][j]; D = r['date']
    cons = Fact.consistent if p.get('interval') else Fact.same
    sp = sm = 0.0; nobs = 0; anch = []
    cand = [(k, l) for k, l in OBS[f.key] if ROWS[k]['page'] != r['page']]
    for k, l in cand:
        w, sg = R[k, l]
        if sg == 0 or w == 0:
            nobs += 1; continue
        nobs += 1
        if rel is not None and w < 1.0 and sg > 0:
            w = w * rel[ROWS[k]['page']]
        kw = kern(D - ROWS[k]['date'], p)
        if kw == 0.0:
            continue
        c = cons(f, ROWS[k]['facts'][l])
        if sg > 0:
            if c: sp += w * kw
            else: sm += w * kw
        elif c:  # known-false value consistent with ours => evidence against
            sm += w * kw
    if p['win'] == 'fwd' and sp + sm == 0 and cand:  # fallback: nothing before D, use later obs
        q = dict(p, win='sym'); return fact_scores(i, j, R, q, rel)
    return sp, sm, nobs


def latest_anchor(i, j, R, p):
    """V2: value in force = latest anchor at/before D (else earliest after)."""
    r = ROWS[i]; f = r['facts'][j]; D = r['date']
    cons = Fact.consistent if p.get('interval') else Fact.same
    an = [(ROWS[k]['date'], k, l) for k, l in OBS[f.key]
          if ROWS[k]['page'] != r['page'] and R[k, l] == (1.0, 1)]
    if not an:
        return 0.0, 0.0, 0
    before = [a for a in an if a[0] <= D]
    if before:
        d0 = max(a[0] for a in before); pick = [a for a in before if a[0] == d0]
    else:
        d0 = min(a[0] for a in an); pick = [a for a in an if a[0] == d0]
    sp = sum(1 for _, k, l in pick if cons(f, ROWS[k]['facts'][l]))
    if p.get('bracket') and before and sp * 2 <= len(pick):  # change-point: new value confirmed by next anchor after D
        after = [a for a in an if a[0] > D]
        if after:
            d1 = min(a[0] for a in after); nxt = [a for a in after if a[0] == d1]
            sn = sum(1 for _, k, l in nxt if cons(f, ROWS[k]['facts'][l]))
            if sn * 2 > len(nxt):
                return float(sn), float(len(nxt) - sn), len(an)
    return float(sp), float(len(pick) - sp), len(an)


def blame_pass(R, lab_pages, p):
    """V6: in labelled false multi-fact rows, blame the fact with the lowest margin (others -> weak anchors)."""
    for i, r in enumerate(ROWS):
        n = len(r['facts'])
        if not lab_pages[r['page']] or r['label'] != 'false' or n == 1:
            continue
        ms = []
        for j in range(n):
            sp, sm, _ = fact_scores(i, j, R, p)
            ms.append((sp - sm) / (sp + sm) if sp + sm else 0.0)
        jb = int(np.argmin(ms))
        for j in range(n):
            R[i, j] = (p['neg'], -1) if j == jb else (p.get('blame_pos', 0.0), 1 if p.get('blame_pos') else 0)
    return R


def reliability(R, lab_pages, p, iters=6):
    """V4: hidden-page reliability = smoothed share of its facts agreeing with current estimate."""
    rel = np.full(NP, 0.8)
    for _ in range(iters):
        agree = np.zeros(NP); tot = np.zeros(NP)
        for i, r in enumerate(ROWS):
            if lab_pages[r['page']]:
                continue
            for j in range(len(r['facts'])):
                sp, sm, _ = fact_scores(i, j, R, p, rel)
                if sp + sm > 0:
                    agree[r['page']] += sp / (sp + sm); tot[r['page']] += 1
        rel = (agree + 2 * 0.8) / (tot + 2)
    lab = np.array([lab_pages[q] for q in range(NP)])
    rel[lab] = 1.0
    return rel, agree, tot


def predict(lab_pages, p):
    """Returns per-row arrays: label, raw confidence, score (min margin), features."""
    R = roles(lab_pages, p)
    if p.get('blame'):
        R = blame_pass(R, lab_pages, p)
    rel = agree = tot = None
    if p.get('rel'):
        rel, agree, tot = reliability(R, lab_pages, p)
    lab, conf, score, feats = [], [], [], []
    for i, r in enumerate(ROWS):
        dec, ms, fe = [], [], []
        for j, f in enumerate(r['facts']):
            if p['mode'] == 'v2':
                sp, sm, nobs = latest_anchor(i, j, R, p)
            else:
                sp, sm, nobs = fact_scores(i, j, R, p, rel)
            m = (sp - sm) / (sp + sm) if sp + sm else 0.0
            if sp + sm == 0:
                dec.append('U')
            elif p['mode'] == 'v1':
                dec.append('F' if sm > 0 and sp == 0 else 'T')
            else:
                dec.append('F' if sm > sp else 'T')
            ms.append(m); fe.append((sp, sm, nobs, f.op != 'eq', f.kind == 'date' and len(f.raw['value']) < 10))
        mmin = min(ms)
        if 'F' in dec:
            L = 'false'
        elif 'U' in dec:
            L = 'unsure'
        else:
            L = 'true'
        lab.append(L); conf.append(0.5 + 0.5 * abs(mmin)); score.append(mmin)
        jw = int(np.argmin(ms)); sp, sm, nobs, hop, coarse = fe[jw]
        pr = 1.0
        if rel is not None and not lab_pages[r['page']]:  # leave-row-out reliability of own page
            a = agree[r['page']]; t = tot[r['page']]
            own = sum((x[0] / (x[0] + x[1])) for x in fe if x[0] + x[1] > 0)
            nown = sum(1 for x in fe if x[0] + x[1] > 0)
            pr = (a - own + 1.6) / (t - nown + 2)
        feats.append([len(r['facts']), mmin, sp, sm, nobs, sum(d == 'U' for d in dec), int(hop), int(coarse),
                      pr, sum(len(ROWS[k]['facts']) and 1 for k, _ in OBS[r['facts'][jw].key]),
                      len({ROWS[k]['facts'][l].canon for k, l in OBS[r['facts'][jw].key]})])
    return np.array(lab), np.array(conf), np.array(score), np.array(feats, float)


# ---------------------------------------------------------------- metrics
def metrics(y, yp, conf):
    acc = float(np.mean(y == yp))
    mf1 = f1_score(y, yp, labels=LABELS, average='macro', zero_division=0)
    cm = confusion_matrix(y, yp, labels=LABELS)
    fr = cm[1, 1] / max(1, cm[1].sum()); fp = cm[1, 1] / max(1, cm[:, 1].sum())
    ur = cm[2, 2] / max(1, cm[2].sum())
    nu = yp != 'unsure'
    c = conf[nu]; ok = (y[nu] == yp[nu]).astype(float)
    ece = 0.0
    if len(c):
        bins = np.minimum((c * 10).astype(int), 9)
        for b in range(10):
            m = bins == b
            if m.any():
                ece += m.mean() * abs(ok[m].mean() - c[m].mean())
    brier = float(np.mean((c - ok) ** 2)) if len(c) else float('nan')
    return dict(acc=acc, mf1=mf1, frec=fr, fprec=fp, urec=ur, ece=ece, brier=brier, cm=cm, cov=float(nu.mean()))


def splits(regime):
    pages = np.arange(NP)
    if regime == 'R80':
        for tr, te in GroupKFold(5).split(pages, groups=pages):
            lab = np.ones(NP, bool); lab[te] = False; yield lab
    else:
        for seed in range(10):
            rng = random.Random(seed); lab = np.zeros(NP, bool)
            lab[rng.sample(range(NP), max(1, round(0.1 * NP)))] = True; yield lab


def run(name, fn, regime):
    ms, cms = [], 0
    for lab in splits(regime):
        hid = ~lab[PAGE]
        yp, conf = fn(lab)
        m = metrics(Y[hid], yp[hid], conf[hid]); ms.append(m); cms = cms + m['cm']
    avg = {k: float(np.mean([m[k] for m in ms])) for k in ms[0] if k != 'cm'}
    avg['cm'] = cms
    return avg


# ---------------------------------------------------------------- variants
BASE = dict(mode='v3', wu=0.3, tau=30.0, win='sym', beta=0.5)  # a-priori: future evidence half weight


def rule(p):
    def fn(lab):
        L, conf, _, _ = predict(lab, p); return L, conf
    return fn


def v0(lab):
    tr = lab[PAGE]; rate = float(np.mean(Y[tr] == 'true'))
    return np.array(['true'] * len(ROWS)), np.full(len(ROWS), rate)


def pick_on_train(cands):
    """Choose params by LOPO macro-F1 on labelled rows (own page always excluded => leave-one-page-out)."""
    def fn(lab):
        tr = lab[PAGE]; best = None
        for p in cands:
            L, conf, _, _ = predict(lab, p)
            s = f1_score(Y[tr], L[tr], labels=LABELS, average='macro', zero_division=0)
            if best is None or s > best[0]:
                best = (s, L, conf, p)
        CHOSEN.append((best[3]['tau'], best[3]['win']))
        return best[1], best[2]
    return fn


CHOSEN = []


def calibrated(p, unsure_band=True):
    """V7: isotonic on LOPO train scores -> P(true); unsure band chosen on train macro-F1."""
    def fn(lab):
        L, _, s, F = predict(lab, p); tr = lab[PAGE]
        nokey = F[:, 5] > 0  # a fact without any evidence
        m = tr & np.isin(Y, ['true', 'false']) & ~nokey
        iso = IsotonicRegression(out_of_bounds='clip', y_min=0, y_max=1).fit(s[m], (Y[m] == 'true').astype(float))
        pt = iso.predict(s)
        best = None
        for th in (0.5, 0.6, 0.7, 0.8, 0.9):  # decision threshold on P(true), chosen on train
            for t in ([0.0, 0.05, 0.1] if unsure_band else [0.0]):
                for nk in ('unsure', 'true'):  # what to do with rows that have a fact without evidence
                    out = np.where(pt >= th, 'true', 'false'); out[np.abs(pt - th) < t] = 'unsure'
                    out[nokey & (out != 'false')] = nk
                    sc = f1_score(Y[tr], out[tr], labels=LABELS, average='macro', zero_division=0)
                    if best is None or sc > best[0]:
                        best = (sc, out, (th, t, nk))
        CHOSEN.append(best[2])
        out = best[1]
        return out, np.where(out == 'false', 1 - pt, pt)
    return fn


def fused(p, model='hgb'):
    """V8: per-row features -> classifier trained on labelled (LOPO) rows, isotonic-calibrated confidence."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.calibration import CalibratedClassifierCV

    def fn(lab):
        _, _, s, F = predict(lab, p); tr = lab[PAGE]
        X = np.c_[F, np.log1p(F[:, 2]), np.log1p(F[:, 3])]
        if model == 'hgb':
            base = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, min_samples_leaf=10)
        else:
            base = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
        ncls = min(C.Counter(Y[tr]).values())
        clf = CalibratedClassifierCV(base, method='isotonic', cv=min(3, ncls)) if ncls >= 2 else base
        clf.fit(X[tr], Y[tr])
        P = clf.predict_proba(X); cls = clf.classes_
        out = cls[P.argmax(1)]
        return out, P.max(1)
    return fn


def asof(p_wu=0.0):
    """Forward-time split: hide labels of last 20% of dates; value in force at 2026-10-28 from earlier data."""
    dates = sorted({r['date'] for r in ROWS}); cut = dates[int(0.8 * len(dates))]
    T = dt.date(2026, 10, 28).toordinal()
    res = {}
    for name, wu in [('anchors only', 0.0), ('anchors+votes(0.3)', 0.3)]:
        ok = n = cov = 0
        for key, obs in OBS.items():
            late = [(ROWS[k]['date'], k, l) for k, l in obs if ROWS[k]['date'] >= cut]
            if not late:
                continue
            d, k, l = max(late)
            if ROWS[k]['label'] != 'true':
                continue
            n += 1
            early = [(ROWS[a]['date'], a, b) for a, b in obs if ROWS[a]['date'] < cut]
            anc = [e for e in early if ROWS[e[1]]['label'] == 'true']
            pool = anc if wu == 0 else early
            if not pool:
                continue
            cov += 1
            # latest-dated observations win (anchors weight 1, others wu), majority value at the last date
            dmax = max(e[0] for e in pool)
            votes = C.Counter()
            for e in pool:
                if e[0] == dmax:
                    votes[ROWS[e[1]]['facts'][e[2]].canon] += 1.0 if ROWS[e[1]]['label'] == 'true' else wu
            ok += votes.most_common(1)[0][0] == ROWS[k]['facts'][l].canon
        res[name] = dict(keys=n, covered=cov, coverage=cov / max(1, n), precision=ok / max(1, cov))
    return res


def data_facts():
    print('rows', len(ROWS), C.Counter(Y), 'pages', NP, 'keys', len(OBS))
    pl = C.Counter(PAGE)
    print('page sizes: min %d median %d max %d' % (min(pl.values()), int(np.median(list(pl.values()))), max(pl.values())))
    fpp = C.Counter(int(sum(Y[PAGE == q] == 'false')) for q in range(NP))
    print('false rows per page histogram', sorted(fpp.items()))
    # distinct dates per page check
    print('keys with >1 distinct value', sum(len({ROWS[k]['facts'][l].canon for k, l in o}) > 1 for o in OBS.values()))
    print('keys observed on >1 page', sum(len({ROWS[k]['page'] for k, l in o}) > 1 for o in OBS.values()))
    fr = [i for i in range(len(ROWS)) if Y[i] == 'false']
    single = [i for i in fr if len(ROWS[i]['facts']) == 1]
    have = sum(any(ROWS[k]['page'] != ROWS[i]['page'] for k, _ in OBS[ROWS[i]['facts'][0].key]) for i in single)
    have_true = sum(any(ROWS[k]['page'] != ROWS[i]['page'] and Y[k] == 'true' for k, _ in OBS[ROWS[i]['facts'][0].key])
                    for i in single)
    print(f'false rows {len(fr)}, single-fact {len(single)}; key stated on another page {have}, on another-page TRUE row {have_true}')
    # explained by contradicting anchor (all labels known, V2 latest anchor rule, full labels)
    lab = np.ones(NP, bool)
    R = roles(lab, BASE)
    expl = 0; diffany = 0
    for i in fr:
        e = False; d = False
        for j in range(len(ROWS[i]['facts'])):
            sp, sm, _ = latest_anchor(i, j, R, BASE)
            e |= sm > sp
            f = ROWS[i]['facts'][j]
            d |= any(ROWS[k]['page'] != ROWS[i]['page'] and Y[k] == 'true' and not f.same(ROWS[k]['facts'][l])
                     for k, l in OBS[f.key])
        expl += e; diffany += d
    print(f'false rows with a contradicting latest anchor (V2 oracle, all labels): {expl}/{len(fr)};'
          f' with ANY differing true anchor: {diffany}/{len(fr)}')
    us = [i for i in range(len(ROWS)) if Y[i] == 'unsure']
    uk = sum(any(any(ROWS[k]['page'] != ROWS[i]['page'] for k, _ in OBS[f.key]) for f in ROWS[i]['facts']) for i in us)
    uk_all = sum(all(any(ROWS[k]['page'] != ROWS[i]['page'] for k, _ in OBS[f.key]) for f in ROWS[i]['facts']) for i in us)
    print(f'unsure rows {len(us)}: some fact key elsewhere {uk}, all fact keys elsewhere {uk_all}')
    tr = [i for i in range(len(ROWS)) if Y[i] == 'true']
    tk = sum(all(any(ROWS[k]['page'] != ROWS[i]['page'] for k, _ in OBS[f.key]) for f in ROWS[i]['facts']) for i in tr)
    print(f'true rows {len(tr)}: all keys stated elsewhere {tk}')


def fmt(name, reg, m):
    return (f"| {name} | {reg} | {m['acc']:.3f} | {m['mf1']:.3f} | {m['frec']:.3f} | {m['fprec']:.3f} | "
            f"{m['urec']:.3f} | {m['cov']:.3f} | {m['ece']:.3f} | {m['brier']:.3f} |")


V = {
    'V0': lambda: v0,
    'V1': lambda: rule(dict(BASE, mode='v1', tau=INF, win='sym', wu=0.3)),
    'V2': lambda: rule(dict(BASE, mode='v2')),
    'V2b': lambda: rule(dict(BASE, mode='v2', bracket=True)),
    'V2b+V5': lambda: rule(dict(BASE, mode='v2', bracket=True, interval=True)),
    'V3fwd': lambda: rule(dict(BASE, win='fwd')),  # fwd + fallback to later obs
    'V3sym': lambda: rule(dict(BASE, win='sym', beta=1.0)),
    'V3asym': lambda: rule(dict(BASE, win='sym', beta=0.5)),
    'V3sel': lambda: pick_on_train([dict(BASE, tau=t, win=w, beta=b) for t in (7.0, 30.0, 120.0)
                                    for w, b in (('fwd', 0.5), ('sym', 0.5), ('sym', 1.0))]),
    'V4': lambda: rule(dict(BASE, rel=True)),
    'V5': lambda: rule(dict(BASE, interval=True)),
    'V5+V4': lambda: rule(dict(BASE, interval=True, rel=True)),
    'V6neg': lambda: rule(dict(BASE, interval=True, neg=1.0)),
    'V6blame': lambda: rule(dict(BASE, interval=True, neg=1.0, blame=True)),
    'V6blame+pos': lambda: rule(dict(BASE, interval=True, neg=1.0, blame=True, blame_pos=0.5)),
    'V6weak': lambda: rule(dict(BASE, interval=True, neg=1.0, neg_multi='weak')),
    'V7': lambda: calibrated(dict(BASE, interval=True, neg=1.0)),
    'V8hgb': lambda: fused(dict(BASE, interval=True, neg=1.0, rel=True), 'hgb'),
    'V8lr': lambda: fused(dict(BASE, interval=True, neg=1.0, rel=True), 'lr'),
}

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or 'facts' in args:
        data_facts()
        print('as-of', asof())
        args = [a for a in args if a != 'facts']
    names = args or list(V)
    print('| variant | regime | acc | macroF1 | false-rec | false-prec | unsure-rec | non-unsure cov | ECE | Brier |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for nm in names:
        for reg in ('R80', 'R10'):
            CHOSEN.clear()
            m = run(nm, V[nm](), reg)
            print(fmt(nm, reg, m), flush=True)
            print('   cm(rows=true,false,unsure):', m['cm'].tolist(), ('chosen ' + str(C.Counter(CHOSEN))) if CHOSEN else '',
                  flush=True)
