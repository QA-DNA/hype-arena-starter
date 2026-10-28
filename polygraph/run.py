"""The entrypoint the judges run: python -m polygraph.run

Reads /universe/universe.csv + lexicon.json, writes /output/output.csv.

1. Within seconds it writes a SAFE output (every unlabelled row `true` at the base rate +
   claims from the bundled gold KB), so a crash later still hands in a valid table.
2. Then it runs the full pipeline and overwrites the table atomically.
3. It watches ARENA_DEADLINE: on SIGTERM it exits, leaving the last complete table.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path

from . import pipeline
from .kb import KB
from .model import Verdict
from .forge import generate
from .tables import write_output
from .validate import normalize_text


def log(msg: str) -> None:
    left = ""
    if os.environ.get("ARENA_DEADLINE"):
        left = f" [{int(float(os.environ['ARENA_DEADLINE']) - time.time())}s left]"
    print(f"{time.strftime('%H:%M:%S')}{left} {msg}", flush=True)


def safe_output(rows, lexicon, bundle, out: Path) -> None:
    verdicts = [Verdict(r.id, "true", 0.6) for r in rows if not r.label]
    kb = KB.from_gold(lexicon, rows, {r.id: bundle.forms[r.id] for r in rows if r.label and r.id in bundle.forms})
    claims = generate(kb, {normalize_text(r.text) for r in rows})
    write_output(out, verdicts, claims)
    log(f"safe output written: {len(verdicts)} labels, {len(claims)} claims")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--universe", default="/universe")
    p.add_argument("--output", default="/output")
    p.add_argument("--trace", help="also write the frontend trace JSON to this path")
    a = p.parse_args(argv)

    signal.signal(signal.SIGTERM, lambda *_: (log("SIGTERM: keeping the last complete table"), sys.exit(0)))
    out = Path(a.output) / "output.csv"
    rows, lexicon = pipeline.load_universe(a.universe)
    bundle = pipeline.Bundle.load()
    log(f"read {len(rows)} rows, {sum(not r.label for r in rows)} unlabelled; lexicon {len(lexicon.subjects)} subjects")

    try:
        safe_output(rows, lexicon, bundle, out)
    except Exception:
        traceback.print_exc()

    result = pipeline.run(rows, lexicon, bundle)
    for s in result.stages:
        log(f"  {s['name']:<10} {s['ms']:>9} ms  {s['count']}")
    write_output(out, result.verdicts, result.claims)
    log(f"final output written: {len(result.verdicts)} labels, {len(result.claims)} claims")
    if a.trace:
        from .trace import to_trace
        Path(a.trace).write_text(json.dumps(to_trace(rows, result), ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"trace written to {a.trace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
