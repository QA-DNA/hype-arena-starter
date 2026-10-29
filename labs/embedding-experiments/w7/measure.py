"""w7 measurement: M1 values_recall, M2 values_unit_recall, M3 form_e2e, M4 multi_fact, M5 subject_from_text.
Run: /tmp/veridyct-bench/.venv/bin/python -I /tmp/veridyct-emb/w7/measure.py [--no-log]"""
import json, re, sys, time
sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w7')
from collections import Counter, defaultdict
import numpy as np
from sklearn.svm import LinearSVC
import harness as H, values as V

H.set_threads(2)
LOG = '--no-log' not in sys.argv
rows, lex = H.load()
sf = H.single_fact_rows(rows)
W = H.ResultWriter(H.results_path('w7'))
NUMERIC = {'money', 'percent', 'date', 'duration', 'quantity', 'version'}
KINDS = ['quantity', 'money', 'duration', 'name', 'percent', 'boolean', 'date', 'version']
SECONDARY = {'alt', 'weak', 'in_name'}
SECONDARY_RANK = {'alt', 'in_name'}  # 'weak' only marks a boolean in a clause that also holds a number: a precision flag
LEXNAMES = set(lex['subjects']) | {a for d in lex['subjects'].values() for a in d['aliases']} | set(lex['events'])


def log(task, variant, metrics, n, notes=''):
    if LOG: W.add('w7', 'rules', task, variant, metrics, n=n, notes=notes)


def noop(v): return {k: x for k, x in v.items() if k != 'op'}
def primary(C): return [c for c in C if not SECONDARY & set(c['flags'])]
def eq(c, g, strict=True): return H.value_equal(c['value'], g) if strict else H.value_equal(noop(c['value']), noop(g))
def f3(x): return None if x is None else round(float(x), 3)


t0 = time.time()
COMMON_ALL = {m.group(0) for r in rows for m in re.finditer(r"\b[a-z][a-z']+\b", r['text'])}
CAND = {r['idx']: V.extract_values(r['text'], lex) for r in rows}
print(f'extracted {sum(map(len, CAND.values()))} candidates from {len(rows)} rows in {time.time() - t0:.2f}s')

# =============================================================== M1 values_recall
st = {k: Counter() for k in KINDS}
fails = defaultdict(list)
cand_by_kind, matched_by_kind, rule_tp, rule_fp = Counter(), Counter(), Counter(), Counter()
for r in rows:
    C = CAND[r['idx']]
    golds = [f['value'] for f in r['facts']]
    for f in r['facts']:
        g, k = f['value'], f['value']['kind']
        s = st[k]; s['n'] += 1
        s['strict'] += any(eq(c, g) for c in C)
        s['lenient'] += any(eq(c, g, False) for c in C)
        s['strict_primary'] += any(eq(c, g) for c in primary(C))
        s['lenient_primary'] += any(eq(c, g, False) for c in primary(C))
        if not any(eq(c, g, False) for c in C): fails[k].append((r, f))
    for c in C:
        hit = any(c['kind'] == g['kind'] and eq(c, g, False) for g in golds)
        cand_by_kind[c['kind']] += 1; matched_by_kind[c['kind']] += hit
        (rule_tp if hit else rule_fp)[(c['kind'], c['rule'])] += 1
m1 = {}
for k in KINDS:
    s = st[k]
    m1[k] = dict(n=s['n'], strict=f3(s['strict'] / s['n']), lenient=f3(s['lenient'] / s['n']), strict_primary=f3(s['strict_primary'] / s['n']),
                 lenient_primary=f3(s['lenient_primary'] / s['n']), cands=cand_by_kind[k], cand_precision=f3(matched_by_kind[k] / max(cand_by_kind[k], 1)))
