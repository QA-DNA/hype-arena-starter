"""w11 measurement: S0 subject_match, S1-S4 subject_resolve, S5 form_full, ceilings, failure types.
Run: /tmp/veridyct-bench/.venv/bin/python -I /tmp/veridyct-emb/w11/measure.py [--no-log]"""
import json, re, sys, time, warnings
sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w7'); sys.path.insert(0, '/tmp/veridyct-emb/w11')
from collections import Counter, defaultdict
import numpy as np
import harness as H
H.set_threads(2)
import values as V
import subjects as S
from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

LOG = '--no-log' not in sys.argv
T0 = time.time()
rows, lex = H.load()
N = len(rows)
sf = H.single_fact_rows(rows)
SFI = [r['idx'] for r in sf]
SFSET = set(SFI)
X = S.Ctx(rows, lex)
C = len(X.CLASSES)
W = H.ResultWriter(H.results_path('w11'))
FLOOR = -3.0
f3 = lambda x: None if x is None else round(float(x), 3)


def log(task, variant, metrics, n, notes=''):
    if LOG:
        with warnings.catch_warnings():  # the lead fixed these task names; the harness only warns about unknown ones
            warnings.simplefilter('ignore')
            W.add('w11', 'rules+tfidf', task, variant, metrics, n=n, notes=notes)


def tick(msg): print(f'[{time.time() - T0:6.1f}s] {msg}', flush=True)


# ------------------------------------------------------------------ S0 subject_match
NAMED = np.array([X.gold[i] <= set(X.found[i]) for i in range(N)])  # gold subjects all matched in the row's own text
s0 = Counter()
for i, r in enumerate(rows):
    found, gs = set(X.found[i]), X.gold[i]
    s0['row_ok'] += gs <= found; s0['exact'] += found == gs; s0['extra'] += len(found - gs); s0['rows_extra'] += bool(found - gs)
    s0['facts'] += len(r['facts']); s0['fact_ok'] += sum(f['subject'] in found for f in r['facts'])
    s0['some'] += bool(found)
m_s0 = dict(rows=N, row_recall=f3(s0['row_ok'] / N), fact_recall=f3(s0['fact_ok'] / s0['facts']), exact_set_rows=f3(s0['exact'] / N),
            extra_subjects_per_row=f3(s0['extra'] / N), rows_with_extra_subject=f3(s0['rows_extra'] / N), rows_with_any_match=f3(s0['some'] / N),
            named_rows=int(NAMED.sum()), unnamed_rows=int((~NAMED).sum()))
print('S0 subject_match', m_s0)
log('subject_match', 'lexicon_longest_first_ci', m_s0, N, 'names+aliases, longest first, case-insensitive, no overlaps; row ok = every gold subject matched')

# ------------------------------------------------------------------ ceilings
page_found = {p: set().union(*[set(X.found[i]) for i in L]) for p, L in X.page.items()}
anywhere = np.array([X.gold[i] <= page_found[r['page']] for i, r in enumerate(rows)])
earlier = np.zeros(N, bool)  # gold covered by the row itself or any EARLIER row of the page (what carry can reach)
for p, L in X.page.items():
    seen = set()
    for i in L:
        seen |= set(X.found[i]); earlier[i] = X.gold[i] <= seen
first_unnamed = [not X.found[L[0]] for L in X.page.values()]
first_gold_unnamed = [not (X.gold[L[0]] <= set(X.found[L[0]])) for L in X.page.values()]
nopage_mention = [p for p, v in page_found.items() if not v]
ceil = dict(gold_on_page_any_row=f3(anywhere.mean()), gold_in_row_or_earlier=f3(earlier.mean()), gold_in_row=f3(NAMED.mean()),
            gold_nowhere_on_page=f3(1 - anywhere.mean()), n_nowhere=int((~anywhere).sum()),
            pages=len(X.page), pages_first_row_names_no_subject=f3(np.mean(first_unnamed)), pages_first_row_missing_gold=f3(np.mean(first_gold_unnamed)),
            pages_with_no_mention_at_all=f3(len(nopage_mention) / len(X.page)), rows_on_pages_with_no_mention=int(sum(len(X.page[p]) for p in nopage_mention)),
            sf_gold_on_page_any_row=f3(anywhere[SFI].mean()), sf_gold_in_row_or_earlier=f3(earlier[SFI].mean()))
