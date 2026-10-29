from v9 import *
lab=np.ones(NP,bool); lab[np.arange(NP)%5==2]=False
X=fact_feats(lab); trf=lab[FPAGE]&(YF>=0)
for model in ('lr','hgb'):
    m=make(model).fit(X[trf],YF[trf]); pf=m.predict_proba(X)[:,1]
    for rid in ('p-1196','p-365','p-499','p-985'):
        i=[k for k,r in enumerate(ROWS) if r['id']==rid][0]
        print(model, rid, [ (round(pf[n],3), X[n][[0,2,22,23,24,25]].tolist()) for n,(a,b) in enumerate(FIDX) if a==i])
