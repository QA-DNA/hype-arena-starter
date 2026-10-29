#!/bin/sh
# Leave-one-family-out robustness runs (dev held out of training as well); measured on dev rows of the left-out family.
PY="/tmp/veridyct-bench/.venv/bin/python -I"; D=/Users/mogaeduard/Downloads/evaluation-data; C=/tmp/veridyct-evalsuite/C
for F in "$@"; do
  N=$(echo $F | tr ':' '_')
  OMP_NUM_THREADS=2 $PY $C/train.py --data $D --out $C/lofo/$N --exclude dev --drop $F > $C/lofo/$N.train.log 2>&1
  $PY $C/extract.py --world dev --artifacts $C/lofo/$N --out $C/lofo/$N > /dev/null
  $PY $C/measure.py --world dev --forms-dir $C/lofo/$N --only $F --tag lofo:$F --errors 2 > $C/lofo/$N.measure.txt
  echo "$F $(grep -A12 '"all"' $C/lofo/$N.measure.txt | grep row_exact)"
done
