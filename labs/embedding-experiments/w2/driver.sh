#!/bin/bash
# sequential driver: one model at a time, 2 threads. usage: driver.sh key1 key2 ... (stages from $STAGES)
cd /tmp/veridyct-emb/w2
for k in "$@"; do
  echo "=== $k start $(date +%T)" >> logs/driver.log
  /tmp/veridyct-bench/.venv/bin/python -I run_model.py $k --stages ${STAGES:-embed,cheap,lr} > logs/$k.log 2>&1
  echo "=== $k exit $? $(date +%T)" >> logs/driver.log
done
echo "=== driver done $(date +%T)" >> logs/driver.log
