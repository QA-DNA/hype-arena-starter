"""w10: uniform speed re-check of all NLI models in one process, back to back (comparable machine load): 800 conflict pairs, bs 32, length-sorted,
tokenization included, 1 warm-up batch, 2 threads. Usage: python -I speed_recheck.py [key ...]"""
import inspect, sys, os, time, random
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import numpy as np
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from huggingface_hub import snapshot_download
KEYS = {'finecat-xxs': 'dleemiller/finecat-nli-xxs', 'finecat-xs': 'dleemiller/finecat-nli-xs', 'finecat-s': 'dleemiller/finecat-nli-s',
        'albert-vitaminc': 'tals/albert-base-vitaminc-mnli', 'finecat-v2-m': 'dleemiller/finecat-nli-v2-m',
        'modernbert-nli': 'tasksource/ModernBERT-base-nli', 'finecat-ultra-m': 'dleemiller/finecat-nli-ultra-m'}
keys = sys.argv[1:] or list(KEYS)
rows, lex = H.load(); PR = H.same_key_pairs(rows)
sel = sorted(random.Random(0).sample(range(len(PR)), 2000))[:800]
pairs = [(rows[PR[k][0]]['text'], rows[PR[k][1]]['text']) for k in sel]
writer = H.ResultWriter(H.results_path('w10')); log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)
for key in keys:
    repo = KEYS[key]; path = snapshot_download(repo, allow_patterns=['*.json', '*.safetensors', '*.py', '*.model', '*.txt'])
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=key == 'finecat-ultra-m')
    model = AutoModelForSequenceClassification.from_pretrained(path, trust_remote_code=key == 'finecat-ultra-m').eval()
    tti = dict(return_token_type_ids=True) if 'token_type_ids' in inspect.signature(model.forward).parameters and getattr(model.config, 'type_vocab_size', 0) > 1 else {}
    order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]), reverse=True); batches = [order[i:i + 32] for i in range(0, len(order), 32)]
    def run(b):
        with torch.inference_mode():
            enc = tok([pairs[i][0] for i in b], [pairs[i][1] for i in b], truncation=True, max_length=128, padding=True, return_tensors='pt', **tti)
            return model(**enc).logits
    run(batches[0]); la0 = os.getloadavg()[0]; t0 = time.perf_counter()
    for b in batches: run(b)
    wall = time.perf_counter() - t0; pps = len(pairs) / wall
    params_m = sum(p.numel() for p in model.parameters()) / 1e6
    log(f'{key}: {pps:.1f} pairs/s ({len(pairs)} pairs, load {la0:.2f}->{os.getloadavg()[0]:.2f})')
    writer.add('w10', repo, 'speed', 'recheck 800 pairs back-to-back', {'pairs_per_s': pps, 'wall_s': wall, 'est_sec_20k_pairs_x86': 20000 / pps * 2.0, 'bs': 32}, n=len(pairs),
               notes=f'uniform re-check, all NLI models back to back in one process, 2 threads, bs 32, tokenization included, load avg {la0:.2f} before / {os.getloadavg()[0]:.2f} after', params_m=params_m, pairs_per_s=pps)
    del model, tok
log('DONE recheck')
