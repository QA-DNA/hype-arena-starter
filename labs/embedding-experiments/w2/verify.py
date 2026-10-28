"""check: the probe predictions derived from run_model.fold_fits equal H.run_probe_attr's. usage: verify.py key..."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/w2')
import run_model as R, numpy as np
H = R.H
for key in sys.argv[1:]:
    meta, Z, Xp, Xs, Xq = R.load_emb(key); X, fa = Xp[R.SF], H.page_folds(R.sf)
    m0, p0 = H.run_probe_attr(X, R.sf, R.lex, fa)
    pp = R.probe_pred(R.fold_fits(X, fa))
    assert list(pp) == list(p0), key
    m1 = H.attr_metrics(H._attrs(R.sf), pp, H.train_counts(R.sf, fa))
    assert m0 == m1, (m0, m1)
    print(key, 'own fit == H.run_probe_attr; acc_all', round(m0['acc_all'], 3))
