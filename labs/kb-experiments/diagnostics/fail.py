from v9 import *
lab=np.ones(NP,bool); lab[np.arange(NP)%5==2]=False
out,conf=v9('lr')(lab)
hid=~lab[PAGE]
from cat import cat
full=np.ones(NP,bool)
def show(i):
    r=ROWS[i]; print('  ',r['id'],r['datestr'],Y[i],'->',out[i],'%.2f'%conf[i],'|',r['text'][:90])
    for j,f in enumerate(r['facts']):
        an=sorted([(ROWS[k]['datestr'],ROWS[k]['facts'][l].canon,Y[k][0],'L' if lab[ROWS[k]['page']] else 'h') for k,l in OBS[f.key] if ROWS[k]['page']!=r['page']])
        print('     ',f.key[:2],f.canon,'| others:',an[:12])
for want,got in (('false','true'),('true','false')):
    ids=[i for i in range(len(ROWS)) if hid[i] and Y[i]==want and out[i]==got]
    print(f'== {want} predicted {got}: {len(ids)}')
    random.seed(3)
    for i in random.sample(ids,min(5,len(ids))): show(i)
