"""w6 report: paired per-split deltas from cache/*.json -> markdown on stdout + /tmp/veridyct-emb/results/w6.jsonl.
Run after fusion.py base, fusion.py base R10x, fusion.py hlie|hctrl 0..9:   python -I report.py [--no-write]"""
import sys, json, math, glob
import numpy as np
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H

W = '/tmp/veridyct-emb/w6/cache/'
D = {}
for reg, f in (('R80', 'base.json'), ('R10', 'base.json'), ('R10x', 'base_R10x.json')):
    d = json.load(open(W + f)); D[reg] = [d[k] for k in sorted(d, key=lambda k: int(k.split(':')[1])) if k.startswith(reg + ':')]
for sc in ('hlie', 'hctrl', 'hpara'):
    D[sc] = [json.load(open(W + f'{sc}_{i}.json'))[f'R10:{i}'] for i in range(10)]
assert [len(D[r]) for r in ('R80', 'R10', 'R10x', 'hlie', 'hctrl', 'hpara')] == [5, 10, 50, 10, 10, 10]
SCN = {'hlie': 'R10 tell-free copied lies (3 verbatim copies of each hidden false row)',
       'hctrl': 'R10 tell-free control (3 verbatim copies of as many hidden true rows)',
       'hpara': 'R10 hlie with each copy reworded by a prefix (Reportedly, / According to one report, / Sources say that)'}
TC = {5: 2.776, 10: 2.262, 50: 2.010}  # two-sided 95% t cutoffs, df = n - 1; many comparisons, uncorrected
MET = [('acc', 1), ('frec', 1), ('fprec', 1), ('brier', -1), ('ece', -1), ('auc_false', 1)]
WRITE = '--no-write' not in sys.argv
RW = H.ResultWriter(H.results_path('w6'))


def model_of(v):
    if 'tfidf' in v: return 'tfidf'
    if any(t in v for t in ('bge', 'copy', 'cos95')): return 'bge-small-en-v1.5'
    return 'none'


def mean(reg, v, k): return float(np.mean([s[v][k] for s in D[reg]]))


def delta(reg, v, ref, k, reg_ref=None):
    a = np.array([s[v][k] for s in D[reg]]); b = np.array([s[ref][k] for s in D[reg_ref or reg]]); return a - b


def paired(reg, v, ref, reg_ref=None):
    out = {}
    for k, sg in MET:
        d = delta(reg, v, ref, k, reg_ref); n = len(d); se = d.std(ddof=1) / math.sqrt(n)
        out[k] = dict(mean=float(d.mean()), sd=float(d.std(ddof=1)), wins=int((sg * d > 0).sum()), n=n,
                      t=float(d.mean() / se) if se > 0 else 0.0, sig=bool(se > 0 and abs(d.mean()) > TC[n] * se))
    return out


def cell(p, k):
    x = p[k]; return f"{x['mean']:+.3f} ± {x['sd']:.3f}{'*' if x['sig'] else ''} ({x['wins']}/{x['n']})"


def table(title, pairs, regs, task, note=''):
    print(f'\n### {title}\nCell: mean paired delta (variant minus reference) ± sd over splits; * = |t| beyond the 95% cutoff '
          f'(2.78 n=5, 2.26 n=10, 2.01 n=50; uncorrected); (wins/n) = splits where the variant is better.{note}\n')
    print('| variant vs ref | regime | acc | false-rec | false-prec | Brier | ECE | AUC(false) | variant means acc / frec / fprec / Brier |')
    print('|---|---|---|---|---|---|---|---|---|')
    for v, ref in pairs:
        for reg in regs:
            if v not in D[reg][0] or ref not in D[reg][0]: continue
            p = paired(reg, v, ref)
            ms = {k: mean(reg, v, k) for k, _ in MET}
            print(f"| {v} vs {ref} | {reg} | " + ' | '.join(cell(p, k) for k, _ in MET) +
                  f" | {ms['acc']:.3f} / {ms['frec']:.3f} / {ms['fprec']:.3f} / {ms['brier']:.3f} |")
            if WRITE:
                RW.add('w6', model_of(v), task, f'{v} vs {ref} | {reg}',
                       {**{f'{k}_mean': ms[k] for k in ms}, **{f'{k}_ref_mean': mean(reg, ref, k) for k, _ in MET},
                        **{f'd_{k}_mean': p[k]['mean'] for k, _ in MET}, **{f'd_{k}_sd': p[k]['sd'] for k, _ in MET},
                        **{f'd_{k}_wins': p[k]['wins'] for k, _ in MET}, **{f'd_{k}_t': p[k]['t'] for k, _ in MET}},
                       n=len(D[reg]), notes=f'paired per split, delta = variant minus ref; regime {reg} ({SCN.get(reg, reg)}); '
                                            f'base model V9 = v9.py V9lr, V11 = V11lr-self1; exp.metrics (Brier/ECE on predicted-label confidence)')