print('ceilings', ceil)
log('subject_resolve', 'ceiling', ceil, N, 'share of rows whose gold subjects are all mentioned (lexicon matcher) in the row / the row or earlier rows / any row of the same page')


# ------------------------------------------------------------------ attribute classifier: unrestricted, calibrated, out of fold
def indicator(idxs):
    Y = np.zeros((len(idxs), C), bool)
    for k, i in enumerate(idxs):
        for f in rows[i]['facts']:
            Y[k, X.CI[f['attribute']]] = True
    return Y


def fit_D(tr, te):
    """TF-IDF char_wb(2,5)+word(1,2) -> one LinearSVC(C=3) per attribute (one-vs-rest, multi-label). Decision values over ALL
    attribute strings; an attribute with no training row gets FLOOR. Returns (D, available mask)."""
    Xtr, Xte = H._tfidf([rows[i]['text'] for i in tr], [rows[i]['text'] for i in te])
    Y = indicator(tr)
    D, avail = np.full((len(te), C), FLOOR), Y.any(0)
    for c in np.flatnonzero(avail):
        D[:, c] = LinearSVC(C=3).fit(Xtr, Y[:, c]).decision_function(Xte)
    return D, avail


def fit_platt(tr):
    """sigmoid(alpha * D + beta), fitted on inner 3-fold (by page) out-of-fold decision values of the TRAINING rows only."""
    xs, ys = [], []
    for a, b in GroupKFold(3).split(np.zeros(len(tr)), groups=[rows[i]['page'] for i in tr]):
        D, avail = fit_D(tr[a], tr[b])
        xs.append(D[:, avail].ravel()); ys.append(indicator(tr[b])[:, avail].ravel())
    lr = LogisticRegression(C=100, max_iter=300).fit(np.concatenate(xs)[:, None], np.concatenate(ys))
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


# w7's ranked value policy (copied from /tmp/veridyct-emb/w7/measure.py, unchanged logic)
LEXNAMES = set(lex['subjects']) | {a for d in lex['subjects'].values() for a in d['aliases']} | set(lex['events'])
SECONDARY = {'alt', 'weak', 'in_name'}; SECONDARY_RANK = {'alt', 'in_name'}
def primary(Cs): return [c for c in Cs if not SECONDARY & set(c['flags'])]
def attr_tokens(a): return [w[:5] for w in a.split('_') if len(w) >= 3 and w not in ('per', 'the', 'and', 'for')]
def distance_to_cue(text, c, a):
    best, low = 10 ** 6, text.lower()
    for tk in attr_tokens(a):
        for m in re.finditer(re.escape(tk), low):
            best = min(best, abs(m.start() - c['start']), abs(m.end() - c['end']))
    return best
def select(Cs, kind, prof, text, attr):
    cs = [c for c in Cs if c['kind'] == kind]
    if not cs: return None
    def key(c):
        v, fl = c['value'], set(c['flags'])
        sec = 1 if SECONDARY_RANK & fl else 0
        bad = 1 if fl & {'neg', 'approx', 'range'} and kind != 'boolean' else 0
        mism = 0
        if prof:
            if 'unit' in v and prof['units'] and v['unit'] not in prof['units']: mism += 1
            if kind == 'money' and prof['pers'] and (v.get('per') not in prof['pers']): mism += 1
            if kind == 'money' and not prof['pers'] and v.get('per'): mism += 1
            if kind == 'name' and prof['origins']:
                if ('lex' if c['rule'] == 'name_lexicon' else 'cap') != prof['origins'].most_common(1)[0][0]: mism += 1
        return (sec, bad, mism, distance_to_cue(text, c, attr), c['start'])
    return min(cs, key=key)
