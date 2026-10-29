"""Stage C grid (selection tracks only): Laplacian LR without same-page edges (lap_page=0, Stage A's best),
combined with self-training, pseudo-labels, F4 plugins and (cross-family) F2 temporal plugins."""
import json
M = "F4/f4models.py"
P, F2 = "F4/f4graph.py:", "F2/f2feat.py:"
g = [{"mil": 2, "lap": l, "lap_page": 0.0, "lap_tau": t} for l in (0.01, 0.02, 0.03, 0.05) for t in (10.0, 30.0, 90.0)]
for l in (0.02, 0.03):
    b = {"mil": 2, "lap": l, "lap_page": 0.0}
    g += [dict(b, selftrain=r, hi=hi, lo=lo) for r in (1, 2) for hi, lo in ((0.9, 0.2), (0.95, 0.2), (0.98, 0.1))]
    g += [dict(b, pseudo=2, pw=0.3, phi=phi) for phi in (0.95, 0.97)]
    g += [dict(b, extra_features=e) for e in ([P + "page_lie"], [P + "prop_feats"], [P + "blame_feats"], [P + "all_feats"],
                                              [F2 + "core"], [F2 + "hmm"], [F2 + "all"])]
    g += [dict(b, selftrain=2, hi=0.9, lo=0.2, extra_features=[F2 + "core"])]
g += [{"mil": m, "lap": 0.03, "lap_page": 0.0} for m in (1, 3)] + [{"mil": 2, "mil_kind": "share", "lap": 0.03, "lap_page": 0.0}]
g += [{"mil": 2, "extra_features": [F2 + "core"]}, {"extra_features": [F2 + "core"]}]
print(f"{M}={json.dumps(g)}")
print("v9=" + json.dumps([{"select": "arena", "extra_features": [F2 + "core"]}]))
