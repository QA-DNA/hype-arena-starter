"""Leaderboard over every $KBC_RESULTS_DIR/*.jsonl (errors files skipped).
Selection score = mean arena points per row over P80 and P10; tie-break lower ECE, then higher macro-F1
(means over the two). One row per (variant, params, src_hash); the latest record per track wins.
Suite tracks are test columns (points per row).

  python -I leaderboard.py [--sort selection|<track>] [--tracks Sdev-jt,Scal-jt] [--worker F3] [--top 50]
      [--metric points_per_row|accuracy|macro_f1|ece10] [--json]
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from world import RESULTS_DIR, SELECTION  # noqa: E402


def load(worker=None):
    rows = {}
    for p in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.jsonl"))):
        if p.endswith(".errors.jsonl"):
            continue
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if worker and r.get("worker") != worker:
                continue
            key = (r["variant"], json.dumps(r["params"], sort_keys=True), r.get("src_hash"))
            cur = rows.setdefault(key, {"variant": key[0], "params": key[1], "src_hash": key[2],
                                        "workers": set(), "tracks": {}})
            cur["workers"].add(r["worker"])
            old = cur["tracks"].get(r["track"])
            if old is None or r["ts"] >= old["ts"]:
                cur["tracks"][r["track"]] = r
    return list(rows.values())


def score(e):
    t = e["tracks"]
    if not all(s in t for s in SELECTION):
        return None
    mean = lambda k: sum(t[s]["metrics"][k] if t[s]["metrics"][k] is not None else 1.0 for s in SELECTION) / len(SELECTION)  # noqa
    return mean("points_per_row"), mean("ece10"), mean("macro_f1")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sort", default="selection")
    ap.add_argument("--tracks", default="")
    ap.add_argument("--worker")
    ap.add_argument("--metric", default="points_per_row")
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--all", action="store_true", help="also list entries missing a selection track")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ents = load(a.worker)
    for e in ents:
        e["sel"] = score(e)
    test = [t for t in a.tracks.split(",") if t] or sorted({t for e in ents for t in e["tracks"]} - set(SELECTION))
    if not a.all and a.sort == "selection":
        ents = [e for e in ents if e["sel"]]

    def key(e):
        if a.sort == "selection":
            s = e["sel"] or (-9, 9, -9)
            return (-s[0], s[1], -s[2])
        r = e["tracks"].get(a.sort)
        return -(r["metrics"][a.metric] if r and r["metrics"][a.metric] is not None else -9)
    ents.sort(key=key)
    if a.top:
        ents = ents[:a.top]
    if a.json:
        print(json.dumps([{"variant": e["variant"], "params": json.loads(e["params"]), "src_hash": e["src_hash"],
                           "selection": e["sel"], "tracks": {t: r["metrics"] for t, r in e["tracks"].items()}}
                          for e in ents]))
        return
    f = lambda x: "-" if x is None else f"{x:.4f}"  # noqa: E731
    hdr = ["#", "sel_pts", "ece", "mf1", "P80", "P10"] + test + ["variant params [hash] workers"]
    print("\t".join(hdr))
    for n, e in enumerate(ents, 1):
        s = e["sel"] or (None, None, None)
        cols = [str(n), f(s[0]), f(s[1]), f(s[2])]
        for t in list(SELECTION) + test:
            r = e["tracks"].get(t)
            cols.append(f(r["metrics"][a.metric]) if r else "-")
        cols.append(f"{e['variant']} {e['params']} [{e['src_hash']}] {','.join(sorted(e['workers']))}")
        print("\t".join(cols))
    print(f"(columns P80.. are {a.metric}; sel_pts/ece/mf1 = mean over {', '.join(SELECTION)})")


if __name__ == "__main__":
    main()