N = sum(st[k]['n'] for k in KINDS)
tot = lambda key: sum(st[k][key] for k in KINDS) / N
ncand = sum(len(c) for c in CAND.values()); nprim = sum(len(primary(c)) for c in CAND.values())
m1_all = dict(n=N, strict=f3(tot('strict')), lenient=f3(tot('lenient')), strict_primary=f3(tot('strict_primary')),
              lenient_primary=f3(tot('lenient_primary')), cands_per_row=f3(ncand / len(rows)), primary_cands_per_row=f3(nprim / len(rows)),
              gold_per_row=f3(N / len(rows)), gold_per_cand=f3(N / ncand), gold_per_primary_cand=f3(N / nprim),
              cand_precision=f3(sum(matched_by_kind.values()) / ncand))
numeric_c = sum(len([c for c in primary(C) if c['kind'] in NUMERIC]) for C in CAND.values())
numeric_g = sum(1 for r in rows for f in r['facts'] if f['value']['kind'] in NUMERIC)
m1_all['numeric_primary_cands_per_gold'] = f3(numeric_c / numeric_g)
print('\nM1 values_recall (all 2,402 gold facts)')
print(f'{"kind":9s} {"n":>5s} {"strict":>7s} {"lenient":>8s} {"str_prim":>8s} {"len_prim":>8s} {"cands":>6s} {"cand_prec":>9s}')
for k in KINDS:
    d = m1[k]; print(f'{k:9s} {d["n"]:5d} {d["strict"]:7.3f} {d["lenient"]:8.3f} {d["strict_primary"]:8.3f} {d["lenient_primary"]:8.3f} {d["cands"]:6d} {d["cand_precision"]:9.3f}')
print('ALL', m1_all)
log('values_recall', 'all_candidates', dict(overall=m1_all, per_kind=m1), N,
    'strict keeps op, lenient ignores it; *_primary drops candidates flagged alt/weak/in_name; cand_precision = share of candidates equal to a gold value of the row')

flag_only = Counter()
for r in rows:
    for f in r['facts']:
        m_ = [c for c in CAND[r['idx']] if c['kind'] == f['value']['kind'] and eq(c, f['value'], False)]
        if m_ and all({'neg', 'approx', 'range'} & set(c['flags']) for c in m_): flag_only[f['value']['kind']] += 1
print('gold facts whose every matching candidate is flagged neg/approx/range (the contract reads those as nothing):', dict(flag_only))
log('values_recall', 'contract_flags', dict(flag_only) or {'flagged_gold_facts': 0}, N, 'gold facts whose only matching candidates are flagged neg/approx/range (booleans excluded by construction)')
print('\nremaining misses (lenient):', {k: len(v) for k, v in fails.items()})
for k, L in fails.items():
    for r, f in L[:6]:
        print(f'  {k} {r["id"]} gold={json.dumps(f["value"], ensure_ascii=False)} | {r["text"][:120]}')
print('\nTop false-positive rules (kind, rule): fp / tp')
for (k, rule), n in rule_fp.most_common(14):
    print(f'  {k:9s} {rule:22s} fp={n:5d} tp={rule_tp[(k, rule)]:5d}')

# subject-aware candidates (the fact's own subject is not a name candidate)
hit = tot_c = 0
nm_c = nm_hit = 0
for r in rows:
    for f in r['facts']:
        C = V.extract_values(r['text'], lex, exclude={f['subject']})
        hit += any(eq(c, f['value'], False) for c in C)
        if f['value']['kind'] == 'name':
            nm_c += 1; nm_hit += any(eq(c, f['value'], False) for c in C)
print(f'subject-aware (per fact exclude): overall lenient recall {hit / N:.3f}; name recall {nm_hit / nm_c:.3f}')
log('values_recall', 'subject_excluded', dict(lenient=f3(hit / N), name_lenient=f3(nm_hit / nm_c)), N, 'per fact, the fact subject is excluded from name candidates')

