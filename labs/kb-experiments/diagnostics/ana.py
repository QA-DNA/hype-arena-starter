from exp import *
from cat import cat
lab=np.ones(NP,bool)
T=C.defaultdict(C.Counter)
for i,r in enumerate(ROWS):
    if len(r['facts'])!=1 or Y[i]=='unsure': continue
    f=r['facts'][0]; D=r['date']
    an=[(ROWS[k]['date'],ROWS[k]['facts'][l]) for k,l in OBS[f.key] if ROWS[k]['page']!=r['page'] and Y[k]=='true']
    ever=any(f.consistent(a[1]) for a in an)
    evb=any(f.consistent(a[1]) for a in an if a[0]<D); eva=any(f.consistent(a[1]) for a in an if a[0]>D)
    othf=sum(1 for k,l in OBS[f.key] if ROWS[k]['page']!=r['page'] and Y[k]=='false' and f.consistent(ROWS[k]['facts'][l]))
    c=cat(i,0,lab)
    T[c+' ever=%d bef=%d aft=%d'%(ever,evb,eva)][Y[i]]+=1
for k,v in sorted(T.items(), key=lambda x:-sum(x[1].values())):
    if sum(v.values())>=8: print(k, dict(v))
# lying pages: share of false rows on pages with >=2 false rows
fp=C.Counter(PAGE[Y=='false']); print('false rows on pages with >=2 false:', sum(c for c in fp.values() if c>=2),'/',sum(fp.values()))
