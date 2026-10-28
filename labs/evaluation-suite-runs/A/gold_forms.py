"""Gold adapter: gold/labeled.csv forms + rows.jsonl validity_qualifier -> shared forms format.

Writes forms/gold/<world>.jsonl (interval = validity_qualifier, set only on rows whose
text states an interval) and forms/gold-nointerval/<world>.jsonl (interval null).
Prints how validity_qualifier is populated, per world.
Usage: python -I gold_forms.py [--worlds dev,cal,...]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite  # noqa: E402

INTERVAL_TEXT = re.compile(r"\bfrom\b.{4,40}?\bthrough\b", re.I)


def build(world):
    vq, stats = {}, Counter()
    for r in suite.read_jsonl(suite.gold_path(world, "rows.jsonl")):
        q = r.get("validity_qualifier")
        vq[r["id"]] = q
        stated = bool(INTERVAL_TEXT.search(r["text"]))
        stats[f"vq={'set' if q else 'null'} visible={r['visible']} label={r['label']} text_states_interval={stated}"] += 1
        if q:
            stats["vq: date==start"] += r["date"] == q[0]
            stats["vq: equals every atom's gold interval"] += all(
                av.get("interval") == q for av in r["assertion_verdicts"])
    out = []
    for r in suite.read_csv(suite.gold_path(world, "labeled.csv")):
        form = json.loads(r["form"])
        out.append({"id": r["id"],
                    "assertions": [{"subject": a["subject"], "attribute": a["attribute"], "value": a["value"]}
                                   for a in form],
                    "interval": vq.get(r["id"])})
    # clean shares dev's gold ids; keep only ids present in this world's public file
    ids = {r["id"] for r in suite.read_universe(world)}
    out = [o for o in out if o["id"] in ids]
    return out, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worlds", default=",".join(suite.WORLDS))
    a = ap.parse_args()
    for d in ("gold", "gold-nointerval"):
        os.makedirs(os.path.join(suite.OUT, "forms", d), exist_ok=True)
    for w in a.worlds.split(","):
        rows, stats = build(w)
        for d, keep in (("gold", True), ("gold-nointerval", False)):
            with open(os.path.join(suite.OUT, "forms", d, f"{w}.jsonl"), "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(dict(r, interval=r["interval"] if keep else None)) + "\n")
        print(w, len(rows), json.dumps(dict(sorted(stats.items()))))


if __name__ == "__main__":
    main()
