"""Stage-1 parameter grids for the F1 standalone labellers (printed as run.py --variant args)."""
import json, sys
V = "F1/f1var.py:Variant"
G = {
 "vote": [
   {"method": "vote", "anchors": ["soft", "hard", "off"], "wa": [1.0, 3.0, 10.0]},
   {"method": "vote", "win": [7, 14, 30, 60, 120], "anchors": ["soft", "hard"], "wa": [1.0, 3.0, 10.0], "wu": [0.3, 1.0]},
   {"method": "vote", "tau": [7.0, 15.0, 30.0, 60.0, 120.0], "beta": [0.5, 1.0], "anchors": ["soft", "hard"], "wa": [1.0, 3.0, 10.0], "wu": [0.3, 1.0]},
 ],
 "tf": [
   {"method": "truthfinder", "tau": [None, 15.0, 30.0, 60.0], "gamma": [0.1, 0.3, 1.0], "rho": [0.2, 0.5, 1.0], "sup": ["contain", "overlap"], "t0": [0.8, 0.9]},
 ],
 "accu": [
   {"method": "accu", "tau": [7.0, 15.0, 30.0, 60.0, 120.0], "nfalse": [3, 10, 30], "beta": [0.5, 1.0], "alpha": [1.0, 3.0, 10.0], "selfw": [0.0, 1.0]},
 ],
 "crh": [
   {"method": "crh", "tau": [7.0, 15.0, 30.0, 60.0, 120.0], "wa": [2.0, 5.0, 20.0], "agg": ["mean", "sum"], "numeric": [True, False]},
 ],
 "ds": [
   {"method": ["ds", "ltm"], "seg_w": [None, 15, 30, 60], "anchor_end": [0.75, 0.9, 0.97], "pages_as": ["page", "cluster"], "a1": [[8.0, 2.0], [2.0, 1.0]]},
   {"method": ["ds", "ltm"], "bound": "fixed", "seg_w": [15, 30, 60], "pages_as": ["page", "cluster"]},
 ],
 "dyn": [
   {"method": "dynworld", "lam": [15.0, 30.0, 60.0, 120.0, 240.0], "E0": [0.7, 0.85, 0.95], "F0": [0.03, 0.08, 0.15], "back": [0.005, 0.02, 0.1], "selfx": [True, False]},
 ],
 "sums": [
   {"method": ["sums", "avglog"], "tau": [15.0, 30.0, 60.0], "wa": [2.0, 5.0, 20.0]},
 ],
}
if __name__ == "__main__":
    out = []
    for fam in sys.argv[1].split(","):
        for g in G[fam]:
            out += ["--variant", V + "=" + json.dumps(g)]
    print("\n".join(out))
