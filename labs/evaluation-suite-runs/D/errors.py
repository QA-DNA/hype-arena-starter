"""Worker D, task 2: error classes of the CV-extracted forms (D/forms_cv.jsonl) vs gold, top classes with 2 examples.
Run: python -I errors.py [forms_cv.jsonl]  -> D/errors.txt"""
import json, os, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(1, '/tmp/veridyct-emb/common')
import harness as H
from run_cv import LEX0, named, vkey, norm


def short(fs): return '; '.join(f"{f['subject']}|{f['attribute']}|{json.dumps(norm(f['value']), sort_keys=True)}" for f in fs) or '(none)'


def page_ctx(rows):
    """per row id: subjects named on EARLIER rows of its page, and anywhere else on its page."""
    by = defaultdict(list)
    for r in rows: by[r['page']].append(r)
    early, anywhere = {}, {}
    for pg in by.values():
        nm = [named(r) for r in pg]
        for k, r in enumerate(pg):
            early[r['id']] = set().union(*nm[:k]) if k else set()
            anywhere[r['id']] = set().union(*(nm[:k] + nm[k + 1:]))
    return early, anywhere


def classify(r, P, early, anywhere):
    G = r['facts']; nm = named(r)
    gv = Counter((f['subject'], f['attribute'], vkey(f['value'])) for f in G)
    if gv == Counter((f['subject'], f['attribute'], vkey(f['value'])) for f in P): return None
    if len(G) > 1:
        miss = [f for f in G if f['subject'] not in nm]
        if len(P) < len(G):
            return 'multi: fewer facts extracted' + (' (a gold subject not named in row)' if miss else ' (all subjects named)')
        if len(P) > len(G): return 'multi: more facts extracted than gold'
        gp, pp = Counter((f['subject'], f['attribute']) for f in G), Counter((f['subject'], f['attribute']) for f in P)
        if gp != pp:
            return 'multi: right count, wrong subject' if {f['subject'] for f in G} != {f['subject'] for f in P} else 'multi: right count, wrong attribute'
        return 'multi: pairs right, a value wrong'
    g = G[0]
    if not P: return 'single: nothing extracted' + ('' if g['subject'] in nm else ' (subject not named in row)')
    hit = [p for p in P if (p['subject'], p['attribute'], vkey(p['value'])) == (g['subject'], g['attribute'], vkey(g['value']))]
    if hit: return 'single: gold fact found + extra assertion(s)'
    p = next((p for p in P if (p['subject'], p['attribute']) == (g['subject'], g['attribute'])), P[0])
    if p['subject'] != g['subject']:
        if g['subject'] in nm: return 'single: wrong subject, gold subject IS named in row'
        if g['subject'] in early[r['id']]: return 'single: wrong subject, gold subject named on an EARLIER row of the page'
        if g['subject'] in anywhere[r['id']]: return 'single: wrong subject, gold subject named only LATER on the page'
        return 'single: wrong subject, gold subject never named on the page'
    if p['attribute'] != g['attribute']:
        return 'single: right subject, wrong attribute' + (' (same value kind)' if p['value'].get('kind') == g['value']['kind'] else ' (other kind)')
    pv, gv_ = norm(p['value']), norm(g['value'])
    if pv.get('kind') != gv_.get('kind'): return 'single: right pair, wrong value kind'
    if {k: v for k, v in pv.items() if k != 'op'} == {k: v for k, v in gv_.items() if k != 'op'}: return 'single: right pair, op differs'
    if pv.get('value') == gv_.get('value'): return 'single: right pair, same number, unit/currency/per differs'
    return 'single: right pair, value differs'


def main(path):
    rows, _ = H.load()
    pred = {json.loads(l)['id']: json.loads(l)['assertions'] for l in open(path, encoding='utf-8')}
    early, anywhere = page_ctx(rows)
    cls = defaultdict(list)
    for r in rows:
        c = classify(r, pred[r['id']], early, anywhere)
        if c: cls[c].append(r)
    n_err = sum(len(v) for v in cls.values())
    lines = [f'{path}: {n_err} non-exact rows of {len(rows)}']
    for c, rs in sorted(cls.items(), key=lambda x: -len(x[1])):
        lines.append(f'\n== {len(rs):4d}  {c}')
        for r in rs[:2]:
            lines.append(f"   {r['id']} [{r['date']}] {r['text'][:220]}")
            lines.append(f"      gold: {short(r['facts'])}")
            lines.append(f"      pred: {short(pred[r['id']])}")
    # page-context ceiling for subject errors: gold subject in the earlier-row set of the page
    sf_err_subj = [r for c, rs in cls.items() if c.startswith('single: wrong subject') or 'not named in row' in c for r in rs]
    lines.append(f"\nsubject-type errors (single): {len(sf_err_subj)}; gold subject named on an earlier row of the page: "
                 f"{sum(r['facts'][0]['subject'] in early[r['id']] for r in sf_err_subj if len(r['facts']) == 1)}")
    open(f'{HERE}/errors.txt', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else f'{HERE}/forms_cv.jsonl')
