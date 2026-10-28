"""Run the system exactly as the judges do, minus Docker, then run their format checker.

    python scripts/run_local.py            # practice data, every 5th label hidden
    python scripts/run_local.py --sample   # sample/sample.csv appended to the practice rows

Writes out/universe/ (the input), out/output/output.csv and out/trace.json (for the frontend).
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", action="store_true", help="append sample/sample.csv (from 09:00 on 29 Oct)")
    a = p.parse_args()

    uni, out = ROOT / "out" / "universe", ROOT / "out" / "output"
    shutil.rmtree(uni, ignore_errors=True)  # keep out/cache (eval_labels.py's extraction cache)
    shutil.rmtree(out, ignore_errors=True)
    uni.mkdir(parents=True)
    out.mkdir(parents=True)
    subprocess.run([sys.executable, ROOT / "scripts" / "input.py", ROOT / "data" / "practice.csv", uni / "universe.csv"], check=True)
    shutil.copy(ROOT / "data" / "lexicon.json", uni / "lexicon.json")
    if a.sample:
        sample = ROOT / "sample" / "sample.csv"
        with open(sample, encoding="utf-8-sig", newline="") as f, open(uni / "universe.csv", "a", encoding="utf-8", newline="") as g:
            w = csv.writer(g)
            for r in csv.DictReader(f):
                w.writerow([r["id"], r["text"], r["date"], ""])
        print(f"appended {sample}")

    subprocess.run([sys.executable, "-m", "polygraph.run", "--universe", uni, "--output", out,
                    "--trace", ROOT / "out" / "trace.json"], check=True, cwd=ROOT)
    return subprocess.run([sys.executable, ROOT / "scripts" / "check_output.py", out,
                           ROOT / "data" / "practice.csv", uni / "universe.csv"]).returncode


if __name__ == "__main__":
    sys.exit(main())
