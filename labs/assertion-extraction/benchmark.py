"""Development-only CPU scaling check; repeated practice is not unseen evaluation."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--binary', required=True)
p.add_argument('--rows', type=int, default=20000)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / 'labs/assertion-extraction/outputs'
out.mkdir(exist_ok=True)
practice = list(csv.DictReader((root / 'data/practice.csv').open()))
input_path = out / 'scaling-input.csv'
with input_path.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'text', 'date', 'label'])
    w.writeheader()
    for i in range(a.rows):
        r = practice[i % len(practice)]
        w.writerow(dict(id=f'bench-{i}', text=r['text'], date=r['date'], label=''))
cpus = sorted(os.sched_getaffinity(0))[:2]
command = [str(Path(a.binary).resolve()), 'parse', '--index', str(out / 'lexicon-index.json'),
           '--input', str(input_path), '--output', str(out / 'scaling-output.csv')]
start = time.monotonic()
run = subprocess.run(command, capture_output=True, text=True,
                     preexec_fn=lambda: os.sched_setaffinity(0, cpus), check=True)
result = dict(rows=a.rows, dataset='repeated practice, unique IDs, no forms or labels',
              elapsed_seconds=time.monotonic()-start,
              peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
              cpu_affinity=cpus, parser_threads=1, profile='release',
              base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              working_tree_changes=True,
              binary_sha256=hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),
              input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
              cpu=next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),
              stderr=run.stderr.strip())
(out / 'benchmark.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
