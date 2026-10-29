#!/bin/sh
# Final run: full model on all allowed material, forms for every world, extraction metrics, then worker A's e2e (both engines).
set -e
PY="/tmp/veridyct-bench/.venv/bin/python -I"; D=/Users/mogaeduard/Downloads/evaluation-data; C=/tmp/veridyct-evalsuite/C
OMP_NUM_THREADS=2 $PY $C/train.py --data $D --out $C/artifacts > $C/train-full.log 2>&1
tail -2 $C/train-full.log
for w in dev synth diag pilot prac extdev clean cal sealed extcal extsealed; do
  /usr/bin/time -l $PY $C/extract.py --world $w 2> $C/time-$w.txt
  grep -E 'maximum resident|real' $C/time-$w.txt | tr -s ' ' | head -2
done
for w in dev synth diag pilot prac extdev clean cal sealed extcal extsealed; do
  $PY $C/measure.py --world $w --tag final --errors 2 > $C/final-measure-$w.txt
done
