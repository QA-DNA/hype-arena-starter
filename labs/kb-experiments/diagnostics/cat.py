from exp import *
def cat(i,j,lab):
    r=ROWS[i]; f=r['facts'][j]; D=r['date']
    an=[(ROWS[k]['date'],ROWS[k]['facts'][l]) for k,l in OBS[f.key] if ROWS[k]['page']!=r['page'] and lab[ROWS[k]['page']] and Y[k]=='true']
    b=[a for a in an if a[0]<D]; s=[a for a in an if a[0]==D]; n=[a for a in an if a[0]>D]
    def m(x):
        if not x: return '-'
        if x is b: x=[a for a in x if a[0]==max(y[0] for y in x)]
        if x is n: x=[a for a in x if a[0]==min(y[0] for y in x)]
        return 'Y' if any(f.same(a[1]) for a in x) else 'N'
    return m(b)+m(s)+m(n)
lab=np.ones(NP,bool)
T=C.defaultdict(C.Counter)
for i,r in enumerate(ROWS):
    if len(r['facts'])==1: T[cat(i,0,lab)][Y[i]]+=1
print('prev/sameday/next match: label counts (single-fact rows, all other-page true anchors)')
for k,v in sorted(T.items(), key=lambda x:-sum(x[1].values())): print(k, dict(v), 'false-rate %.2f'%(v['false']/sum(v.values())))
