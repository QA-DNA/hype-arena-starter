#!/bin/bash
# waits for the sweep, then runs the required extras (one model at a time), then an optional albert conflict top-up
PY=/tmp/veridyct-bench/.venv/bin/python; cd /tmp/veridyct-emb/w4
while ! grep -q "SWEEP DONE" logs/sweep.log; do sleep 3; done
scripts/extras.sh ce-base ml-base-mnli-fever-anli ml-base-zeroshot2
echo "=== $(date +%H:%M:%S) reverse ce-xsmall" >> logs/sweep.log; $PY -I scripts/nli_run.py ce-xsmall 100 --only anchor --reverse > logs/ce-xsmall.rev.log 2>&1
rm -f budget_cap
echo "=== $(date +%H:%M:%S) albert conflict top-up" >> logs/sweep.log; $PY -I scripts/nli_run.py albert-xlarge-vitaminc-mnli 170 --only conflict > logs/albert-xlarge-vitaminc-mnli.topup.log 2>&1
echo "AFTER DONE $(date +%H:%M:%S)" >> logs/sweep.log
