"""Leaderboard like harness/leaderboard.py, skipping non-harness lines (F5-paired.jsonl breaks the original)."""
import glob, json, os, sys
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
def load(skip=("R4",)):
    rows = {}
    for p in sorted(glob.glob(os.path.join(R, "*.jsonl"))):
        if p.endswith(".errors.jsonl"): continue
        for line in open(p, encoding="utf-8"):
            if not line.strip(): continue
            r = json.loads(line)
            if "variant" not in r or "track" not in r or r.get("worker") in skip: continue
            key = (r["variant"], json.dumps(r["params"], sort_keys=True), r.get("src_hash"))
            cur = rows.setdefault(key, {"key": key, "workers": set(), "tracks": {}})
            cur["workers"].add(r["worker"])
            old = cur["tracks"].get(r["track"])
            if old is None or r.get("ts", "") >= old.get("ts", ""): cur["tracks"][r["track"]] = r
    out = []
    for e in rows.values():
        t = e["tracks"]
        if "P80" in t and "P10" in t:
            e["sel"] = (t["P80"]["metrics"]["points_per_row"] + t["P10"]["metrics"]["points_per_row"]) / 2
            out.append(e)
    out.sort(key=lambda e: -e["sel"])
    return out
if __name__ == "__main__":
    ents = load()
    top = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print("n configs with P80+P10:", len(ents))
    f = lambda e, t: ("%.4f" % e["tracks"][t]["metrics"]["points_per_row"]) if t in e["tracks"] else "-"
    for i, e in enumerate(ents[:top], 1):
        v, p, h = e["key"]
        print(i, "%.4f" % e["sel"], f(e, "P80"), f(e, "P10"), f(e, "Sdev-jt"), f(e, "Sdev-jr"), v.split("/")[-2:] and "/".join(v.split("/")[-2:]), p[:150], h, ",".join(sorted(e["workers"])))