nv = Counter()
for r in rows:
    Cv = V.extract_values(r['text'], lex, common=COMMON_ALL)
    nv['cands'] += len([c for c in Cv if c['kind'] == 'name']); nv['primary'] += len([c for c in Cv if c['kind'] == 'name' and 'alt' not in c['flags']])
    for f in r['facts']:
        if f['value']['kind'] == 'name':
            nv['n'] += 1; nv['hit_all'] += any(eq(c, f['value']) for c in Cv); nv['hit_primary'] += any(eq(c, f['value']) for c in Cv if 'alt' not in c['flags'])
nm0 = Counter()
for r in rows:
    for f in r['facts']:
        if f['value']['kind'] == 'name': nm0['n'] += 1; nm0['hit_primary'] += any(eq(c, f['value']) for c in primary(CAND[r['idx']]))
print(f"names: primary recall without vocabulary {nm0['hit_primary'] / nm0['n']:.3f}; with lower-case vocabulary ({len(COMMON_ALL)} words) all {nv['hit_all'] / nv['n']:.3f}, primary {nv['hit_primary'] / nv['n']:.3f}, name candidates {nv['cands']} (primary {nv['primary']})")
log('values_recall', 'names_with_vocab', dict(primary_recall_no_vocab=f3(nm0['hit_primary'] / nm0['n']), primary_recall_vocab=f3(nv['hit_primary'] / nv['n']), all_recall_vocab=f3(nv['hit_all'] / nv['n']), name_cands=nv['cands'], name_primary_cands=nv['primary'], vocab_size=len(COMMON_ALL)), nv['n'], 'single sentence-initial capitalised word is a name only if its lower-case form is not seen in any text (label-free vocabulary)')

# =============================================================== M2 values_unit_recall
qa = Counter()
unit_fail = []
for r in rows:
    C = CAND[r['idx']]
    for f in r['facts']:
        g = f['value']
        if g['kind'] != 'quantity': continue
        qa['n'] += 1
        num_any = [c for c in C if c['value'].get('value') == g['value'] and c['kind'] in NUMERIC]
        num_q = [c for c in num_any if c['kind'] == 'quantity']
        qa['number_found_any_kind'] += bool(num_any)
        qa['number_found_as_quantity'] += bool(num_q)
        qa['unit_ok_any_cand'] += any(c['value'].get('unit') == g['unit'] for c in num_q)
        pq = [c for c in primary(C) if c['kind'] == 'quantity' and c['value'].get('value') == g['value']]
        qa['number_found_primary'] += bool(pq)
        qa['unit_ok_primary'] += any(c['value'].get('unit') == g['unit'] for c in pq)
        qa['unit_ok_first_primary_at_number'] += bool(pq) and pq[0]['value'].get('unit') == g['unit']
        if num_q and not any(c['value'].get('unit') == g['unit'] for c in num_q): unit_fail.append((r, f, num_q))
        if not num_any: qa['number_missing'] += 1
n = qa['n']
m2 = dict(n=n, number_found_any_kind=f3(qa['number_found_any_kind'] / n), number_found_as_quantity=f3(qa['number_found_as_quantity'] / n),
          unit_exact_given_number=f3(qa['unit_ok_any_cand'] / max(qa['number_found_as_quantity'], 1)),
          unit_exact_overall=f3(qa['unit_ok_any_cand'] / n),
          unit_wrong_or_missing_given_number=f3(1 - qa['unit_ok_any_cand'] / max(qa['number_found_as_quantity'], 1)),
          primary_number_found=f3(qa['number_found_primary'] / n), primary_unit_exact_overall=f3(qa['unit_ok_primary'] / n),
          primary_unit_exact_given_number=f3(qa['unit_ok_primary'] / max(qa['number_found_primary'], 1)),
          first_primary_unit_exact_given_number=f3(qa['unit_ok_first_primary_at_number'] / max(qa['number_found_primary'], 1)))
print('\nM2 values_unit_recall (quantity facts)', m2)
log('values_unit_recall', 'quantity', m2, n, 'any_cand = some quantity candidate at the same number carries the gold unit; primary = no alt-flagged candidates; first_primary = the first (the only unflagged) candidate at that number')
for r, f, nq in unit_fail[:8]:
    print('  unit mismatch', r['id'], f['value'], [c['value'].get('unit') for c in nq], '|', r['text'][:100])

