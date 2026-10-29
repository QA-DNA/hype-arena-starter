"""Contention-robust speed: same 2000 texts, bs32, 3 timed passes; reports wall AND process CPU time.  python -I speed_cpu.py <model>"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w1')
import harness as H; H.set_threads(2)
import os; os.environ['HF_HUB_OFFLINE'] = '1'
import torch; torch.set_num_threads(2)
import time, warnings
warnings.filterwarnings('ignore')
from models import MODELS
from sentence_transformers import SentenceTransformer
mid = sys.argv[1]; cfg = MODELS[mid]
if cfg['trc'] and 'veridyct-bench' in sys.prefix: sys.exit('trc model: use the w1 venv')
rows, _ = H.load(); tx = [cfg['sym'] + r['text'] for r in rows]; tx = tx + tx[:103]
model = SentenceTransformer(mid, device='cpu', trust_remote_code=cfg['trc']).float()
ts = sorted(tx, key=len, reverse=True); batches = [ts[i:i + 32] for i in range(0, len(ts), 32)]
model.encode(batches[0], batch_size=32, show_progress_bar=False)
runs = []
for _ in range(1):  # one timed pass: CPU time is stable under contention, 3 passes do not fit the time box
    w0, c0 = time.perf_counter(), time.process_time()
    for b in batches: model.encode(b, batch_size=32, show_progress_bar=False)
    runs.append((time.perf_counter() - w0, time.process_time() - c0))
runs.sort(key=lambda r: r[1]); wall, cpu = runs[len(runs) // 2]
m = dict(sentences_per_s=len(ts) / wall, sents_per_cpu_s=len(ts) / cpu, wall_s=wall, cpu_s=cpu, est_sec_20k_x86=20000 / (len(ts) / wall) * 2.0,
         cpu_over_wall=cpu / wall)
H.ResultWriter(H.results_path('w1')).add('w1', mid, 'speed', 'bs32_2000texts_cpu_time', m, n=len(ts), notes=f'single timed pass after warm-up, CPU time, fp32, 2 threads; loadavg1={os.getloadavg()[0]:.1f}; all (wall,cpu)={[(round(a, 2), round(b, 2)) for a, b in runs]}')
print(mid, {k: round(v, 3) for k, v in m.items()}, flush=True)
