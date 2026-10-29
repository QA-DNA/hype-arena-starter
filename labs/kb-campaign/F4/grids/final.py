"""Final test grid: top 3 (chosen on P80 + P10 only) plus references, on every suite track (S and X forms,
anchors j and n, transfer t and refit r). Prints --variant args, then a --tracks line."""
import json
M, G = "F4/f4models.py", "F4/f4graph.py"
P, F2 = "F4/f4graph.py:", "F2/f2feat.py:"
T1 = {"mil": 2, "lap": 0.02, "lap_page": 0.0, "lap_tau": 10.0, "extra_features": [P + "prop_feats", F2 + "core"]}
T2 = {"mil": 2, "lap": 0.03, "lap_page": 0.0, "lap_tau": 10.0, "extra_features": [P + "prop_feats"]}
T3 = {"mil": 2, "lap": 0.03, "lap_page": 0.0, "lap_tau": 10.0}
REF = [{"mil": 2}, {"mil": 2, "lap": 0.02, "lap_page": 0.0, "lap_tau": 10.0, "extra_features": [P + "prop_feats"],
                    "pseudo": 2, "phi": 0.95, "pw": 0.3}]
print(f"{M}={json.dumps([T1, T2, T3] + REF)}")
print("v9=" + json.dumps([{"select": "arena"}]))
print(f"{G}:Prop=" + json.dumps([{"mode": "prop", "tau": 10.0, "beta": 1.0, "gamma": 0.2}]))
W = ["dev", "diag", "cal", "sealed", "syn", "pilot", "prac", "extdev", "extcal", "extsealed"]
print("TRACKS " + ",".join(f"{f}{w}-{m}{t}" for f in "SX" for w in W for m in "jn" for t in "tr"))
