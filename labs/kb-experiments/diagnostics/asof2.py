from exp import *
dates = sorted({r['date'] for r in ROWS}); cut = dates[int(0.8 * len(dates))]
print('distinct dates', len(dates), 'pages', NP, 'cut date', dt.date.fromordinal(cut), 'rows after cut', sum(r['date']>=cut for r in ROWS))
res=C.defaultdict(lambda:[0,0])
for key, obs in OBS.items():
    late = [(ROWS[k]['date'], k, l) for k, l in obs if ROWS[k]['date'] >= cut]
    if not late: continue
    d, k, l = max(late)
    if ROWS[k]['label'] != 'true': continue
    anc = [(ROWS[a]['date'], a, b) for a, b in obs if ROWS[a]['date'] < cut and ROWS[a]['label']=='true']
    if not anc: continue
    nv = len({ROWS[a]['facts'][b].canon for _, a, b in anc})
    dmax = max(e[0] for e in anc); pred = C.Counter(ROWS[a]['facts'][b].canon for e0, a, b in anc if e0 == dmax).most_common(1)[0][0]
    ok = pred == ROWS[k]['facts'][l].canon
    g = 'stable(1 value before cut)' if nv == 1 else 'volatile(>1 value)'
    res[g][0]+=ok; res[g][1]+=1
    kind = ROWS[k]['facts'][l].kind; res['kind='+kind][0]+=ok; res['kind='+kind][1]+=1
for g,(a,n) in sorted(res.items()): print(f'{g}: {a}/{n} = {a/n:.2f}')
