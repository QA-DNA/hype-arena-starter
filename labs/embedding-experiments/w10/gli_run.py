"""w10: GLiClass single-pass zero-shot attribute mapping (nli_attr) + rows/s with 14 labels (speed). Own venv.
Usage: .venv/bin/python -I gli_run.py <gliclass-edge|gliclass-modern-base>"""
import sys, os, time, random
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
try: torch.set_num_interop_threads(1)
except Exception: pass
import numpy as np
from transformers import AutoTokenizer
from gliclass import GLiClassModel, ZeroShotClassificationPipeline
from huggingface_hub import snapshot_download

KEYS = {'gliclass-edge': 'knowledgator/gliclass-edge-v3.0', 'gliclass-modern-base': 'knowledgator/gliclass-modern-base-v3.0'}
W = 'w10'; key_name = sys.argv[1]; repo = KEYS[key_name]
smoke = '--smoke' in sys.argv; speed_only = '--speed-only' in sys.argv; no_hyp = '--no-hyp' in sys.argv
writer = H.ResultWriter(H.results_path(W) if not smoke else '/tmp/veridyct-emb/w10/smoke.jsonl')
log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)
path = snapshot_download(repo, allow_patterns=['*.json', '*.safetensors', '*.py', '*.model', '*.txt'])
model = GLiClassModel.from_pretrained(path).eval()
tok = AutoTokenizer.from_pretrained(path, add_prefix_space=True)
pipe = ZeroShotClassificationPipeline(model, tok, classification_type='multi-label', device='cpu', progress_bar=False, max_classes=64, max_length=512)
params_m = sum(p.numel() for p in model.parameters()) / 1e6
disk_mb = sum(os.path.getsize(os.path.realpath(os.path.join(path, f))) for f in os.listdir(path) if f.endswith('.safetensors')) / 2**20
log(f'{repo}: params {params_m:.1f}M disk {disk_mb:.1f}MB arch {model.config.architecture_type}')
base = dict(params_m=params_m, disk_mb=disk_mb)
rows, lex = H.load(); sf = H.single_fact_rows(rows)
if smoke: sf = sf[:24]; rows = rows[:64]

def scores(texts, labels, bs=32):
    """-> list of {label: score}, original order; texts sorted longest first; labels: one list (shared) or one list per text."""
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]), reverse=True)
    t = [texts[i] for i in order]; l = labels if isinstance(labels[0], str) else [labels[i] for i in order]
    res = pipe(t, l, threshold=0.0, batch_size=bs, return_hierarchical=True)
    out = [None] * len(texts)
    for k, i in enumerate(order): out[i] = res[k]
    return out

# sanity (GLiClass is not an NLI model: one price-vs-others check in place of the 3 NLI pairs)
s = scores(['Pixel 10 costs €799.'], ['price', 'colour', 'storage'])[0]
note = 'sanity (Pixel 10 costs €799. vs price/colour/storage): ' + ', '.join(f'{k}={v:.3f}' for k, v in s.items()) + (' OK' if max(s, key=s.get) == 'price' else ' MISMATCH')
log(note)

def run_attr(ids, label_fn, variant):
    texts = [sf[i]['text'] for i in ids]
    cands = [H.candidates(lex, sf[i]['facts'][0]['subject']) for i in ids]
    lab = [[label_fn(sf[i]['facts'][0]['subject'], a) for a in c] for i, c in zip(ids, cands)]
    t0 = time.perf_counter(); sc = scores(texts, lab); el = time.perf_counter() - t0
    pred, ties = [], 0
    for c, lb, s_ in zip(cands, lab, sc):
        v = np.array([s_[x] for x in lb]); ties += int((v == v.max()).sum() > 1); pred.append(c[int(v.argmax())])
    y = [sf[i]['facts'][0]['attribute'] for i in ids]
    return H.attr_metrics(y, pred, np.zeros(len(ids), int)), el, ties, pred

rng = random.Random(0); sample_ids = sorted(rng.sample(range(len(sf)), 400)) if not smoke else list(range(12))
VARIANTS = [('labels=attr words', lambda subj, a: H.attr_words(a)),
            ('labels=hypothesis "This sentence states the {attr} of {subject}."', lambda subj, a: f'This sentence states the {H.attr_words(a)} of {subj}.')]
for vname, fn in ([] if speed_only else VARIANTS[:1] if no_hyp else VARIANTS):
    m, el, ties, pred = run_attr(list(range(len(sf))), fn, vname)
    pos = {i: p for i, p in enumerate(pred)}
    ms = H.attr_metrics([sf[i]['facts'][0]['attribute'] for i in sample_ids], [pos[i] for i in sample_ids], np.zeros(len(sample_ids), int))
    nl = np.mean([len(H.candidates(lex, r['facts'][0]['subject'])) for r in sf])
    log(f'attr {vname}: full acc {m["acc_all"]:.3f} (n {len(sf)}, {len(sf) / el:.1f} rows/s, mean {nl:.1f} labels, ties {ties}); sample400 acc {ms["acc_all"]:.3f}')
    nt = f'single pass per row against all gold-subject candidate labels (mean {nl:.1f}); multi-label sigmoid scores, argmax (ties {ties}); train_counts zero; {len(sf) / el:.1f} rows/s at 2 threads bs32; ' + note
    writer.add(W, repo, 'nli_attr', f'full1467 {vname}', m, n=len(sf), notes=nt, rows_per_s=len(sf) / el, **base)
    writer.add(W, repo, 'nli_attr', f'sample400 {vname}', ms, n=len(sample_ids), notes='seeded random.Random(0) 400-row subset of the full run (same rows as the NLI models); ' + nt, rows_per_s=len(sf) / el, **base)

# speed: rows/s with 14 labels (fixed shared list), all practice rows (texts), bs 32, longest first, 1 warm-up batch
labels14 = list(lex['subjects']['Hooly Chrome']['attributes'])[:14]; labels14 = [H.attr_words(a) for a in labels14]; assert len(labels14) == 14
texts = [r['text'] for r in rows]
order = sorted(range(len(texts)), key=lambda i: len(texts[i]), reverse=True); t = [texts[i] for i in order]
pipe(t[:32], labels14, threshold=0.0, batch_size=32)  # warm-up
t0 = time.perf_counter(); pipe(t, labels14, threshold=0.0, batch_size=32); wall = time.perf_counter() - t0
rps = len(t) / wall; la = os.getloadavg()[0]
log(f'speed: {rps:.1f} rows/s with 14 labels ({len(t)} rows, bs 32, load {la:.2f})')
writer.add(W, repo, 'speed', 'rows/s 14 labels bs32 maxlen512', {'rows_per_s': rps, 'wall_s': wall, 'est_sec_20k_rows_x86': 20000 / rps * 2.0, 'bs': 32, 'labels': 14},
           n=len(t), notes=f'all {len(t)} practice rows, one shared list of 14 attr-word labels, 2 threads, tokenization included, 1 warm-up batch, load avg {la:.2f} (shared machine, noisy); ' + note,
           rows_per_s=rps, pairs_per_s=rps, **base)
log('DONE', key_name)