# pure unit-from-text diagnostic: which word position holds the gold unit
pos = Counter()
for r in rows:
    for f in r['facts']:
        g = f['value']
        if g['kind'] != 'quantity': continue
        for c in CAND[r['idx']]:
            if c['kind'] == 'quantity' and c['value'].get('value') == g['value'] and c['value'].get('unit') == g['unit']:
                pos[c['rule'] + (':alt' if 'alt' in c['flags'] else '')] += 1
                break
print('  gold unit found by rule:', dict(pos))

# =============================================================== M3 form_e2e
folds = H.page_folds(sf)
y = np.array([r['facts'][0]['attribute'] for r in sf], dtype=object)
pred = np.empty(len(sf), dtype=object)
for tr, te in folds:
    Xtr, Xte = H._tfidf([sf[i]['text'] for i in tr], [sf[i]['text'] for i in te])
    m = LinearSVC(C=3).fit(Xtr, y[tr])
    pred[te] = H._restricted_argmax(m.decision_function(Xte), m.classes_, [sf[i] for i in te], lex)
am = H.attr_metrics(y, pred, H.train_counts(sf, folds))
print('\nM3 attribute baseline', {k: f3(v) for k, v in am.items()})
CAND_SF = [V.extract_values(r['text'], lex, exclude={r['facts'][0]['subject']}) for r in sf]
COMMON = {m.group(0) for r in rows for m in re.finditer(r"\b[a-z][a-z']+\b", r['text'])}  # label-free: lower-case words seen in any text
CAND_SF_V = [V.extract_values(r['text'], lex, exclude={r['facts'][0]['subject']}, common=COMMON) for r in sf]


def attr_tokens(a):
    return [w[:5] for w in a.split('_') if len(w) >= 3 and w not in ('per', 'the', 'and', 'for')]


def distance_to_cue(text, c, a):
    toks = attr_tokens(a)
    best = 10 ** 6
    low = text.lower()
    for tk in toks:
        for m in re.finditer(re.escape(tk), low):
            best = min(best, abs(m.start() - c['start']), abs(m.end() - c['end']))
    return best


def guess_kind(C):
    """Text-only fallback when the attribute's kind is unknown (attribute unseen in training): the kind of the first
    unflagged numeric candidate; else a mid-sentence capitalised name; else a boolean."""
    P = primary(C)
    for c in P:
        if c['kind'] in NUMERIC: return c['kind']
    if any(c['kind'] == 'name' and c['rule'] == 'name_cap' for c in P): return 'name'
    return 'boolean'


def select(C, kind, policy, prof, text='', attr=''):
    cs = [c for c in C if c['kind'] == kind]
    if policy == 'first_primary': cs = primary(cs)
    if not cs: return None
    if policy == 'ranked':
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
    return cs[0]


def profile(train_rows):
    kinds, units, pers, origins = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    for r in train_rows:
        f = r['facts'][0]; v = f['value']
        kinds[f['attribute']][v['kind']] += 1
        if 'unit' in v: units[f['attribute']][v['unit']] += 1
        if v['kind'] == 'money': pers[f['attribute']][v.get('per')] += 1
        if v['kind'] == 'name': origins[f['attribute']]['lex' if v['value'] in LEXNAMES else 'cap'] += 1
    return kinds, units, pers, origins


