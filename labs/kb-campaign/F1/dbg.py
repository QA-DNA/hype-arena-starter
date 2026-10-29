import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness")); sys.path.insert(0, HERE)
import numpy as np, td, json
from world import load_track
from sklearn.metrics import roc_auc_score
tr = load_track("P80")
w, gold, sc = tr.folds[0]
p = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
pf, rel, ex = td.run_method(w, sys.argv[1], **p)
pr = td.row_prod(w, pf)
m = np.isin(gold, ["true", "false"])
print("AUC rows", roc_auc_score(gold[m] == "true", pr[sc][m]))
print("quantiles true", np.quantile(pr[sc][m][gold[m]=="true"], [.05,.25,.5,.75]).round(3), "false", np.quantile(pr[sc][m][gold[m]=="false"], [.25,.5,.75,.95]).round(3))
