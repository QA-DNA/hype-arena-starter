"""V12: MMR-style 'count independent evidence, not rows' features on top of V9/V11 (imports v9.py, which imports exp.py).
Only the fact feature matrix changes; LR, stage 2, isotonic, self-training and threshold search are V11lr-self1's.
Run: python v12.py            # base + copy-lie + copy-control, full report on stdout (see README for runtime)
     python v12.py base|lie|control|mixed   # one scenario (sets KB_COPY before exp.py loads)
     python v12.py hlie|hctrl <seed>        # tell-free scenario, one R10 split
Stress scenarios append synthetic hidden copies to the rows (copies.py); see REPORT_v12.md."""
import os, sys, json, subprocess, time
SCEN = sys.argv[1] if len(sys.argv) > 1 else 'all'
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else None  # hlie / hctrl: the R10 seed whose hidden pages get copies
if SCEN in ('lie', 'control', 'mixed'):
    os.environ['KB_COPY'] = SCEN
elif SCEN in ('hlie', 'hctrl'):
    os.environ['KB_COPY'] = f'{SCEN}:{SEED}'
import v9 as V9M
from v9 import *  # noqa  (ROWS, PAGE, Y, OBS, NP, FIDX, CHOSEN, CHOSEN_C, fmt, metrics ...)
from sklearn.feature_extraction.text import TfidfVectorizer

COPY = np.array([bool(r.get('copy')) for r in ROWS])
NP_ORIG = int(PAGE[~COPY].max()) + 1
MODE = {'m': 'base'}
PSEUDO = []  # per self-training call: (# copies given pseudo 'true', # given pseudo 'false')
import exp as EXP
assert len(GAP) == len(ROWS) == len(EXP.PAGE) == len(PAGE) and len(FPAGE) == len(FIDX) == len(YF) == len(FROW)  # no stale globals
assert (YF[COPY[FROW]] == -1).all()  # copy facts never carry a training target
TFIDF = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5)).fit_transform([r['text'] for r in ROWS])  # label-free, L2-normalised
_GRAM = {}


def gram(key):
    """Pairwise similarity of the observations of a key: 1 for the same page, else TF-IDF cosine. Label-free."""
    if key not in _GRAM:
        ob = OBS[key]; rows = [k for k, _ in ob]
        G = (TFIDF[rows] @ TFIDF[rows].T).toarray()
        pg = PAGE[rows]; G[pg[:, None] == pg[None, :]] = 1.0
        _GRAM[key] = ({o: n for n, o in enumerate(ob)}, np.clip(G, 0.0, 1.0))
    return _GRAM[key]


def mmr_mass(items, G):
    """items: [(rel, pos)]; greedy in relevance order, weight = rel * (1 - max sim to already counted)."""
    items = sorted(items, key=lambda t: (-t[0], t[1])); tot = 0.0; done = []
    for rel, p in items:
        tot += rel * (1.0 - (max(G[p, q] for q in done) if done else 0.0)); done.append(p)
    raw = sum(t[0] for t in items)
    assert tot <= raw + 1e-9, (tot, raw)  # discounted mass never exceeds raw mass
    return tot


def extra_feats(lab, role, interval=True):
    """Per fact: [distinct pages x5] + [MMR masses x4], using V9M.fact_feats' anchor / negative / vote split."""
    cons = Fact.consistent if interval else Fact.same
    role = np.where(lab[PAGE], Y, role)
    out = []
    for i, j in FIDX:
        r = ROWS[i]; f = r['facts'][j]; D = r['date']; pos, G = gram(f.key)
        g = {n: [] for n in ('ac', 'ai', 'vc', 'vi', 'nc')}
        for k, l in OBS[f.key]:
            o = ROWS[k]
            if o['page'] == r['page']: continue
            c = cons(f, o['facts'][l]); rel = math.exp(-abs(o['date'] - D) / 30); e = (rel, pos[k, l], o['page'])
            if role[k] == 'true': g['ac' if c else 'ai'].append(e)
            elif role[k] == 'false':
                if c and len(o['facts']) == 1: g['nc'].append(e)  # same negative rule as v9 (single-fact false row)
            else: g['vc' if c else 'vi'].append(e)
        out.append([len({e[2] for e in g[n]}) for n in ('ac', 'ai', 'vc', 'vi', 'nc')]
                   + [mmr_mass([e[:2] for e in g[n]], G) for n in ('ac', 'ai', 'vc', 'vi')])
    return np.array(out, float)


