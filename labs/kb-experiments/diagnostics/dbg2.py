import sys
from exp import *
p=eval(sys.argv[1]); seed=int(sys.argv[2]) if len(sys.argv)>2 else 1
lab=np.ones(NP,bool); lab[np.arange(NP)%5==0]=False
L,conf,s,F=predict(lab, p)
R=roles(lab,p)
hid=~lab[PAGE]
bad=[i for i in range(len(ROWS)) if hid[i] and Y[i]=='true' and L[i]=='false']
random.seed(seed)
for i in random.sample(bad,6):
    r=ROWS[i]; print('\n##',r['id'],r['datestr'],r['text'][:110])
    for j,f in enumerate(r['facts']):
        print('  fact',f.key[:2],f.canon,f.op, 'scores',[round(x,2) for x in fact_scores(i,j,R,p)])
        for k,l in sorted(OBS[f.key],key=lambda x:ROWS[x[0]]['date']):
            o=ROWS[k]; print('     ',o['id'],o['datestr'],o['label'],'LAB' if lab[o['page']] else 'hid', o['facts'][l].canon, '<-own' if o['page']==r['page'] else '')
