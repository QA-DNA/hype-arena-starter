"""Stage D grid (selection tracks only): around the Stage C winner (mil 2, Laplacian without page edges,
prop_feats), plus the cross-family F2 core block."""
import json
M = "F4/f4models.py"
P, F2 = "F4/f4graph.py:", "F2/f2feat.py:"
b = {"mil": 2, "lap_page": 0.0}
g = [dict(b, lap=l, lap_tau=t, extra_features=e) for l in (0.02, 0.03) for t in (10.0, 30.0)
     for e in ([P + "prop_feats"], [P + "prop_feats_t10"], [P + "prop_feats", F2 + "core"])]
g += [dict(b, lap=0.02, lap_tau=t, extra_features=[P + "prop_feats"], pseudo=2, phi=0.95, pw=0.3) for t in (10.0, 30.0)]
g += [dict(b, lap=0.02, lap_tau=t, extra_features=[P + "prop_feats"], selftrain=2, hi=0.98, lo=0.1) for t in (10.0, 30.0)]
g += [dict(b, lap=l, extra_features=[P + "prop_feats"]) for l in (0.015, 0.025)]
g += [dict(b, lap=0.02, extra_features=[P + "prop_feats"], mil=m) for m in (0, 1, 3)]
print(f"{M}={json.dumps(g)}")