def run_e2e(policy, use_gold_attr, oracle_kind=False, fallback=False, cands=None):
    cands = cands or CAND_SF
    out = dict(exact=0, attr_only=0, value_only=0, gold_in_cands=0, picked_other_given_in=0, picked_other_wrong_kind=0,
               picked_other_same_kind=0, no_value=0)
    perkind = defaultdict(Counter)
    errs = []
    for tr, te in folds:
        kinds, units, pers, origins = profile([sf[i] for i in tr])
        for i in te:
            r, f = sf[i], sf[i]['facts'][0]
            a = f['attribute'] if use_gold_attr else pred[i]
            g = f['value']
            if oracle_kind: kind = g['kind']
            else: kind = kinds[a].most_common(1)[0][0] if kinds.get(a) else None
            if kind is None and fallback: kind = guess_kind(cands[i])
            prof = dict(units=units.get(a, {}), pers={p for p in pers.get(a, {}) if p}, origins=origins.get(a, Counter())) if a in kinds else None
            sel = select(cands[i], kind, policy, prof, r['text'], a) if kind else None
            val_ok = sel is not None and eq(sel, g)
            attr_ok = (a == f['attribute'])
            gold_in = any(eq(c, g) for c in cands[i])
            out['exact'] += attr_ok and val_ok; out['attr_only'] += attr_ok; out['value_only'] += val_ok
            out['gold_in_cands'] += gold_in
            out['no_value'] += sel is None
            if gold_in and not val_ok:
                out['picked_other_given_in'] += 1
                if kind != g['kind']: out['picked_other_wrong_kind'] += 1
                else: out['picked_other_same_kind'] += 1
                errs.append((r, f, a, sel))
            pk = perkind[g['kind']]; pk['n'] += 1; pk['exact'] += attr_ok and val_ok; pk['value'] += val_ok; pk['gold_in'] += gold_in
    n = len(sf)
    res = {k: f3(v / n) for k, v in out.items()}
    res['n'] = n
    res['picked_other_share_of_gold_in'] = f3(out['picked_other_given_in'] / max(out['gold_in_cands'], 1))
    res['per_kind'] = {k: dict(n=v['n'], exact=f3(v['exact'] / v['n']), value=f3(v['value'] / v['n']), gold_in_cands=f3(v['gold_in'] / v['n'])) for k, v in perkind.items()}
    return res, errs


E2E = {}
print('\nM3 form_e2e on', len(sf), 'single-fact rows (subject given = gold; attribute from TF-IDF+LinearSVC / gold)')
print(f'{"variant":34s} {"exact":>6s} {"attr":>6s} {"value":>6s} {"gold_in":>7s} {"other|in":>8s} {"none":>6s}')
for name, v in {'pred_attr/first_all': ('first_all', False, False), 'pred_attr/first_primary': ('first_primary', False, False),
                            'pred_attr/ranked': ('ranked', False, False), 'gold_attr/first_all': ('first_all', True, False),
                            'gold_attr/first_primary': ('first_primary', True, False), 'gold_attr/ranked': ('ranked', True, False),
                            'gold_attr_gold_kind/ranked': ('ranked', True, True), 'gold_attr_gold_kind/first_all': ('first_all', True, True),
                            'pred_attr/ranked+fallback': ('ranked', False, False, True), 'gold_attr/ranked+fallback': ('ranked', True, False, True),
                            'pred_attr/ranked+vocab': ('ranked', False, False, False, True), 'gold_attr/ranked+vocab+fallback': ('ranked', True, False, True, True)}.items():
    pol, ga, ok = v[0], v[1], v[2]
    res, errs = run_e2e(pol, ga, ok, fallback=len(v) > 3 and v[3], cands=CAND_SF_V if len(v) > 4 else None)
    E2E[name] = (res, errs)
    print(f'{name:34s} {res["exact"]:6.3f} {res["attr_only"]:6.3f} {res["value_only"]:6.3f} {res["gold_in_cands"]:7.3f} {res["picked_other_share_of_gold_in"]:8.3f} {res["no_value"]:6.3f}')
    log('values_form_e2e', name, {**{k: v for k, v in res.items()}, 'attr_acc_all': f3(am['acc_all'])}, len(sf),
        'TF-IDF char_wb(2,5)+word(1,2) LinearSVC C=3, gold-subject restricted, page_folds(sf); kind from training-fold attribute majority; policy ' + pol)
