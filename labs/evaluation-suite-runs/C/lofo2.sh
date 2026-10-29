#!/bin/sh
PY="/tmp/veridyct-bench/.venv/bin/python -I"; D=/Users/mogaeduard/Downloads/evaluation-data; C=/tmp/veridyct-evalsuite/C
OMP_NUM_THREADS=2 $PY $C/train.py --data $D --out $C/artifacts-devholdout --exclude dev > $C/train-devholdout.log 2>&1
$PY $C/extract.py --world dev --artifacts $C/artifacts-devholdout --out $C/forms-devholdout > /dev/null
$PY $C/measure.py --world dev --forms-dir $C/forms-devholdout --tag devholdout-v3 --errors 2 > $C/devholdout-v3.txt
echo "devholdout $(grep -A12 '"all"' $C/devholdout-v3.txt | grep row_exact) $(grep -A4 '"error_classes"' $C/devholdout-v3.txt | tr -d '\n' | tr -s ' ')"
for F in development:aside:4 development:aside:1 development:aside:5 development:aside:0 development:aside:3 development:aside:2 development:aside:6 development:aside:7 development:recollection development:conversation development:possessive; do
  N=$(echo $F | tr ':' '_')
  $PY $C/extract.py --world dev --artifacts $C/lofo/$N --out $C/lofo/$N > /dev/null
  $PY $C/measure.py --world dev --forms-dir $C/lofo/$N --only $F --tag lofo-v3:$F --errors 2 > $C/lofo/$N.measure3.txt
  echo "$F $(grep -A12 '"all"' $C/lofo/$N.measure3.txt | grep row_exact) $(grep -A4 '"error_classes"' $C/lofo/$N.measure3.txt | tr -d '\n' | tr -s ' ')"
done
echo LOFO2-DONE
