#!/bin/zsh
# filtered copy of results (lines with variant+params) -> P3/lbres, then leaderboard over it
KBC="$(cd "$(dirname "$0")/.." && pwd)"
rm -rf $KBC/P3/lbres; mkdir -p $KBC/P3/lbres
for f in $KBC/results/*.jsonl; do
  case $f in *.errors.jsonl) continue;; esac
  $KBC/.venv/bin/python -I -c 'import json,sys
for l in open(sys.argv[1]):
    try: r=json.loads(l)
    except Exception: continue
    if "variant" in r and "params" in r and "track" in r and "metrics" in r: sys.stdout.write(l)' $f > $KBC/P3/lbres/$(basename $f)
done
cd $KBC/harness && KBC_RESULTS_DIR=$KBC/P3/lbres $KBC/.venv/bin/python -I leaderboard.py "$@"
