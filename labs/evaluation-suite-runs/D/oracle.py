"""Worker D: end-to-end value of each error class. Build forms where the rows of one error class get their GOLD form
(everything else stays CV-extracted), then run e2e.py on it. An upper bound on what fixing that class buys.
Run: python -I oracle.py  (writes forms_oracle_<tag>.jsonl, runs e2e.py for each, FIXU=1 and 0)"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(1, '/tmp/veridyct-emb/common')
import harness as H, errors as ER

rows, _ = H.load()
pred = {json.loads(l)['id']: json.loads(l) for l in open(f'{HERE}/forms_cv.jsonl', encoding='utf-8')}
early, anywhere = ER.page_ctx(rows)
cls = {r['id']: ER.classify(r, pred[r['id']]['assertions'], early, anywhere) for r in rows}
GROUPS = {
    'fix_multi_generic': lambda c: c == 'multi: fewer facts extracted (all subjects named)',
    'fix_page_named_subject': lambda c: c in ('single: wrong subject, gold subject named on an EARLIER row of the page',
                                              'single: wrong subject, gold subject named only LATER on the page',
                                              'single: nothing extracted (subject not named in row)',
                                              'multi: fewer facts extracted (a gold subject not named in row)'),
    'fix_page_topic_never_named': lambda c: c == 'single: wrong subject, gold subject never named on the page',
    'fix_small_generic': lambda c: c is not None and (c.startswith('single: right') or c in (
        'single: gold fact found + extra assertion(s)', 'single: wrong subject, gold subject IS named in row',
        'single: nothing extracted', 'multi: more facts extracted than gold') or c.startswith('multi: right count') or c.startswith('multi: pairs')),
}
GROUPS['fix_subject_all'] = lambda c: GROUPS['fix_page_named_subject'](c) or GROUPS['fix_page_topic_never_named'](c)
GROUPS['fix_subject_and_multi'] = lambda c: GROUPS['fix_subject_all'](c) or GROUPS['fix_multi_generic'](c)
ONLY = sys.argv[1:]  # optional: run only these group tags
procs = []
for tag, g in GROUPS.items():
    if ONLY and tag not in ONLY: continue
    n = 0
    with open(f'{HERE}/forms_oracle_{tag}.jsonl', 'w', encoding='utf-8') as f:
        for r in rows:
            o = dict(pred[r['id']])
            if g(cls[r['id']]): o['assertions'] = r['facts']; n += 1
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    print(tag, 'rows patched with gold:', n, flush=True)
    for fx in ('1', '0'):
        env = dict(os.environ, FORMS=f'{HERE}/forms_oracle_{tag}.jsonl', FIXU=fx)
        procs.append(subprocess.Popen([sys.executable, '-I', f'{HERE}/e2e.py', f'oracle_{tag}' + ('' if fx == '1' else '_origdecide')],
                                      env=env, stdout=open(f'{HERE}/logs/e2e_oracle_{tag}_{fx}.log', 'w'), stderr=subprocess.STDOUT))
        if len(procs) >= 3:
            procs.pop(0).wait()
for p in procs: p.wait()
