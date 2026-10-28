#!/bin/bash
# after the albert top-up: template 2 on three more attr candidates (cheap, same rows as their tmpl1 run)
PY=/tmp/veridyct-bench/.venv/bin/python; cd /tmp/veridyct-emb/w4
while ! grep -q "AFTER DONE" logs/sweep.log; do sleep 3; done
for k in ml-large-zeroshot2 ml-modernbert-base-zeroshot2 ts-deberta-small-long-nli; do
  echo "=== $(date +%H:%M:%S) tmpl2 $k" >> logs/sweep.log; $PY -I scripts/nli_run.py $k 60 --only attr --tmpl2 > logs/$k.tmpl2.log 2>&1
done
echo "TRIO DONE $(date +%H:%M:%S)" >> logs/sweep.log
