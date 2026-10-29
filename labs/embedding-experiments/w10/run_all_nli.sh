#!/bin/bash
# one model at a time, shared venv (read-only), 2 threads
cd /tmp/veridyct-emb/w10
for k in "$@"; do
  echo "=== $k $(date +%T)" >> logs/driver.log
  PYTHONDONTWRITEBYTECODE=1 /tmp/veridyct-bench/.venv/bin/python -I nli_run.py $k > logs/$k.log 2>&1 || echo "FAILED $k" >> logs/driver.log
done
echo "=== ALL DONE $(date +%T)" >> logs/driver.log
