"""Stage A grid (selection tracks only). Prints run.py --variant args, one per line."""
import json
M, G = "F4/f4models.py", "F4/f4graph.py"
P = "F4/f4graph.py:"
L = "F4/f4lex.py:"
ex = [[], [P + "all_feats"], [P + "prop_p"], [P + "prop_feats"], [P + "page_lie"], [P + "blame_feats"],
      [L + "lex_features"], [L + "lex_small"], [P + "all_feats", L + "lex_features"]]
v = []
v.append((M, [{"mil": m, "extra_features": e} for m in (0, 1, 2, 3) for e in ex]))
v.append((M, [{"mil": m, "mil_kind": "share"} for m in (1, 2, 3)]))
v.append((M, [{"mil": m, "lap": l, "lap_page": lp} for m in (0, 2) for l in (0.003, 0.01, 0.03, 0.1, 0.3) for lp in (0.0, 1.0)]))
v.append((M, [{"mil": m, "pseudo": r, "pw": pw, "phi": phi} for m in (0, 2) for r in (1, 2) for pw in (0.3, 1.0) for phi in (0.95, 0.99)]))
v.append((M, [{"mil": m, "selftrain": r, "hi": hi, "lo": lo} for m in (0, 2) for r in (1, 2) for hi in (0.9, 0.95, 0.98) for lo in (0.1, 0.2)]))
import sys
if "--hgb" in sys.argv:
    v.append((M, [{"mil": m, "model": "hgb", "extra_features": e} for m in (0, 2) for e in ([], [P + "all_feats", L + "lex_features"])]))
v.append((M, [{"mil": m, "model": c} for m in (0, 2) for c in ("lrC0.1", "lrC2.0")]))
v.append((M + ":CoTrain", [{"rounds": r, "per_round": k} for r in (1, 2, 3, 5) for k in (0.01, 0.03)]))
v.append((G + ":Prop", [{"mode": md, "tau": t, "beta": b, "gamma": g} for md in ("prop", "spread") for t in (10.0, 30.0, 90.0, 1e9)
                        for b in (0.25, 0.5, 1.0) for g in (0.0, 0.2)]))
v.append((G + ":Prop", [{"mode": md, "pagelie": True, "em": e} for md in ("prop", "spread") for e in (0, 2)]
          + [{"mode": "spread", "page_w": pw} for pw in (0.1, 0.3)] + [{"mode": "ppr", "gamma": g} for g in (0.0, 0.5)]))
for spec, grid in v:
    print(f"{spec}={json.dumps(grid)}")
