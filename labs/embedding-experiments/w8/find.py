import json, sys
out = json.load(open('eng_v2_flat.json'))
pats = [p.lower() for p in sys.argv[1:]]
for o in sorted(out, key=lambda o: -(o['mean'] or 0)):
    n = o['name'].lower()
    if any(p in n for p in pats):
        print(f"{o['rank']} | {o['name']} | {o['params']} | dim={o['dim']} | max={o['maxtok']} | mean={(o['mean'] or 0)*100:.2f} | zs={o['zs']} | {o['lic']} | {o['rel']}")
