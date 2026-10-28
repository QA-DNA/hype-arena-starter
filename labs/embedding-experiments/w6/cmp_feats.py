"""Diagnostic: V9+dd_cos95x fact features of ORIGINAL facts, clean vs hlie (same R10 seed). Usage: cmp_feats.py base|hlie SEED"""
import sys, numpy as np
scen, seed = sys.argv[1], int(sys.argv[2])
sys.argv = ['fusion.py', scen, str(seed)]
sys.path.insert(0, '/tmp/veridyct-emb/w6')
import fusion as F
lab = list(F.my_splits('R10'))[seed]
X = F.ff(lab, dd=sys.argv[3] if len(sys.argv) > 3 else 'cos95x')
orig = ~F.COPY[F.FROW]
np.save(f'/tmp/veridyct-emb/w6/cache/cmp_{scen}_{seed}.npy', X[orig])