def profile(train_rows):
    kinds, units, pers, origins = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    for r in train_rows:
        f = r['facts'][0]; v = f['value']
        kinds[f['attribute']][v['kind']] += 1
        if 'unit' in v: units[f['attribute']][v['unit']] += 1
        if v['kind'] == 'money': pers[f['attribute']][v.get('per')] += 1
        if v['kind'] == 'name': origins[f['attribute']]['lex' if v['value'] in LEXNAMES else 'cap'] += 1
    return kinds, units, pers, origins


def make_prior(tr):
    a_s, sc = defaultdict(Counter), Counter()
    for i in tr:
        for f in rows[i]['facts']:
            a_s[X.CI[f['attribute']]][f['subject']] += 1; sc[f['subject']] += 1
    return dict(attr_subj=a_s, top_subject=sc.most_common(1)[0][0], profile=profile([rows[i] for i in tr if len(rows[i]['facts']) == 1]))


def build(regime):
    """Out-of-fold calibrated attribute probabilities. 'all': page_folds(rows), multi-label training on every training row.
    'sf': page_folds(single-fact rows), training and evaluation on single-fact rows only (w7's M3/M6 protocol)."""
    ev = list(range(N)) if regime == 'all' else SFI
    folds = H.page_folds(rows if regime == 'all' else sf)
    B = dict(P=np.zeros((N, C)), D=np.full((N, C), FLOOR), fold_of=np.full(N, -1), prior=[], ev=ev, alpha=[])
    for f, (trp, tep) in enumerate(folds):
        tr, te = np.array([ev[p] for p in trp]), np.array([ev[p] for p in tep])
        al, be = fit_platt(tr)
        D, _ = fit_D(tr, te)
        B['P'][te] = 1 / (1 + np.exp(-(al * D + be))); B['D'][te] = D; B['fold_of'][te] = f
        B['prior'].append(make_prior(tr)); B['alpha'].append((round(al, 3), round(be, 3)))
        tick(f'  {regime} fold {f}: train {len(tr)} test {len(te)} platt alpha={al:.2f} beta={be:.2f}')
    return B


# ------------------------------------------------------------------ resolvers
def base_pred(kind, i):
    found = X.found[i]
    if kind == 'match': return dict(set=frozenset(found) if found else None, s=found[0] if found else None, a=None, how='named' if found else 'none')
    if found: return dict(set=frozenset(found), s=found[0], a=None, how='named')
    L, k = X.page[rows[i]['page']], X.pos[i]
    for j in range(k - 1, -1, -1):
        if X.found[L[j]]:
            s = X.found[L[j]][-1] if kind == 'carry_recent' else X.found[L[j]][0]
            return dict(set=frozenset({s}), s=s, a=None, how='context')
    return dict(set=None, s=None, a=None, how='none')


CFG = {  # name -> cfg for subjects.resolve (rho: extra named subjects kept when their score >= rho * best)
    'S0c match_compat (w7 text_only)': dict(ctx=None, rho=None),
    'S2w nearest_row_compat (w7 page_carry)': dict(ctx='nearest_row', rho=None),
    'S2 carry_compatible': dict(ctx='carry', rho=0.5),
    'S2 page_any': dict(ctx='page', rho=0.5),
    'S3 page_dominant_fallback': dict(ctx='carry', rho=0.5, fallback=True),
    'S3p page_any+fallback': dict(ctx='page', rho=0.5, fallback=True),
    'S4 pronoun_typing (on S2)': dict(ctx='carry', rho=0.5, pron=True),
    'S4 pronoun_typing (on S3)': dict(ctx='carry', rho=0.5, fallback=True, pron=True),
    'S4p pronoun_typing (page_any+fallback)': dict(ctx='page', rho=0.5, fallback=True, pron=True),
    'X1 S3+competes': dict(ctx='carry', rho=0.5, fallback=True, competes=True),
    'X2 S3+competes+amb3': dict(ctx='carry', rho=0.5, fallback=True, competes=True, amb=3),
    'X3 S4p+competes+amb3': dict(ctx='page', rho=0.5, fallback=True, competes=True, amb=3, pron=True),
    'X4 S3+competes+collective': dict(ctx='carry', rho=0.5, fallback='collective', competes=True),
    'X5 page_any+competes+collective': dict(ctx='page', rho=0.5, fallback='collective', competes=True, mu=0.8),
    'X6 X4+pronoun_typing': dict(ctx='carry', rho=0.5, fallback='collective', competes=True, pron=True),
}


