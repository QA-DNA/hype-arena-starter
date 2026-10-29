#!/bin/bash
# w3 queue: one model per process, strictly sequential (2 threads each). SAFE, GREY, then RISKY (heavy last).
cd /tmp/veridyct-emb/w3
for k in "$@"; do
  echo "=== $k $(date +%T)"
  /tmp/veridyct-bench/.venv/bin/python -I run_model.py "$k" 2>&1 | grep -v "^W10\|redirects"
done
echo "=== QUEUE DONE $(date +%T)"
