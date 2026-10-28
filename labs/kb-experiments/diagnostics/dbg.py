import sys; sys.argv=['x']
from exp import *
lab=np.ones(NP,bool); lab[np.arange(NP)%5==0]=False
L,conf,s,F=predict(lab, dict(BASE,mode='v2'))
hid=~lab[PAGE]
bad=[i for i in range(len(ROWS)) if hid[i] and Y[i]=='true' and L[i]=='false']
random.seed(1)
for i in random.sample(bad,8):
    r=ROWS[i]; print('\n##',r['id'],r['datestr'],r['text'][:110])
    for f in r['facts']:
        print('  fact',f.key[:2],f.canon,f.op)
        for k,l in sorted(OBS[f.key],key=lambda x:ROWS[x[0]]['date']):
            o=ROWS[k]; print('     ',o['id'],o['datestr'],o['label'],'LAB' if lab[o['page']] else 'hid', o['facts'][l].canon, '<-own' if o['page']==r['page'] else '')
