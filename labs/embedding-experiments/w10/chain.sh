#!/bin/bash
# stage 2: waits for the stage-1 driver, then runs (one model at a time): albert (token_type_ids fix), GLiClass x2, extras
cd /tmp/veridyct-emb/w10
until grep -q "ALL DONE" logs/driver.log; do sleep 4; done
S=/tmp/veridyct-bench/.venv/bin/python; G=/tmp/veridyct-emb/w10/.venv/bin/python
echo "=== stage2 albert $(date +%T)" >> logs/driver.log
PYTHONDONTWRITEBYTECODE=1 $S -I nli_run.py albert-vitaminc > logs/albert-vitaminc.log 2>&1 || echo "FAILED albert-vitaminc" >> logs/driver.log
for k in gliclass-edge gliclass-modern-base; do
  echo "=== stage2 $k $(date +%T)" >> logs/driver.log
  PYTHONDONTWRITEBYTECODE=1 $G -I gli_run.py $k > logs/$k.log 2>&1 || echo "FAILED $k" >> logs/driver.log
done
for k in finecat-xxs finecat-xs finecat-s; do
  echo "=== stage2 attr_variants $k $(date +%T)" >> logs/driver.log
  PYTHONDONTWRITEBYTECODE=1 $S -I attr_variants.py $k > logs/attrvar-$k.log 2>&1 || echo "FAILED attrvar $k" >> logs/driver.log
done
for k in finecat-v2-m finecat-s; do
  echo "=== stage2 extra $k $(date +%T)" >> logs/driver.log
  PYTHONDONTWRITEBYTECODE=1 $S -I nli_extra.py $k > logs/extra-$k.log 2>&1 || echo "FAILED extra $k" >> logs/driver.log
done
echo "=== STAGE2 DONE $(date +%T)" >> logs/driver.log