_orig_feats = V9M.fact_feats


def feats12(lab, interval=True, role=None):
    X = _orig_feats(lab, interval, role)
    if role is not None and COPY.any(): PSEUDO.append((int((role[COPY] == 'true').sum()), int((role[COPY] == 'false').sum())))
    m = MODE['m']
    if m == 'base': return X
    E = extra_feats(lab, np.full(len(ROWS), '') if role is None else role, interval)
    if m == 'pages': return np.c_[X, E[:, :5]]
    if m == 'mmr': return np.c_[X, E[:, 5:]]
    if m == 'mmr-replace': return np.c_[np.delete(X, [11, 12, 13, 14], axis=1), E[:, 5:]]  # drop sum(vs) sum(vd) len(vs) len(vd)
    raise ValueError(m)


V9M.fact_feats = feats12  # v9.v9 / V9M.selftrain resolve fact_feats from v9's globals at call time

VAR = {
    'V9lr': ('base', lambda: V9M.v9('lr')),
    'V11lr-self1': ('base', lambda: V9M.selftrain('lr', 1)),
    'V12pages': ('pages', lambda: V9M.selftrain('lr', 1)),
    'V12mmr': ('mmr', lambda: V9M.selftrain('lr', 1)),
    'V12mmr-replace': ('mmr-replace', lambda: V9M.selftrain('lr', 1)),
}


def splits_orig(regime):
    """Same splits as exp.splits, over the ORIGINAL pages only (identical RNG draws)."""
    pages = np.arange(NP_ORIG)
    if regime == 'R80':
        for tr, te in GroupKFold(5).split(pages, groups=pages):
            lab = np.ones(NP_ORIG, bool); lab[te] = False; yield lab
    else:
        for seed in range(10):
            rng = random.Random(seed); lab = np.zeros(NP_ORIG, bool)
            lab[rng.sample(range(NP_ORIG), max(1, round(0.1 * NP_ORIG)))] = True; yield lab


def run12(name, regime):
    mode, build = VAR[name]; fn = build()
    ms, cms, pseudo = [], 0, []
    for n, lo in enumerate(splits_orig(regime)):
        if SEED is not None and n != SEED: continue  # hlie / hctrl: copies are built for one split only
        lab = np.zeros(NP, bool); lab[:NP_ORIG] = lo
        assert not lab[PAGE[COPY]].any() and (lab[:NP_ORIG] == lo).all() and not lab[NP_ORIG:].any()  # original split, padded False
        PSEUDO.clear()
        hid = ~lab[PAGE] & ~COPY  # evaluate original hidden rows only
        MODE['m'] = mode
        try: yp, conf = fn(lab)
        finally: MODE['m'] = 'base'
        m = metrics(Y[hid], yp[hid], conf[hid]); ms.append(m); cms = cms + m['cm']
        if PSEUDO: pseudo.append(PSEUDO[-1])  # last self-training call is the one whose roles feed the final fit
    if pseudo: print(f'   pseudo roles on copies, mean per split (of {int(COPY.sum())}): true={np.mean([p[0] for p in pseudo]):.1f} false={np.mean([p[1] for p in pseudo]):.1f}')
    avg = {k: float(np.mean([m[k] for m in ms])) for k in ms[0] if k != 'cm'}
    avg['cm'] = cms
    return avg, [{k: v for k, v in m.items() if k != 'cm'} for m in ms]


