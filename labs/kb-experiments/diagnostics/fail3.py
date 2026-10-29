from v9 import *
lab=np.ones(NP,bool)
X=fact_feats(lab); t=(YF>=0)
for nm,c in (('pm',0),('nm',2),('eb',22),('ea',23),('stale',24),('prem',25)):
    print(nm, C.Counter(zip(X[t,c].tolist(), YF[t].tolist())))
print('NN', C.Counter(zip(X[t,24].tolist(),YF[t].tolist(), ((X[t,0]==0)&(X[t,2]==0)).tolist())))
