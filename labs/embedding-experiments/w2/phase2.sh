#!/bin/bash
# waits for the main driver; then (1) remote-code models that failed under transformers 5 -> own venv (transformers 4.57), (2) re-run cheap+lr for early models to add later variants
cd /tmp/veridyct-emb/w2
while pgrep -f "driver.sh granite-small" > /dev/null; do sleep 3; done
ALT=/tmp/veridyct-emb/w2/.venv/bin/python
for k in nomic-v1.5 stella-400m jina-v3; do
  if [ ! -f emb/$k.npz ]; then
    echo "=== alt-venv $k start $(date +%T)" >> logs/driver.log
    $ALT -I run_model.py $k --stages embed,cheap,lr > logs/$k.alt.log 2>&1
    echo "=== alt-venv $k exit $? $(date +%T)" >> logs/driver.log
  fi
done
for k in modernbert-embed bge-large e5-large gte-modernbert granite-r2 granite-small; do
  echo "=== rerun $k start $(date +%T)" >> logs/driver.log
  /tmp/veridyct-bench/.venv/bin/python -I run_model.py $k --stages cheap,lr > logs/$k.rerun.log 2>&1
  echo "=== rerun $k exit $? $(date +%T)" >> logs/driver.log
done
echo "=== phase2 done $(date +%T)" >> logs/driver.log