def run(name, B, idxs):
    if name in ('S0 match_only', 'S1 carry_recent', 'S1b carry_first'):
        kind = {'S0 match_only': 'match', 'S1 carry_recent': 'carry_recent', 'S1b carry_first': 'carry_first'}[name]
        return {i: base_pred(kind, i) for i in idxs}
    valid = B['fold_of'] >= 0
    return {i: S.resolve(X, i, B['P'][i], CFG[name], B['prior'][B['fold_of'][i]], B['P'], valid) for i in idxs}


def summarize(preds, idxs):
    """set accuracy by group (named = gold subjects all matched in the row's own text) + joint (subject, attribute) on single-fact rows."""
    ok = {i: preds[i]['set'] == X.gold[i] for i in idxs}
    g = lambda sel: float(np.mean([ok[i] for i in idxs if sel(i)])) if any(sel(i) for i in idxs) else float('nan')
    out = dict(named=g(lambda i: NAMED[i]), unnamed=g(lambda i: not NAMED[i]), all=g(lambda i: True),
               n_named=sum(NAMED[i] for i in idxs), n_unnamed=sum(not NAMED[i] for i in idxs), n=len(idxs))
    sfi = [i for i in idxs if i in SFSET]
    if sfi:
        gs = lambda sel: float(np.mean([ok[i] for i in sfi if sel(i)])) if any(sel(i) for i in sfi) else float('nan')
        out.update(sf_named=gs(lambda i: NAMED[i]), sf_unnamed=gs(lambda i: not NAMED[i]), sf_all=gs(lambda i: True),
                   sf_n_named=sum(NAMED[i] for i in sfi), sf_n_unnamed=sum(not NAMED[i] for i in sfi), sf_n=len(sfi))
        if preds[sfi[0]].get('a') is not None or any(preds[i].get('a') for i in sfi):
            gold = {i: rows[i]['facts'][0] for i in sfi}
            sub = np.array([preds[i]['s'] == gold[i]['subject'] for i in sfi]); att = np.array([preds[i]['a'] == gold[i]['attribute'] for i in sfi])
            out.update(sf_subject=float(sub.mean()), sf_attr=float(att.mean()), sf_joint=float((sub & att).mean()),
                       sf_attr_given_subject=float(att[sub].mean()) if sub.any() else float('nan'))
    return {k: (f3(v) if isinstance(v, float) else v) for k, v in out.items()}


ALL_IDX = list(range(N))
tick('building ALL regime (page_folds(rows), multi-label)')
BA = build('all')
tick('building SF regime (page_folds(sf), single-fact training)')
BS = build('sf')

order = ['S0 match_only', 'S1 carry_recent', 'S1b carry_first'] + list(CFG)
RES = {}
print('\nSUBJECT RESOLUTION, set accuracy (pred set == gold set).  ALL = every row (all-row folds); SF = single-fact subset of the same run')
print(f'{"variant":42s} {"named":>6s} {"unnamed":>7s} {"all":>6s} | {"sf_nam":>6s} {"sf_unn":>6s} {"sf_all":>6s} | {"joint":>6s} {"attr":>6s} {"a|s":>6s}')
for name in order:
    preds = run(name, BA, ALL_IDX)
    m = summarize(preds, ALL_IDX)
    RES[('all', name)] = (preds, m)
    j = lambda k: f'{m[k]:6.3f}' if m.get(k) is not None else '   n/a'
    print(f'{name:42s} {m["named"]:6.3f} {m["unnamed"]:7.3f} {m["all"]:6.3f} | {m["sf_named"]:6.3f} {m["sf_unnamed"]:6.3f} {m["sf_all"]:6.3f} | {j("sf_joint")} {j("sf_attr")} {j("sf_attr_given_subject")}')
    log('subject_resolve', name, m, N, 'ALL rows, page_folds(rows); classifier = TF-IDF char_wb(2,5)+word(1,2) LinearSVC(C=3) one-vs-rest multi-label, unrestricted, Platt-calibrated on inner OOF of training pages; set accuracy; named = gold subjects all matched in the row text')
