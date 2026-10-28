#!/bin/bash
# second queue (replaces the tail of driver.sh): waits for the running arctic job (pid $1), then runs the rest one model at a time
cd /tmp/veridyct-emb/w2
SH=/tmp/veridyct-bench/.venv/bin/python; ALT=/tmp/veridyct-emb/w2/.venv/bin/python
while kill -0 $1 2>/dev/null; do sleep 2; done
echo "=== arctic-l-v2 finished $(date +%T)" >> logs/driver.log
run() {  # run <python> <key> <stages> <logsuffix>
  echo "=== $2 [$4] start $(date +%T)" >> logs/driver.log
  $1 -I run_model.py $2 --stages $3 > logs/$2.$4.log 2>&1
  echo "=== $2 [$4] exit $? $(date +%T)" >> logs/driver.log
}
run $SH bge-m3 embed,cheap,lr main
run $SH stella-400m embed,cheap,lr main
[ -f emb/stella-400m.npz ] || run $ALT stella-400m embed,cheap,lr alt
run $ALT nomic-v1.5 embed,cheap,lr alt
for k in modernbert-embed bge-large e5-large gte-modernbert granite-r2 granite-small; do run $SH $k cheap,lr rerun; done
run $SH jina-v3 embed,cheap,lr main
[ -f emb/jina-v3.npz ] || run $ALT jina-v3 embed,cheap,lr alt
echo "=== queue2 done $(date +%T)" >> logs/driver.log
