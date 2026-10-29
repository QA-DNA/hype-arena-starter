"""Markdown tables from results/e2e.jsonl (latest line per tag/engine/world).
Usage: python -I tables.py tag-engine [tag-engine ...] [--slice answerability]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite  # noqa: E402
args = [a for a in sys.argv[1:] if not a.startswith("--")]
sl = sys.argv[sys.argv.index("--slice") + 1] if "--slice" in sys.argv else None
if sl: args.remove(sl)
latest = {}
for line in open(os.path.join(suite.OUT, "results", "e2e.jsonl")):
    r = json.loads(line)
    latest[(f"{r['tag']}-{r['engine']}", r["world"])] = r
for run in args:
    print(f"\n**{run}**\n")
    if sl:
        print("| world | slice value | n | accuracy | macro-F1 | points/row |\n|---|---|---:|---:|---:|---:|")
    else:
        print("| world | n | accuracy | macro-F1 | bal. acc | false P / R | unsure P / R | points/row | coverage | ECE | engine s |")
        print("|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|")
    for w in suite.WORLDS:
        r = latest.get((run, w))
        if not r: continue
        m = r["metrics"]; pc = m["per_class"]
        if sl:
            for v, s in m["slices"].get(sl, {}).items():
                print(f"| {w} | {v} | {s['n']} | {s['accuracy']:.4f} | {s['macro_f1']:.4f} | {s['points_per_row']:.4f} |")
            continue
        e = "" if m["ece10"] is None else f"{m['ece10']:.4f}"
        print(f"| {w} | {m['n']} | {m['accuracy']:.4f} | {m['macro_f1']:.4f} | {m['balanced_accuracy']:.4f} | "
              f"{pc['false']['precision']:.4f} / {pc['false']['recall']:.4f} | {pc['unsure']['precision']:.4f} / {pc['unsure']['recall']:.4f} | "
              f"{m['points_per_row']:.4f} | {m['coverage']:.4f} | {e} | {r['runtime_s']:.2f} |")
