#!/bin/bash
# one model at a time, shared venv; usage: run_queue.sh <venv-python> <id> [<id> ...]
PY="$1"; shift
for m in "$@"; do
  f=$(echo "$m" | tr '/' '_')
  echo "=== $(date +%T) start $m" >> /tmp/veridyct-emb/w9/logs/queue.log
  "$PY" -I /tmp/veridyct-emb/w9/bench.py "$m" > "/tmp/veridyct-emb/w9/logs/$f.log" 2>&1
  echo "=== $(date +%T) end $m rc=$?" >> /tmp/veridyct-emb/w9/logs/queue.log
done
