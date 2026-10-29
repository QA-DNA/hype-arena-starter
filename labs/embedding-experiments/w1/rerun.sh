#!/bin/sh
# waits for run_all.py, drops the fp16 gte-small/gte-base records, reruns them (fp32) + the two remote-code models (w1 venv), then extras for all models
cd /tmp/veridyct-emb/w1
while ! grep -q "ALL DONE" run_all.log; do sleep 3; done
python3 - <<'PY'
import json
p='/tmp/veridyct-emb/results/w1.jsonl'
L=[l for l in open(p)]
bad=('thenlper/gte-small','thenlper/gte-base')
keep=[l for l in L if json.loads(l)['model'] not in bad]; drop=[l for l in L if json.loads(l)['model'] in bad]
open('/tmp/veridyct-emb/w1/discarded_fp16.jsonl','w').writelines(drop)
open('/tmp/veridyct-emb/w1/w1.jsonl.new','w').writelines(keep)
print('dropped', len(drop), 'kept', len(keep))
PY
mv /tmp/veridyct-emb/w1/w1.jsonl.new /tmp/veridyct-emb/results/w1.jsonl
SH=/tmp/veridyct-bench/.venv/bin/python
W1=/tmp/veridyct-emb/w1/.venv/bin/python
for m in thenlper/gte-small thenlper/gte-base; do
  $SH -I bench.py $m > log_$(echo $m | sed 's#/#__#').txt 2>&1; echo "$(date +%T) bench $m rc=$?" >> rerun.log
done
for m in Alibaba-NLP/gte-base-en-v1.5 jinaai/jina-embeddings-v2-small-en; do
  $W1 -I bench.py $m > log_$(echo $m | sed 's#/#__#').txt 2>&1; echo "$(date +%T) bench(w1 venv) $m rc=$?" >> rerun.log
done
echo "$(date +%T) MAIN DONE" >> rerun.log
for m in $(python3 -c "import sys; sys.path.insert(0,'.'); from models import MODELS; print(' '.join(m for m in MODELS if not MODELS[m]['trc']))"); do
  $SH -I extras.py $m > xlog_$(echo $m | sed 's#/#__#').txt 2>&1; echo "$(date +%T) extras $m rc=$?" >> rerun.log
done
for m in Alibaba-NLP/gte-base-en-v1.5 jinaai/jina-embeddings-v2-small-en; do
  $W1 -I extras.py $m > xlog_$(echo $m | sed 's#/#__#').txt 2>&1; echo "$(date +%T) extras(w1 venv) $m rc=$?" >> rerun.log
done
echo "$(date +%T) EXTRAS DONE" >> rerun.log
