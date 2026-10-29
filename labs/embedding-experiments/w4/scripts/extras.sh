#!/bin/bash
# usage: extras.sh REV_MODEL_1 REV_MODEL_2 ATTR_TMPL2_MODEL   (run AFTER the sweep: one model at a time)
PY=/tmp/veridyct-bench/.venv/bin/python; cd /tmp/veridyct-emb/w4
for k in "$1" "$2"; do echo "=== $(date +%H:%M:%S) reverse $k" >> logs/sweep.log; $PY -I scripts/nli_run.py $k 100 --only anchor --reverse > logs/$k.rev.log 2>&1; done
echo "=== $(date +%H:%M:%S) tmpl2 $3" >> logs/sweep.log; $PY -I scripts/nli_run.py "$3" 100 --only attr --tmpl2 > logs/$3.tmpl2.log 2>&1
echo "EXTRAS DONE $(date +%H:%M:%S)" >> logs/sweep.log