print('\nSAME, SF regime (page_folds(sf), classifier trained on single-fact rows only; eval on 1,467 single-fact rows)')
for name in order:
    preds = run(name, BS, SFI)
    m = summarize(preds, SFI)
    RES[('sf', name)] = (preds, m)
    j = lambda k: f'{m[k]:6.3f}' if m.get(k) is not None else '   n/a'
    print(f'{name:42s} {m["named"]:6.3f} {m["unnamed"]:7.3f} {m["all"]:6.3f} | joint {j("sf_joint")} attr {j("sf_attr")} a|s {j("sf_attr_given_subject")}  n={m["n_named"]}/{m["n_unnamed"]}/{m["n"]}')
    log('subject_resolve', name + ' [sf_regime]', m, len(SFI), 'single-fact rows only, page_folds(sf), classifier trained on single-fact training rows only (w7 protocol)')

# ------------------------------------------------------------------ attribute sanity: gold-subject-restricted accuracy of the OOF classifier
for reg, B, idxs in (('sf', BS, SFI), ('all', BA, [i for i in SFI])):
    yt = np.array([rows[i]['facts'][0]['attribute'] for i in idxs], dtype=object)
    Dm = B['D'][idxs]
    un = np.array(X.CLASSES, dtype=object)[Dm.argmax(1)]
    rest = H._restricted_argmax(Dm, np.array(X.CLASSES, dtype=object), [rows[i] for i in idxs], lex)
    print(f'attribute accuracy on single-fact rows [{reg} regime]: unrestricted {np.mean(un == yt):.3f}, restricted to gold subject {np.mean(rest == yt):.3f}')
    log('subject_resolve', f'attribute_sanity[{reg}]', dict(acc_unrestricted=f3(np.mean(un == yt)), acc_gold_subject_restricted=f3(np.mean(rest == yt))), len(idxs))
tick('resolvers done')

# ------------------------------------------------------------------ rho / lam sensitivity (diagnostic: picked on the test folds, so optimistic)
print('\nsensitivity of S3 page_dominant_fallback (ALL regime, test-fold picked: diagnostic only)')
for key, vals in (('lam', [0.5, 0.65, 0.8, 0.9, 0.95]), ('rho', [0.25, 0.5, 0.75, None]), ('mu', [0.5, 0.8, 1.0])):
    for v in vals:
        cfg = dict(CFG['S3p page_any+fallback' if key == 'mu' else 'S3 page_dominant_fallback']); cfg[key] = v
        preds = {i: S.resolve(X, i, BA['P'][i], cfg, BA['prior'][BA['fold_of'][i]]) for i in ALL_IDX}
        m = summarize(preds, ALL_IDX)
        print(f'  {key}={v!s:5s} named {m["named"]:.3f} unnamed {m["unnamed"]:.3f} all {m["all"]:.3f} sf_joint {m["sf_joint"]:.3f}')
        log('subject_resolve', f'sensitivity {key}={v}', m, N, ('S3p page_any+fallback' if key == 'mu' else 'S3 page_dominant_fallback') + ' with one parameter changed; chosen on test folds, optimistic')