def baseline():
    print('### Baseline reproduction (fusion.fit == v9.py V9lr / V11lr-self1, same splits; recorded in results_v9.txt)\n')
    print('| model | regime | acc | false-rec | false-prec | Brier | ECE | AUC(false) |\n|---|---|---|---|---|---|---|---|')
    for v in ('V9', 'V11'):
        for reg in ('R80', 'R10', 'R10x', 'hlie', 'hpara', 'hctrl'):
            print(f'| {v} | {reg} | ' + ' | '.join(f'{mean(reg, v, k):.3f}' for k, _ in MET) + ' |')
            if WRITE and reg in ('R80', 'R10'):
                RW.add('w6', 'none', 'fusion_text', f'{v} baseline | {reg}', {k: mean(reg, v, k) for k, _ in MET}, n=len(D[reg]),
                       notes='reproduction of results_v9.txt (V9lr R80 .902/.675/.763/.077, R10 .816/.465/.502/.122)')
    ta = {k: [s['_text_auc'][k] for s in D['R80']] for k in ('pt_bge', 'pt_tfidf')}
    tb = {k: [s['_text_auc'][k] for s in D['R10']] for k in ('pt_bge', 'pt_tfidf')}
    print('\nStand-alone text score, AUC false-vs-rest on hidden rows (mean over splits): '
          + ', '.join(f'{k} R80 {np.mean(ta[k]):.3f} R10 {np.mean(tb[k]):.3f}' for k in ta))
    if WRITE:
        for k in ta:
            RW.add('w6', 'bge-small-en-v1.5' if k == 'pt_bge' else 'tfidf', 'fusion_text', f'{k} stand-alone AUC',
                   dict(auc_R80=float(np.mean(ta[k])), auc_R10=float(np.mean(tb[k])), auc_R80_sd=float(np.std(ta[k], ddof=1)),
                        auc_R10_sd=float(np.std(tb[k], ddof=1))), n=15, notes='nested OOF p_text, hidden rows, false vs rest')


def stress(vs):
    print('\n### Copied-lie stress, R10 seeds 0..9, original hidden rows only. Cell: mean (paired delta vs the undefended base '
          'model in the same scenario, ± sd, wins/10); * = |t| > 2.26\n')
    print('| variant | false-rec clean | false-rec hlie | false-rec hpara (reworded) | false-rec hctrl | Brier hlie | Brier hpara | Brier hctrl |')
    print('|---|---|---|---|---|---|---|---|')
    for v in vs:
        ref = 'V11' if v.startswith('V11') else 'V9'
        def c(reg, k, sg):
            if v not in D[reg][0]: return 'n/a'
            m = mean(reg, v, k)
            if v == ref: return f'{m:.3f}'
            d = delta(reg, v, ref, k); se = d.std(ddof=1) / math.sqrt(len(d))
            return f"{m:.3f} ({d.mean():+.3f} ± {d.std(ddof=1):.3f}{'*' if se > 0 and abs(d.mean()) > TC[len(d)] * se else ''}, {int((sg * d > 0).sum())}/{len(d)})"
        print(f"| {v} | {c('R10', 'frec', 1)} | {c('hlie', 'frec', 1)} | {c('hpara', 'frec', 1)} | {c('hctrl', 'frec', 1)} | "
              f"{c('hlie', 'brier', -1)} | {c('hpara', 'brier', -1)} | {c('hctrl', 'brier', -1)} |")
        if WRITE:
            rec = {}
            for reg in ('R10', 'hlie', 'hpara', 'hctrl'):
                if v not in D[reg][0]: continue
                for k in ('frec', 'fprec', 'brier', 'acc', 'auc_false'):
                    rec[f'{k}_{reg}'] = mean(reg, v, k)
                    if reg != 'R10':
                        dg = delta(reg, v, v, k, 'R10'); rec[f'd_{k}_{reg}_minus_clean_mean'] = float(dg.mean()); rec[f'd_{k}_{reg}_minus_clean_sd'] = float(dg.std(ddof=1))
                    if v != ref:
                        d = delta(reg, v, ref, k); rec[f'd_{k}_{reg}_vs_{ref}_mean'] = float(d.mean()); rec[f'd_{k}_{reg}_vs_{ref}_sd'] = float(d.std(ddof=1))
            RW.add('w6', model_of(v), 'fusion_dedup' if 'dd_' in v else ('fusion_copy' if 'copy' in v else 'fusion_text'),
                   f'{v} stress (hlie/hpara/hctrl vs clean R10)', rec, n=10,
                   notes=f'R10 seeds 0..9, paired vs {ref} in the same scenario and vs itself clean; recorded V11 frec .461 clean -> .204 hlie; '
                         + '; '.join(f'{k}: {v_}' for k, v_ in SCN.items()))