def scenario(names, regs):
    per = {}
    if SCEN != 'base':
        nf = int((Y[~COPY] == 'false').sum()); nsrc = int(COPY.sum()) // 3
        assert COPY.sum() == 3 * nsrc and (Y[COPY] == '').all()
        if SCEN in ('lie', 'control'): assert nsrc == nf
        if SCEN == 'mixed': assert nsrc == 2 * (nf // 2)
        what = {'lie': 'false rows', 'control': 'sampled true rows', 'mixed': 'rows (half false, half true)',
                'hlie': 'hidden false rows of this split', 'hctrl': 'sampled hidden true rows of this split'}[SCEN]
        tag = {'lie': 'TELL-CONFOUNDED', 'control': 'TELL-CONFOUNDED', 'mixed': 'post-hoc, still carries a tell',
               'hlie': 'tell-free', 'hctrl': 'tell-free'}[SCEN]
        if SCEN in ('hlie', 'hctrl'):  # sources must be hidden-page rows of exactly this split, labelled by class
            lab0 = list(splits_orig('R10'))[SEED]; byid = {r['id']: r for r in ROWS if not r.get('copy')}
            srcs = {r['id'].split('-', 1)[1] for r in ROWS if r.get('copy')}
            assert all(not lab0[byid[s]['page']] for s in srcs)  # no labelled row has a copy
            assert {byid[s]['label'] for s in srcs} == ({'false'} if SCEN == 'hlie' else {'true'})
            assert nsrc == sum(1 for r in byid.values() if r['label'] == 'false' and not lab0[r['page']])
        print(f'## scenario {SCEN}{"" if SEED is None else ":%d" % SEED} [{tag}]: {COPY.sum()} copies = 3 x {nsrc} {what}, {len(ROWS)} rows total', flush=True)
    for nm in names:
        for reg in regs:
            CHOSEN.clear(); CHOSEN_C.clear(); m, ps = run12(nm, reg); per[f'{nm}|{reg}'] = ps
            print(fmt(nm, reg, m), flush=True)
            print('   cm:', m['cm'].tolist(), 'chosen(t,band)', C.Counter(CHOSEN), C.Counter(CHOSEN_C), flush=True)
    return per


HDR = ('| variant | regime | acc | macroF1 | false-rec | false-prec | unsure-rec | non-unsure cov | ECE | Brier |\n'
       '|---|---|---|---|---|---|---|---|---|---|')
T_CUT = {10: 2.26, 5: 2.78}
MET = (('brier', 'Brier', -1), ('fprec', 'false-prec', 1), ('frec', 'false-rec', 1), ('acc', 'acc', 1))


def paired(a, b, label):
    """a, b: per-split metric dicts. Delta = b - a. wins = splits where b is better (Brier: lower)."""
    print(f'\n{label}')
    print('| metric | mean delta | sd of delta | se | wins/total | exceeds noise (abs(t) > t-cutoff 2.26 for n=10, 2.78 for n=5; many comparisons, uncorrected) |\n|---|---|---|---|---|---|')
    for k, nm, sgn in MET:
        d = np.array([y[k] - x[k] for x, y in zip(a, b)]); n = len(d)
        se = d.std(ddof=1) / math.sqrt(n); tc = T_CUT[n]
        print(f'| {nm} | {d.mean():+.4f} | {d.std(ddof=1):.4f} | {se:.4f} | {int((sgn * d > 0).sum())}/{n} | '
              f'{"yes" if abs(d.mean()) > tc * se else "no"} |')


VARS_H = ['V9lr', 'V11lr-self1', 'V12mmr', 'V12mmr-replace']
HEADER = """# results_v12.txt: V12 (independent-evidence features) vs V11lr-self1. Generated by `python v12.py`.
# Deviations from the pre-declared spec:
#  - MMR discounting is also applied to the ANCHOR pools (ac, ai), not only to votes (the spec listed four masses, two of them anchors; this is that, stated explicitly).
#  - V12mmr-replace removes sum(vs), sum(vd), len(vs), len(vd) and adds all four masses (two of them anchor masses); the raw anchor features stay.
# Scenario labels: lie, control = TELL-CONFOUNDED (every false / sampled-true row is copied, including rows on labelled pages, so in
#   training a duplicate means a class); mixed = post-hoc and still carries a tell (50% false among copied rows vs 8.6% elsewhere).
#   hlie, hctrl = TELL-FREE (copies only of rows on pages hidden in that R10 split) and are the headline stress test.
# Noise: paired t cutoffs 2.26 (n=10) and 2.78 (n=5); many comparisons are made, no multiplicity correction; 5 folds / 10 seeds share rows.
"""
SC = ('lie', 'control', 'mixed', 'hlie', 'hctrl')
SCL = {'base': 'clean', 'lie': 'lie (confounded)', 'control': 'control (confounded)', 'mixed': 'mixed (tell)', 'hlie': 'hlie (tell-free)', 'hctrl': 'hctrl (tell-free)'}

if __name__ == '__main__':
    if SCEN == 'base':
        print('JSON:' + json.dumps(scenario(list(VAR), ('R80', 'R10'))))
    elif SCEN in ('lie', 'control', 'mixed'):
        print('JSON:' + json.dumps(scenario(['V11lr-self1', 'V12mmr', 'V12mmr-replace'], ('R10',))))
    elif SCEN in ('hlie', 'hctrl'):
        print('JSON:' + json.dumps(scenario(VARS_H, ('R10',))))
    else:
        t0 = time.time(); out = {}
        def sub(*a):
            p = subprocess.run([sys.executable, __file__, *a], capture_output=True, text=True, check=True)
            ls = p.stdout.splitlines()
            return json.loads([l for l in ls if l.startswith('JSON:')][0][5:]), [l for l in ls if not l.startswith('JSON:')]
        print(HEADER + HDR)
        for s in ('base', 'lie', 'control', 'mixed'):
            out[s], body = sub(s); print('\n'.join(body), flush=True)
        for s in ('hlie', 'hctrl'):
            out[s] = {}
            for seed in range(10):
                r, body = sub(s, str(seed))
                print('\n'.join(body), flush=True)
                for k, ps in r.items(): out[s].setdefault(k, []).extend(ps)
        for reg in ('R80', 'R10'):
            for nm in ('V9lr', 'V12pages', 'V12mmr', 'V12mmr-replace'):
                paired(out['base']['V11lr-self1|' + reg], out['base'][nm + '|' + reg],
                       f'### Paired {nm} vs V11lr-self1, {reg} (delta = {nm} minus V11)')
        keys = ('acc', 'mf1', 'frec', 'fprec', 'urec', 'cov', 'ece', 'brier')
        mean = lambda ps, k: float(np.mean([p[k] for p in ps]))
        print('\n### Stress (R10, original hidden rows only): mean over 10 splits; in brackets the change vs the same variant on clean')
        print('| variant | scenario | acc | macroF1 | false-rec | false-prec | unsure-rec | cov | ECE | Brier |\n|---|---|---|---|---|---|---|---|---|---|')
        for nm in VARS_H:
            b = out['base'][nm + '|R10']
            for s in ('base',) + SC:
                if nm + '|R10' not in out[s]: continue
                ps = out[s][nm + '|R10']
                cell = lambda k: f'{mean(ps, k):.3f}' + ('' if s == 'base' else f' ({mean(ps, k) - mean(b, k):+.3f})')
                print(f'| {nm} | {SCL[s]} | ' + ' | '.join(cell(k) for k in keys) + ' |')
        print('\n### Degradation vs clean (R10, paired per split, original hidden rows; delta = scenario minus clean; k/n = splits where it got worse)')
        print('| variant | scenario | metric | mean | sd | k/n worse |\n|---|---|---|---|---|---|')
        dg = {}; MK = (('frec', 'false-rec', 1), ('fprec', 'false-prec', 1), ('brier', 'Brier', -1), ('acc', 'acc', 1))
        for s in SC:
            for nm in VARS_H:
                if nm + '|R10' not in out[s]: continue
                for k, mn, sgn in MK:
                    d = np.array([a[k] - b[k] for a, b in zip(out[s][nm + '|R10'], out['base'][nm + '|R10'])]); dg[nm, s, k] = d
                    print(f'| {nm} | {SCL[s]} | {mn} | {d.mean():+.4f} | {d.std(ddof=1):.4f} | {int((sgn * d < 0).sum())}/10 |')
        print('\n### Degradation of V9lr / V12 minus degradation of V11lr-self1 (paired per split; false-rec/false-prec/acc positive = degrades LESS than V11, Brier negative = degrades less; k/10 = splits where it degrades less; t = mean/se, cutoff 2.26)')
        print('| variant | scenario | metric | mean | sd | k/10 degrades less | t | beyond noise |\n|---|---|---|---|---|---|---|---|')
        for s in SC:
            for nm in ('V9lr', 'V12mmr', 'V12mmr-replace'):
                if (nm, s, 'frec') not in dg: continue
                for k, mn, sgn in MK:
                    d = dg[nm, s, k] - dg['V11lr-self1', s, k]; t = d.mean() / (d.std(ddof=1) / math.sqrt(10))
                    print(f'| {nm} | {SCL[s]} | {mn} | {d.mean():+.4f} | {d.std(ddof=1):.4f} | {int((sgn * d > 0).sum())}/10 | {t:+.2f} | {"yes" if abs(t) > 2.26 else "no"} |')
        print(f'\nwall-clock {time.time() - t0:.0f} s')