# ------------------------------------------------------------------ S5 form_full (single-fact rows, SF regime)
def form(preds, B, name_set=True):
    res, errs = Counter(), []
    for i in SFI:
        r, f = rows[i], rows[i]['facts'][0]
        p = preds[i]
        s, a = p['s'], p['a']
        kinds, units, pers, origins = B['prior'][B['fold_of'][i]]['profile']
        ok_s = p['set'] == X.gold[i] if name_set else s == f['subject']
        ok_a = a == f['attribute']
        ok_v = False
        if s is not None and a is not None:
            Cs = V.extract_values(r['text'], lex, exclude={s})
            kind = kinds[a].most_common(1)[0][0] if kinds.get(a) else None
            prof = dict(units=units.get(a, {}), pers={x for x in pers.get(a, {}) if x}, origins=origins.get(a, Counter())) if a in kinds else None
            sel = select(Cs, kind, prof, r['text'], a) if kind else None
            ok_v = sel is not None and H.value_equal(sel['value'], f['value'])
        res['n'] += 1; res['subject'] += ok_s; res['attr'] += ok_a; res['value'] += ok_v
        res['subject_attr'] += ok_s and ok_a; res['exact'] += ok_s and ok_a and ok_v
        res['attr_and_value'] += ok_a and ok_v; res['wrong_subject_attr_value_right'] += (not ok_s) and ok_a and ok_v
        res['s_ok_attr'] += ok_s and ok_a; res['s_ok'] += ok_s; res['s_ok_av'] += ok_s and ok_a and ok_v
        res['pred'] += s is not None
        if ok_s and ok_a and not ok_v: errs.append((r, p))
    n = res['n']
    out = {k: f3(v / n) for k, v in res.items() if k not in ('n', 's_ok_attr', 's_ok', 's_ok_av')}
    out.update(n=n, attr_given_subject_ok=f3(res['s_ok_attr'] / max(res['s_ok'], 1)), value_given_subject_attr_ok=f3(res['s_ok_av'] / max(res['s_ok_attr'], 1)),
               wrong_subject_but_attr_value_right_share=f3(res['wrong_subject_attr_value_right'] / n))
    return out


BEST = max([n for n in CFG if n[0] in 'SX' and not n.startswith(('S0c', 'S2w'))], key=lambda n: RES[('all', n)][1]['all'])
print('\nbest variant on ALL rows (set accuracy):', BEST, RES[('all', BEST)][1]['all'], '| on the SF regime:', RES[('sf', BEST)][1]['all'])
print('\nS5 FORM_FULL on 1,467 single-fact rows (SF regime): exact = subject set AND attribute AND typed value')
gold_pred = {i: dict(set=X.gold[i], s=rows[i]['facts'][0]['subject'], a=None) for i in SFI}
for i in SFI:  # reference: gold subject, attribute = restricted argmax of the same classifier
    cs = H.candidates(lex, gold_pred[i]['s'])
    P = BS['P'][i]; gold_pred[i]['a'] = max(cs, key=lambda a: P[X.CI[a]])
FORM = {}
for label, nset in (('S0c match_compat (w7 text_only)', False), ('S2w nearest_row_compat (w7 page_carry)', False), ('S2 carry_compatible', True),
                    ('S3 page_dominant_fallback', True), ('S4 pronoun_typing (on S3)', True), (BEST, True), ('reference', True)):
    preds = gold_pred if label == 'reference' else RES[('sf', label)][0]
    label = 'reference: gold subject given' if label == 'reference' else label
    m = form(preds, BS, nset)
    FORM[label] = m
    print(f'  {label:48s} subject {m["subject"]:.3f} attr {m["attr"]:.3f} value {m["value"]:.3f} subj+attr {m["subject_attr"]:.3f} EXACT {m["exact"]:.3f} | attr|subj_ok {m["attr_given_subject_ok"]:.3f} value|s,a_ok {m["value_given_subject_attr_ok"]:.3f} wrongS_rightAV {m["wrong_subject_but_attr_value_right_share"]:.3f}')
    log('form_full', label, m, len(SFI), 'single-fact rows, page_folds(sf); exact = subject set (w7 baselines: the joint-picked subject) AND attribute AND typed value via w7 extract_values + ranked policy (kind per attribute from training folds)')
