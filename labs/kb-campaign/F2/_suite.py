"""Dev helper: per-config suite points for rows that have suite tracks (prefix S or X via argv)."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import table
P = sys.argv[1] if len(sys.argv) > 1 else "S"
R = table.load()
rows = []
for k, t in R.items():
    if f'{P}dev-jt' not in t or 'P80' not in t or 'P10' not in t:
        continue
    s = (t['P80']['metrics']['points_per_row'] + t['P10']['metrics']['points_per_row']) / 2
    rows.append((s, k, t))
rows.sort(key=lambda x: -x[0])
W = ('dev', 'cal', 'sealed', 'diag', 'syn', 'pilot', 'prac', 'extdev', 'extcal', 'extsealed')
for s, k, t in rows:
    print(f"{s:.4f} P80 {t['P80']['metrics']['points_per_row']:.4f} P10 {t['P10']['metrics']['points_per_row']:.4f} {k[0]} {k[1]} [{k[2][:6]}]")
    for m in 'jn':
        for f in 'tr':
            print('   ', m + f, ' '.join(f"{w}={t[f'{P}{w}-{m}{f}']['metrics']['points_per_row']:.3f}" if f'{P}{w}-{m}{f}' in t
                                     else f"{w}=NA" for w in W))
