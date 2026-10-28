#!/bin/bash
# sequential, one process at a time. jina in the w9 venv (needs peft), the rest in the shared venv.
L=/tmp/veridyct-emb/w9/logs; B=/tmp/veridyct-emb/w9/bench.py; SH=/tmp/veridyct-bench/.venv/bin/python; W9=/tmp/veridyct-emb/w9/.venv/bin/python
run() { local py="$1"; shift; local tag="$1"; shift; echo "=== $(date +%T) start $tag" >> $L/queue.log; "$py" -I $B "$@" > "$L/$tag.log" 2>&1; echo "=== $(date +%T) end $tag rc=$?" >> $L/queue.log; }
run $W9 jina-rerun jinaai/jina-embeddings-v5-text-nano
run $SH ultrabert-noprompt dmis-lab/UltraBERT-Embed-150M --noprompt
run $SH bekko-static-d256 hotchpotch/bekko-static-embedding-v1 --trunc 256
run $SH bekko-static-d128 hotchpotch/bekko-static-embedding-v1 --trunc 128
run $SH bekko-static-d64 hotchpotch/bekko-static-embedding-v1 --trunc 64
run $SH mdbr-d256 MongoDB/mdbr-leaf-mt --trunc 256
echo "=== $(date +%T) extras done" >> $L/queue.log
