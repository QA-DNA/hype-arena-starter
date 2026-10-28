#!/bin/bash
cd /tmp/veridyct-emb/w10
S=/tmp/veridyct-bench/.venv/bin/python
run() { name=$1; shift; echo "=== stage4 $name $(date +%T)" >> logs/driver.log; "$@" > logs/$name.log 2>&1 || echo "FAILED $name" >> logs/driver.log; }
export PYTHONDONTWRITEBYTECODE=1
run attrvar-modernbert-T3 $S -I attr_variants.py modernbert-nli --only=T3
run attrvar-v2-m-T3 $S -I attr_variants.py finecat-v2-m --only=T3
run attrvar-s-T3 $S -I attr_variants.py finecat-s --only=T3
run attrvar-ultra-T3 $S -I attr_variants.py finecat-ultra-m --only=T3
run extra-v2-m $S -I nli_extra.py finecat-v2-m
echo "=== STAGE4 DONE $(date +%T)" >> logs/driver.log
