"""w10 extras: alternative NLI hypothesis templates for nli_attr (sample400, same seeded rows as the main run).
Usage: python -I attr_variants.py <key>"""
import inspect, sys, os, time, random
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import numpy as np
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from huggingface_hub import snapshot_download
KEYS = {'finecat-xxs': 'dleemiller/finecat-nli-xxs', 'finecat-xs': 'dleemiller/finecat-nli-xs', 'finecat-s': 'dleemiller/finecat-nli-s',
        'finecat-v2-m': 'dleemiller/finecat-nli-v2-m', 'finecat-ultra-m': 'dleemiller/finecat-nli-ultra-m',
        'modernbert-nli': 'tasksource/ModernBERT-base-nli', 'albert-vitaminc': 'tals/albert-base-vitaminc-mnli'}
key_name = sys.argv[1]; repo = KEYS[key_name]; W = 'w10'
TEMPLATES = {'T2 no-subject "This sentence states the {attr}."': lambda s, a: f'This sentence states the {a}.',
             'T3 no-subject "This sentence is about the {attr}."': lambda s, a: f'This sentence is about the {a}.',
             'T4 "The {attr} of {subject} is given."': lambda s, a: f'The {a} of {s} is given.'}
log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)
path = snapshot_download(repo, allow_patterns=['*.json', '*.safetensors', '*.py', '*.model', '*.txt'])
tok = AutoTokenizer.from_pretrained(path, trust_remote_code=key_name == 'finecat-ultra-m')
model = AutoModelForSequenceClassification.from_pretrained(path, trust_remote_code=key_name == 'finecat-ultra-m').eval()
id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
if all(v.startswith('label_') for v in id2label.values()): IDX = {'E': 0, 'N': 1, 'C': 2}
else: IDX = {('E' if v.startswith(('entail', 'support')) else 'C' if v.startswith(('contra', 'refute')) else 'N'): i for i, v in id2label.items()}
params_m = sum(p.numel() for p in model.parameters()) / 1e6
# transformers 5.x AutoTokenizer (ALBERT) omits token_type_ids for pairs unless asked; BERT-style models need them, ModernBERT does not take them
USE_TTI = 'token_type_ids' in inspect.signature(model.forward).parameters and getattr(model.config, 'type_vocab_size', 0) > 1
TTI = dict(return_token_type_ids=True) if USE_TTI else {}
disk_mb = sum(os.path.getsize(os.path.realpath(os.path.join(path, f))) for f in os.listdir(path) if f.endswith('.safetensors')) / 2**20
writer = H.ResultWriter(H.results_path(W))

@torch.inference_mode()
def pe(pairs, bs=32, max_len=128):
    order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]), reverse=True)
    out = np.zeros(len(pairs), np.float32)
    for s in range(0, len(order), bs):
        b = order[s:s + bs]
        enc = tok([pairs[i][0] for i in b], [pairs[i][1] for i in b], truncation=True, max_length=max_len, padding=True, return_tensors='pt', **TTI)
        out[b] = torch.softmax(model(**enc).logits.float(), -1)[:, IDX['E']].numpy()
    return out

rows, lex = H.load(); sf = H.single_fact_rows(rows)
ids = sorted(random.Random(0).sample(range(len(sf)), 400))
only = [a.split('=')[1] for a in sys.argv if a.startswith('--only=')]
for vname, fn in TEMPLATES.items():
    if only and not vname.startswith(only[0]): continue
    pairs, owner = [], []
    for n_, i in enumerate(ids):
        r = sf[i]; subj = r['facts'][0]['subject']
        for a in H.candidates(lex, subj):
            pairs.append((r['text'], fn(subj, H.attr_words(a)))); owner.append((n_, a))
    t0 = time.time(); p = pe(pairs); el = time.time() - t0
    best = {}
    for k, (n_, a) in enumerate(owner):
        if n_ not in best or p[k] > best[n_][0]: best[n_] = (p[k], a)
    m = H.attr_metrics([sf[i]['facts'][0]['attribute'] for i in ids], [best[n_][1] for n_ in range(len(ids))], np.zeros(len(ids), int))
    log(f'{key_name} {vname}: acc {m["acc_all"]:.3f} ({len(pairs)} pairs, {el:.0f}s)')
    writer.add(W, repo, 'nli_attr', f'sample400 {vname}', m, n=400, notes='extra hypothesis template; seeded random.Random(0) 400-row sample; gold-subject candidates; p_entail argmax', params_m=params_m, disk_mb=disk_mb, pairs_per_s=len(pairs) / el)
log('DONE attr_variants', key_name)
