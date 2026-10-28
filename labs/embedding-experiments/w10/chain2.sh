#!/bin/bash
# stage 2 (reordered): waits for the stage-1 driver, then runs one model at a time
cd /tmp/veridyct-emb/w10
until grep -q "ALL DONE" logs/driver.log; do sleep 4; done
S=/tmp/veridyct-bench/.venv/bin/python; G=/tmp/veridyct-emb/w10/.venv/bin/python
run() { name=$1; shift; echo "=== stage2 $name $(date +%T)" >> logs/driver.log; "$@" > logs/$name.log 2>&1 || echo "FAILED $name" >> logs/driver.log; }
export PYTHONDONTWRITEBYTECODE=1
run albert-vitaminc $S -I nli_run.py albert-vitaminc
run gliclass-edge $G -I gli_run.py gliclass-edge
run gliclass-modern-base $G -I gli_run.py gliclass-modern-base
run attrvar-xxs $S -I attr_variants.py finecat-xxs
run attrvar-xs $S -I attr_variants.py finecat-xs
run extra-v2-m $S -I nli_extra.py finecat-v2-m
run attrvar-s $S -I attr_variants.py finecat-s
run attrvar-v2-m-T3 $S -I attr_variants.py finecat-v2-m --only=T3
echo "=== STAGE2 DONE $(date +%T)" >> logs/driver.log