def arena(vs, full):
    regs = ('R80', 'R10', 'R10x', 'hlie', 'hpara', 'hctrl')
    print('\n### E4 arena at the train-chosen abstention threshold (t in .50..95 picked on labelled rows; P(true) isotonic). '
          'Cell: mean (paired delta vs V9 ± sd); always-true bar in the last row\n')
    print('| variant | ' + ' | '.join(regs) + ' |\n|---|' + '---|' * len(regs))
    for v in vs:
        cells = []
        for reg in regs:
            if v not in D[reg][0]: cells.append('n/a'); continue
            m = mean(reg, v, 'arena_at_train_t')
            if v == 'V9': cells.append(f'{m:.3f}'); continue
            d = delta(reg, v, 'V9', 'arena_at_train_t'); se = d.std(ddof=1) / math.sqrt(len(d))
            cells.append(f"{m:.3f} ({d.mean():+.3f} ± {d.std(ddof=1):.3f}{'*' if se > 0 and abs(d.mean()) > TC[len(d)] * se else ''})")
        print(f'| {v} | ' + ' | '.join(cells) + ' |')
    print('| always-true | ' + ' | '.join(f"{mean(reg, 'V9', 'p3_arena_always_true'):.3f}" for reg in regs) + ' |')
    print('\n### E4 harness three_class_metrics (proba = [P(true), 1-P(true), 0]; acc/false-rec/false-prec at argmax, 3-class Brier)\n')
    print('| variant | regime | acc | false-rec | false-prec | 3-class Brier | arena t=.5 | arena oracle best t (median t) | arena train-chosen t | always-true |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for v in full:
        for reg in regs:
            if v not in D[reg][0]: continue
            g = lambda k: mean(reg, v, k); bt = [x[v]['p3_arena_best_t'] for x in D[reg]]
            print(f"| {v} | {reg} | {g('p3_acc'):.3f} | {g('p3_false_recall'):.3f} | {g('p3_false_precision'):.3f} | {g('p3_brier'):.3f} | "
                  f"{g('p3_arena_at_05'):.3f} | {g('p3_arena_best'):.3f} ({np.median(bt):.2f}) | {g('arena_at_train_t'):.3f} | {g('p3_arena_always_true'):.3f} |")
            if WRITE:
                d = delta(reg, v, 'V9', 'arena_at_train_t')
                RW.add('w6', model_of(v), 'fusion_arena', f'{v} | {reg}',
                       {k: g(k) for k in ('p3_acc', 'p3_false_recall', 'p3_false_precision', 'p3_brier', 'p3_ece', 'p3_arena_at_05',
                                          'p3_arena_best', 'arena_at_train_t', 'p3_arena_always_true')}
                       | dict(arena_best_t_median=float(np.median(bt)), d_arena_train_t_vs_V9_mean=float(d.mean()),
                              d_arena_train_t_vs_V9_sd=float(d.std(ddof=1))),
                       n=len(D[reg]), notes=f'{SCN.get(reg, reg)}; P(true) = isotonic-calibrated row prob; oracle best t chosen on the '
                                            'test rows (optimistic); train-chosen t from labelled rows (inner-OOF calibrated P)')


if __name__ == '__main__':
    baseline()
    regs = ('R80', 'R10', 'R10x', 'hlie', 'hpara', 'hctrl')
    table('E1 fusion_text: row text score p_text added to every fact of the row', [
        ('V9+pt_bge', 'V9'), ('V9+pt_tfidf', 'V9'), ('V9+pt_bge', 'V9+pt_tfidf'), ('V11+pt_bge', 'V11')], regs, 'fusion_text')
    table('E2 fusion_copy: embedding near-duplicate features', [
        ('V9+copy', 'V9'), ('V11+copy', 'V11'), ('V9+pt_bge+copy', 'V9')], regs, 'fusion_copy')
    table('E3 fusion_dedup: copies collapsed to one vote before the V9 features', [
        (f'{b}+dd_{d}', b) for b in ('V9', 'V11') for d in ('cos95', 'cos95x', 'cos90x', 'txt', 'txtx', 'kv0', 'kv30')]
        + [('V9+dd_cos95x', 'V9+dd_txtx'), ('V11+dd_cos95x', 'V11+dd_txtx')], regs, 'fusion_dedup')
    table('E5 nonlinear fusion: MLP(64) instead of the LR, same features', [
        ('MLP', 'V9'), ('MLP+pt_bge', 'V9+pt_bge'), ('MLPreg+pt_bge', 'V9+pt_bge')], ('R80', 'R10', 'R10x'), 'fusion_mlp',
        ' MLP = early stopping (spec); MLPreg = no early stopping, alpha 0.1 (sensitivity).')
    SV = [v for v in D['hlie'][0] if not v.startswith('_')]
    stress(SV)
    arena([v for v in D['R80'][0] if not v.startswith('_')], ['V9', 'V11', 'V9+dd_cos95x', 'V9+dd_txtx'])