print('per-kind (pred_attr/ranked):')
for k, d in E2E['pred_attr/ranked'][0]['per_kind'].items(): print(f'   {k:9s} {d}')
print('per-kind (gold_attr/ranked):')
for k, d in E2E['gold_attr/ranked'][0]['per_kind'].items(): print(f'   {k:9s} {d}')
print('sample selection errors (gold_attr/ranked):')
for r, f, a, sel in E2E['gold_attr/ranked'][1][:12]:
    print(f'   {r["id"]} {f["attribute"]} gold={json.dumps(f["value"], ensure_ascii=False)} picked={json.dumps(sel["value"], ensure_ascii=False) if sel else None} | {r["text"][:110]}')

# =============================================================== M4 multi_fact
mf = [r for r in rows if len(r['facts']) > 1]
mc = Counter()
for r in mf:
    C, Cp = CAND[r['idx']], primary(CAND[r['idx']])
    ng = len(r['facts'])
    gn = [f for f in r['facts'] if f['value']['kind'] in NUMERIC]
    mc['rows'] += 1
    mc['count_eq_all'] += len(C) == ng
    mc['count_eq_primary'] += len(Cp) == ng
    pn = [c for c in Cp if c['kind'] in NUMERIC]
    mc['numeric_rows'] += len(gn) == len(r['facts'])
    mc['count_eq_numeric_primary_on_all_numeric_rows'] += (len(gn) == ng and len(pn) == len(gn))
    mc['count_eq_numeric_primary_any'] += len(pn) == len(gn)
    mc['facts'] += ng
    mc['fact_hit_all'] += sum(any(eq(c, f['value'], False) for c in C) for f in r['facts'])
    mc['fact_hit_primary'] += sum(any(eq(c, f['value'], False) for c in Cp) for f in r['facts'])
    mc['fact_hit_strict_all'] += sum(any(eq(c, f['value']) for c in C) for f in r['facts'])
    mc['row_all_facts_hit'] += all(any(eq(c, f['value'], False) for c in C) for f in r['facts'])
    mc['row_all_facts_hit_primary'] += all(any(eq(c, f['value'], False) for c in Cp) for f in r['facts'])
    # distinct gold values need distinct candidates (injective matching)
    used, ok = set(), True
    for f in r['facts']:
        j = next((j for j, c in enumerate(Cp) if j not in used and eq(c, f['value'], False)), None)
        if j is None: ok = False
        else: used.add(j)
    mc['row_injective_primary'] += ok
nr = mc['rows']
m4 = dict(rows=nr, facts=mc['facts'], count_equal_all_candidates=f3(mc['count_eq_all'] / nr), count_equal_primary_candidates=f3(mc['count_eq_primary'] / nr),
          numeric_only_rows=mc['numeric_rows'], count_equal_numeric_primary_over_numeric_only_rows=f3(mc['count_eq_numeric_primary_on_all_numeric_rows'] / max(mc['numeric_rows'], 1)),
          count_equal_numeric_primary_vs_numeric_gold=f3(mc['count_eq_numeric_primary_any'] / nr),
          fact_recall_all=f3(mc['fact_hit_all'] / mc['facts']), fact_recall_primary=f3(mc['fact_hit_primary'] / mc['facts']),
          fact_recall_strict_all=f3(mc['fact_hit_strict_all'] / mc['facts']), row_recall_all=f3(mc['row_all_facts_hit'] / nr),
          row_recall_primary=f3(mc['row_all_facts_hit_primary'] / nr), row_injective_primary=f3(mc['row_injective_primary'] / nr),
          mean_candidates=f3(np.mean([len(CAND[r['idx']]) for r in mf])), mean_primary_candidates=f3(np.mean([len(primary(CAND[r['idx']])) for r in mf])),
          mean_gold=f3(np.mean([len(r['facts']) for r in mf])))
print('\nM4 multi_fact', m4)
log('values_multi_fact', 'all_vs_primary', m4, nr, 'count_equal = number of candidates equals number of gold facts; numeric = money/percent/date/duration/quantity/version only; fact recall lenient (op ignored) unless strict')

