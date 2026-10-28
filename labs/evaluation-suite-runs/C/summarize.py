"""Compact tables for REPORT.md from results/C.jsonl (tag final) and results/e2e.jsonl (worker C)."""
import json
R = [json.loads(l) for l in open('/tmp/veridyct-evalsuite/results/C.jsonl')]
last = {}
for r in R:
    if r['tag'] == 'final' and not r.get('only'):
        last[r['world']] = r
print('| World | Split | Pair F1 | Triple F1 | Row exact | Anchors row exact | Targets row exact | Interval exact |')
print('| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |')
for w in ['dev', 'synth', 'diag', 'pilot', 'prac', 'extdev', 'clean', 'cal', 'sealed', 'extcal', 'extsealed']:
    if w not in last: continue
    r = last[w]; a = r['all']
    f = lambda x: '%.2f%%' % (100 * x) if x is not None else 'n/a'
    print(f"| {w} | {'HELD-OUT' if r['held_out'] else 'in-sample'} | {f(a['pair']['f1'])} | {f(a['trip']['f1'])} | {f(a['row_exact'])} | "
          f"{f(r.get('anchors', {}).get('row_exact'))} | {f(r['targets']['row_exact'])} | {f(a.get('interval_exact_when_stated'))} |")
try:
    E = [json.loads(l) for l in open('/tmp/veridyct-evalsuite/results/e2e.jsonl')]
except FileNotFoundError:
    E = []
e = {}
for r in E:
    if r.get('tag') == 'C':
        e[(r['world'], r['engine'])] = r
if e:
    print('\n| World | Split | Engine | n targets | Accuracy | Macro-F1 | Balanced acc | Points/row | ECE |')
    print('| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    for w in ['dev', 'synth', 'diag', 'pilot', 'prac', 'extdev', 'clean', 'cal', 'sealed', 'extcal', 'extsealed']:
        for eng in ('interval', 'point'):
            if (w, eng) not in e: continue
            m = e[(w, eng)]['metrics']
            g = lambda k: '%.4f' % m[k] if m.get(k) is not None else 'n/a'
            print(f"| {w} | {'HELD-OUT' if w in ('cal', 'sealed', 'extcal', 'extsealed') else 'in-sample'} | {eng} | {m['n']} | {g('accuracy')} | {g('macro_f1')} | {g('balanced_accuracy')} | {g('points_per_row')} | {g('ece10')} |")