# the same on the ALL-regime classifier (trained on every training row, multi-label), single-fact rows only
BAS = dict(BA); BAS['prior'] = BA['prior']
m = form({i: RES[('all', BEST)][0][i] for i in SFI}, BA, True)
print(f'  {BEST + " [ALL-regime classifier]":48s} subject {m["subject"]:.3f} attr {m["attr"]:.3f} value {m["value"]:.3f} subj+attr {m["subject_attr"]:.3f} EXACT {m["exact"]:.3f}')
log('form_full', BEST + ' [all_regime_classifier]', m, len(SFI), 'same, but resolver + attribute classifier from the all-row folds (multi-label training)')

json.dump(dict(best=BEST), open('/tmp/veridyct-emb/w11/best.json', 'w'))


# ------------------------------------------------------------------ pronoun cue diagnostics (S4)
cue = Counter()
for i in ALL_IDX:
    he, it = X.cues(i)
    gp = all(s in X.person for s in X.gold[i])
    gn = all(s not in X.person for s in X.gold[i])
    k = 'he_only' if he and not it else 'it_only' if it and not he else 'both' if he and it else 'none'
    cue[k] += 1; cue[k + '_gold_person'] += gp; cue[k + '_gold_nonperson'] += gn; cue[k + '_unnamed'] += (not NAMED[i])
print('\nS4 cue diagnostics:', dict(cue))
log('subject_resolve', 'pronoun_cue_diagnostics', dict(cue), N, 'rows by pronoun cue (he_only = he/she/his/her, it_only = it/its/the platform...), gold-subject typing and unnamed count')

# ------------------------------------------------------------------ failure types of the best variant (ALL regime)
def categorize(i, p):
    gs, found = X.gold[i], set(X.found[i])
    L, k = X.page[rows[i]['page']], X.pos[i]
    before = set().union(*[set(X.found[j]) for j in L[:k]]) if k else set()
    after = set().union(*[set(X.found[j]) for j in L[k + 1:]])
    if len(gs) > 1: return 'multi-subject row (set not recovered)'
    if gs <= found:
        return 'named, but an extra/other subject won' if p['set'] and p['set'] != gs else 'named, nothing predicted'
    if not (gs <= (before | after | found)): return 'gold subject never mentioned on the page'
    if found: return 'a different entity is named in the row (gold elsewhere on page)'
    if gs <= before: return 'unnamed, gold mentioned earlier but another subject picked'
    return 'unnamed, gold mentioned only in later rows'


pb, mb = RES[('all', BEST)]
fail = defaultdict(list)
for i in ALL_IDX:
    if pb[i]['set'] != X.gold[i]:
        fail[categorize(i, pb[i])].append(i)
nfail = sum(len(v) for v in fail.values())
print(f'\nfailure types of {BEST}: {nfail} wrong rows of {N}')
cat_counts = {}
for cat, L in sorted(fail.items(), key=lambda kv: -len(kv[1])):
    cat_counts[cat] = len(L)
    print(f'  {len(L):4d} ({len(L) / N:.3f} of rows) {cat}')
log('subject_resolve', 'failure_types[' + BEST + ']', cat_counts, N, 'wrong rows by type, ALL regime')
EX = []
rng = np.random.RandomState(0)
for cat, L in sorted(fail.items(), key=lambda kv: -len(kv[1])):
    pick = [L[j] for j in rng.choice(len(L), size=min(3, len(L)), replace=False)] if len(L) > 3 else L
    for i in pick[:3]:
        r = rows[i]
        print(f'   [{cat[:34]}] {r["id"]} gold={sorted(X.gold[i])} pred={sorted(pb[i]["set"]) if pb[i]["set"] else None} how={pb[i]["how"]} | {r["text"][:120]}')
tick('failure analysis done')
by_how = Counter()
for i in ALL_IDX:
    by_how[(pb[i]['how'], pb[i]['set'] == X.gold[i])] += 1
print('by decision path (how, correct): ', dict(by_how))
tick('all done')
