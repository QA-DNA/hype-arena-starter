"""Sequential driver: one subprocess per model, per-model timeout, global deadline 18:50 local."""
import subprocess, sys, time, datetime
sys.path.insert(0, '/tmp/veridyct-emb/w1')
from models import MODELS
order = [m for m in MODELS if not MODELS[m]['trc']] + [m for m in MODELS if MODELS[m]['trc']]
only = sys.argv[1:]
for m in (only or order):
    t = time.time()
    log = '/tmp/veridyct-emb/w1/log_' + m.replace('/', '__') + '.txt'
    with open(log, 'w') as f:
        try:
            r = subprocess.run(['/tmp/veridyct-bench/.venv/bin/python', '-I', '/tmp/veridyct-emb/w1/bench.py', m], stdout=f, stderr=subprocess.STDOUT, timeout=900)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = 'TIMEOUT'
    print(f'{datetime.datetime.now():%H:%M:%S} {m} rc={rc} {time.time() - t:.0f}s', flush=True)
print('ALL DONE', flush=True)
