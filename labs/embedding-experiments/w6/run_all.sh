#!/bin/zsh
# w6: two chains, 1 BLAS thread each (2 threads total on the shared machine)
cd /tmp/veridyct-emb/w6
PY=/tmp/veridyct-bench/.venv/bin/python
( W6_THREADS=1 $PY -I fusion.py base > logs/base.log 2>&1; W6_THREADS=1 $PY -I fusion.py base R10x > logs/base_R10x.log 2>&1; echo done > logs/chainA.done ) &
( for s in hlie hctrl hpara; do for i in 0 1 2 3 4 5 6 7 8 9; do W6_THREADS=1 $PY -I fusion.py $s $i >> logs/stress.log 2>&1; done; done; echo done > logs/chainB.done ) &
wait
