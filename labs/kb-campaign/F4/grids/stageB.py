"""Stage B grid (selection tracks only): arena-scored threshold selection, Laplacian LR combinations."""
import json
M, G = "F4/f4models.py", "F4/f4graph.py"
P, L = "F4/f4graph.py:", "F4/f4lex.py:"
REL = [8, 9, 11, 12, 13, 14, 17, 26, 38]  # absolute count columns of the V9 base block
v = [("v9", [{"select": "arena"}, {"select": "arena", "selftrain": 1}])]
g = [{}, {"mil": 2}]
g += [{"mil": m, "lap": l, "lap_tau": t} for m in (0, 2) for l in (0.01, 0.02, 0.03, 0.05) for t in (10.0, 30.0, 90.0)]
for l in (0.02, 0.03):
    g += [{"mil": 2, "lap": l, "extra_features": e} for e in ([P + "all_feats"], [P + "page_lie"], [P + "prop_feats"],
                                                              [P + "blame_feats"], [P + "prop_p"], [L + "lex_small"],
                                                              [P + "page_lie_lab"])]
    g += [{"mil": 2, "lap": l, "pseudo": 2, "phi": 0.95, "pw": pw} for pw in (0.3, 1.0)]
    g += [{"mil": 2, "lap": l, "selftrain": r, "hi": hi, "lo": lo} for r in (1, 2) for hi, lo in ((0.9, 0.2), (0.98, 0.1))]
    g += [{"mil": 2, "lap": l, "drop_features": REL, "extra_features": [P + "prop_feats"]}]
    g += [{"mil": 2, "lap": l, "lap_page": lp} for lp in (0.1, 0.3)]
    g += [{"mil": 2, "lap": l, "model": c} for c in ("lrC0.1", "lrC2.0")]
v.append((M, g))
v.append((G + ":Prop", [{"mode": "prop", "tau": t, "beta": b, "gamma": 0.2} for t in (3.0, 5.0, 10.0, 20.0) for b in (1.0, 2.0)]
          + [{"mode": "prop", "tau": 10.0, "beta": 1.0, "gamma": 0.2, "pagelie": True}]))
for spec, grid in v:
    print(f"{spec}={json.dumps(grid)}")
