#!/bin/bash
cd /tmp/veridyct-emb/w10
S=/tmp/veridyct-bench/.venv/bin/python
until grep -q "DONE attr_variants" logs/attrvar-v2-m-T3.log 2>/dev/null; do sleep 2; done
run() { name=$1; shift; echo "=== stage5 $name $(date +%T)" >> logs/driver.log; "$@" > logs/$name.log 2>&1 || echo "FAILED $name" >> logs/driver.log; }
export PYTHONDONTWRITEBYTECODE=1
run attrvar-s-T3 $S -I attr_variants.py finecat-s --only=T3
run attrvar-ultra-T3 $S -I attr_variants.py finecat-ultra-m --only=T3
run attrvar-albert-T3 $S -I attr_variants.py albert-vitaminc --only=T3
run extra-v2-m $S -I nli_extra.py finecat-v2-m
echo "=== STAGE5 DONE $(date +%T)" >> logs/driver.log
