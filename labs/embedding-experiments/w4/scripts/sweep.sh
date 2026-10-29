#!/bin/bash
# Sequential sweep, one model at a time (2 threads). key:budget_seconds
PY=/tmp/veridyct-bench/.venv/bin/python
cd /tmp/veridyct-emb/w4
for kb in ce-xsmall:140 ce-distilroberta:120 ce-minilm2-l6-h768:120 ce-small:120 ts-deberta-small-long-nli:120 \
          albert-xlarge-vitaminc-mnli:200 ml-base-zeroshot2:120 ml-base-mnli-fever-anli:120 ce-base:120 \
          ml-modernbert-base-zeroshot2:120 bart-large-mnli:150 ml-large-zeroshot2:150; do
  k=${kb%%:*}; b=${kb##*:}
  echo "=== $(date +%H:%M:%S) $k budget=$b" >> logs/sweep.log
  $PY -I scripts/nli_run.py $k $b > logs/$k.log 2>&1
  echo "--- $(date +%H:%M:%S) $k exit=$? : $(grep -E 'FAILED|FINISHED' logs/$k.log | tr '\n' ' ')" >> logs/sweep.log
done
echo "SWEEP DONE $(date +%H:%M:%S)" >> logs/sweep.log
