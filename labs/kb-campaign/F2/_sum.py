"""Dev helper: per (class, engine, hash) config count and best selection score."""
import sys, json, collections as C
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import table
R = table.load()
G = C.defaultdict(list)
for k, t in R.items():
    if 'P80' not in t or 'P10' not in t:
        continue
    p = json.loads(k[1]); s = (t['P80']['metrics']['points_per_row'] + t['P10']['metrics']['points_per_row']) / 2
    G[(k[0], p.get('engine', ''), k[2][:6])].append((s, t['P80']['metrics']['points_per_row'], t['P10']['metrics']['points_per_row'], k[1], t['P80'].get('metrics_std', {}).get('points_per_row'), t['P10'].get('metrics_std', {}).get('points_per_row'), t['P80']['ts']))
tot = 0
for g, L in sorted(G.items(), key=lambda x: min(r[6] for r in x[1])):
    L.sort(reverse=True); tot += len(L)
    b = L[0]
    print(f"{g[0]:10s} {g[1]:8s} [{g[2]}] n={len(L):4d} first={min(r[6] for r in L)[:16]} best sel {b[0]:.4f} P80 {b[1]:.4f}+-{b[4] or 0:.3f} P10 {b[2]:.4f}+-{b[5] or 0:.3f} {b[3]}")
print("total configs", tot)
