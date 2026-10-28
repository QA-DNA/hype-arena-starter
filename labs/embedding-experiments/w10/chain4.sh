#!/bin/bash
cd /tmp/veridyct-emb/w10
S=/tmp/veridyct-bench/.venv/bin/python; G=/tmp/veridyct-emb/w10/.venv/bin/python
run() { name=$1; shift; echo "=== stage3 $name $(date +%T)" >> logs/driver.log; "$@" > logs/$name.log 2>&1 || echo "FAILED $name" >> logs/driver.log; }
export PYTHONDONTWRITEBYTECODE=1
run gliclass-modern-base-speed $G -I gli_run.py gliclass-modern-base --speed-only
run speed-recheck $S -I speed_recheck.py
run attrvar-xxs $S -I attr_variants.py finecat-xxs
run attrvar-xs $S -I attr_variants.py finecat-xs
run extra-v2-m $S -I nli_extra.py finecat-v2-m
run attrvar-s $S -I attr_variants.py finecat-s
echo "=== STAGE3 DONE $(date +%T)" >> logs/driver.log
