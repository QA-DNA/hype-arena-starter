#!/bin/sh
cd /tmp/veridyct-emb/w1
while ! grep -q "EXTRAS DONE" rerun.log 2>/dev/null; do sleep 3; done
SH=/tmp/veridyct-bench/.venv/bin/python; W1=/tmp/veridyct-emb/w1/.venv/bin/python
for m in $(python3 -c "import sys; sys.path.insert(0,'.'); from models import MODELS; print(' '.join(m for m in MODELS if not MODELS[m]['trc']))"); do
  $SH -I speed_cpu.py $m > slog_$(echo $m | sed 's#/#__#').txt 2>&1; echo "$(date +%T) speedcpu $m rc=$?" >> rerun2.log
done
for m in Alibaba-NLP/gte-base-en-v1.5 jinaai/jina-embeddings-v2-small-en; do
  $W1 -I speed_cpu.py $m > slog_$(echo $m | sed 's#/#__#').txt 2>&1; echo "$(date +%T) speedcpu(w1) $m rc=$?" >> rerun2.log
done
echo "$(date +%T) SPEEDCPU DONE" >> rerun2.log