# =============================================================== M5 subject_from_text
def subj_eval(strict_case):
    c = Counter(); reasons = defaultdict(list)
    for r in rows:
        ents = V.find_entities(r['text'], lex, strict_case=strict_case)
        found = {e[2] for e in ents}
        gs = {f['subject'] for f in r['facts']}
        c['rows'] += 1
        c['row_ok'] += gs <= found
        c['fact_ok'] += sum(f['subject'] in found for f in r['facts']); c['facts'] += len(r['facts'])
        c['extra_subjects'] += len(found - gs); c['rows_with_extra'] += bool(found - gs)
        c['rows_exact'] += found == gs
        c['rows_ok_with_exactly_gold_longest'] += gs <= found
        if not gs <= found:
            miss = sorted(gs - found)
            t = r['text']
            if not ents: why = 'no_entity_at_all'
            else: why = 'other_entity_only'
            if re.match(r'\s*(?:["“]?\s*)?(?:It|Its|He|She|They|This|That|These|His|Her|Their)\b', t) or re.search(r'\b(?:it|its|he|she|they|his|her|their|this)\b', t, re.I):
                why += '+pronoun'
            suffix = any(re.search(r'\b' + re.escape(w) + r'\b', t) for m in miss for w in re.split(r'\s+', m)[1:] if len(w) >= 3 and w not in ('Cloud',))
            if suffix: why += '+partial_name'
            if re.search(r'^[A-Z][a-z]+:', t): why += '+speaker_tag'
            if len(t.split()) <= 6: why += '+short_headline'
            reasons[why].append((r, miss))
    return c, reasons


for sc in (False, True):
    c, reasons = subj_eval(sc)
    m5 = dict(rows=c['rows'], row_recall=f3(c['row_ok'] / c['rows']), fact_recall=f3(c['fact_ok'] / c['facts']), exact_set_rows=f3(c['rows_exact'] / c['rows']),
              extra_subjects_per_row=f3(c['extra_subjects'] / c['rows']), rows_with_extra_subject=f3(c['rows_with_extra'] / c['rows']))
    print(f'\nM5 subject_from_text strict_case={sc}', m5)
    log('values_subject_from_text', 'case_insensitive' if not sc else 'capitalised_single_word_aliases_keep_capital', m5, c['rows'], 'longest-first lexicon name/alias matcher; a row is ok when every gold subject is matched')
    agg = Counter({k: len(v) for k, v in reasons.items()})
    print('  failure reasons:', dict(agg.most_common()))
    if not sc:
        for why, L in sorted(reasons.items(), key=lambda kv: -len(kv[1]))[:8]:
            for r, miss in L[:2]:
                print(f'   [{why}] {r["id"]} missing={miss} | {r["text"][:100]}')
# can the page (same date, consecutive ids) carry a missing subject? (case-insensitive matcher)
pg = defaultdict(list)
for r in rows: pg[r['page']].append(r)
cnt = Counter()
for r in rows:
    found = {e[2] for e in V.find_entities(r['text'], lex, strict_case=False)}
    gs = {f['subject'] for f in r['facts']}
    if gs <= found: continue
    cnt['failed_rows'] += 1
    page_found = set()
    prev_found = set()
    for o in pg[r['page']]:
        if o['idx'] == r['idx']: continue
        fo = {e[2] for e in V.find_entities(o['text'], lex, strict_case=False)}
        page_found |= fo
        if o['n'] < r['n']: prev_found = fo if o['n'] == max(x['n'] for x in pg[r['page']] if x['n'] < r['n']) else prev_found
    miss = gs - found
    cnt['missing_in_page'] += miss <= page_found
    cnt['missing_in_prev_row'] += miss <= prev_found
    cnt['gold_is_company_Hooly'] += miss == {'Hooly'}
    cnt['page_has_single_subject_found'] += len(page_found) == 1 and miss <= page_found
