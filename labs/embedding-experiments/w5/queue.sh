#!/bin/bash
# Sequential queue: one 4-thread training process at a time.
cd /tmp/veridyct-emb/w5
export HF_HUB_OFFLINE=1 HF_HOME=/tmp/veridyct-bench/hf
PY=/tmp/veridyct-bench/.venv/bin/python
while kill -0 49404 2>/dev/null; do sleep 5; done
$PY -I f2_ce.py cross-encoder/ms-marco-MiniLM-L-6-v2 > logs/f2_msmarco.log 2>&1
$PY -I f3_truth_text.py BAAI/bge-small-en-v1.5 > logs/f3_bge.log 2>&1
$PY -I f4_truth_pair.py > logs/f4.log 2>&1
$PY -I f1_bi.py sentence-transformers/all-MiniLM-L6-v2 > logs/f1_minilm.log 2>&1
$PY -I f4_truth_pair.py strict > logs/f4_strict.log 2>&1
$PY -I f2_ce.py cross-encoder/ms-marco-MiniLM-L-6-v2 lexneg > logs/f2_lexneg.log 2>&1
$PY -I f1_bi.py BAAI/bge-small-en-v1.5 aug > logs/f5_bge_aug.log 2>&1
echo QUEUE_DONE > logs/queue.done
