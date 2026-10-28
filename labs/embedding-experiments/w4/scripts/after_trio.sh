#!/bin/bash
cd /tmp/veridyct-emb/w4
while ! grep -q "TRIO DONE" logs/sweep.log; do sleep 3; done
echo "=== $(date +%H:%M:%S) speed recheck" >> logs/sweep.log
/tmp/veridyct-bench/.venv/bin/python scripts/speed_recheck.py > logs/speed_recheck.log 2>&1
echo "RECHECK FINISHED $(date +%H:%M:%S)" >> logs/sweep.log
