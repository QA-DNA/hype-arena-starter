#!/bin/bash
# w3 queue 3 (after queue 2 finished): cleanup, GloVe re-run, Qwen3 without instruction, then the mean-centered extra pass.
cd /tmp/veridyct-emb/w3
PY=/tmp/veridyct-bench/.venv/bin/python
echo "=== cleanup (glove) $(date +%T)"; $PY -I cleanup.py glove
for k in glove-6B-300d Qwen3-Embedding-0.6B-noprompt nomic-embed-text-v2-moe; do
  echo "=== $k $(date +%T)"; $PY -I run_model.py "$k" 2>&1 | grep --line-buffered -v "^W10\|redirects"
done
echo "=== cleanup (superseded failures) $(date +%T)"; $PY -I cleanup.py
echo "=== centered $(date +%T)"
$PY -I run_centered.py "$@" 2>&1 | grep --line-buffered -v "^W10\|redirects"
echo "=== QUEUE 3 DONE $(date +%T)"