ms = Counter(m for r in rows for m in ({f['subject'] for f in r['facts']} - {e[2] for e in V.find_entities(r['text'], lex, strict_case=False)}))
print('\nM5 page-context upper bound on failed rows:', dict(cnt), 'top missing subjects:', ms.most_common(8))
log('values_subject_from_text', 'page_context_upper_bound', dict(cnt), cnt['failed_rows'], 'of the rows the matcher fails: gold subject(s) matched in another row of the same page / the previous row; top missing subjects in notes: ' + str(ms.most_common(6)))
print(f'\ndone in {time.time() - t0:.1f}s')

# =============================================================== M6 full form (subject, attribute, value) from the sentence alone
ENT = {r['idx']: V.find_entities(r['text'], lex, strict_case=False) for r in rows}


def subject_lists(carry):
    """Per row: subjects matched in the text, in order (deduplicated); with carry, a row with no match inherits the subjects of the
    most recent earlier row of the same page that had some."""
    out, last = {}, {}
    for r in rows:  # rows are sorted by id number
        S = list(dict.fromkeys(e[2] for e in ENT[r['idx']]))
        if S: last[r['page']] = S
        elif carry and r['page'] in last: S = last[r['page']]
        out[r['idx']] = S
    return out


def run_full(carry):
    SL = subject_lists(carry)
    res = Counter(); per_kind = defaultdict(Counter)
    for tr, te in folds:
        kinds, units, pers, origins = profile([sf[i] for i in tr])
        Xtr, Xte = H._tfidf([sf[i]['text'] for i in tr], [sf[i]['text'] for i in te])
        m = LinearSVC(C=3).fit(Xtr, y[tr]); D = m.decision_function(Xte); ci = {a: j for j, a in enumerate(m.classes_)}
        for ii, i in enumerate(te):
            r, f = sf[i], sf[i]['facts'][0]
            best, bs = None, -1e9
            for subj in SL[r['idx']]:
                for a in H.candidates(lex, subj):
                    if a in ci and D[ii, ci[a]] > bs: best, bs = (subj, a), D[ii, ci[a]]
            res['n'] += 1
            ok_s = ok_a = ok_v = False
            if best:
                subj, a = best
                ok_s, ok_a = subj == f['subject'], a == f['attribute']
                C = V.extract_values(r['text'], lex, exclude={subj})
                kind = kinds[a].most_common(1)[0][0] if kinds.get(a) else None
                prof = dict(units=units.get(a, {}), pers={p for p in pers.get(a, {}) if p}, origins=origins.get(a, Counter()))
                sel = select(C, kind, 'ranked', prof, r['text'], a) if kind else None
                ok_v = sel is not None and eq(sel, f['value'])
            res['subject'] += ok_s; res['attr'] += ok_a; res['value'] += ok_v; res['pred'] += bool(best)
            res['subject_attr'] += ok_s and ok_a; res['exact'] += ok_s and ok_a and ok_v
            res['subject_in_text'] += f['subject'] in SL[r['idx']]
            pk = per_kind[f['value']['kind']]; pk['n'] += 1; pk['exact'] += ok_s and ok_a and ok_v
    n = res['n']
    out = {k: f3(v / n) for k, v in res.items() if k != 'n'}
    out['n'] = n
    out['exact_given_subject_found'] = f3(res['exact'] / max(res['subject_in_text'], 1))
    out['per_kind_exact'] = {k: f3(v['exact'] / v['n']) for k, v in per_kind.items()}
    return out


print('\nM6 full form (subject from lexicon matcher, attribute from TF-IDF+SVC over the matched subjects, value ranked)')
for carry in (False, True):
    fm = run_full(carry)
    print('  page_carry' if carry else '  text_only ', fm)
    log('values_form_e2e', 'full_form_text_subject' + ('+page_carry' if carry else ''), fm, fm['n'],
        'single-fact rows, page_folds(sf); subject = lexicon matcher (case-insensitive longest), carry = a row without a match inherits the last matched subjects of its page; attribute = argmax SVC score over attributes of the matched subjects; value = ranked policy with the predicted attribute kind')
