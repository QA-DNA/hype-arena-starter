"""w10 extras: reverse direction (hypothesis->premise) for nli_conflict and nli_anchor, symmetrised scores.
Needs the forward probs saved by nli_run.py. Usage: python -I nli_extra.py <key>"""
import inspect, sys, os, time
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
base = dict(params_m=params_m, disk_mb=disk_mb); writer = H.ResultWriter(H.results_path(W))

@torch.inference_mode()
def probs(pairs, bs=32, max_len=128):
    order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]), reverse=True)
    out = np.zeros((len(pairs), 3), np.float32)
    for s in range(0, len(order), bs):
        b = order[s:s + bs]
        enc = tok([pairs[i][0] for i in b], [pairs[i][1] for i in b], truncation=True, max_length=max_len, padding=True, return_tensors='pt', **TTI)
        out[b] = torch.softmax(model(**enc).logits.float(), -1).numpy()
    return out

rows, lex = H.load(); sf = H.single_fact_rows(rows)
# ---- conflict
PR = H.same_key_pairs(rows); fwd = np.load(f'/tmp/veridyct-emb/w10/probs_conflict_{key_name}.npy')
t0 = time.time(); rev = probs([(rows[j]['text'], rows[i]['text']) for i, j, _ in PR]); log(f'conflict reverse {len(PR)} pairs {time.time() - t0:.0f}s')
y = np.array([0 if same else 1 for _, _, same in PR]); kinds = np.array([rows[i]['facts'][0]['value']['kind'] for i, _, _ in PR])
pc_f, pc_r = fwd[:, IDX['C']], rev[:, IDX['C']]
for variant, s in (('p_contra(j->i) reverse only', pc_r), ('p_contra mean(i->j, j->i)', (pc_f + pc_r) / 2), ('p_contra max(i->j, j->i)', np.maximum(pc_f, pc_r))):
    m = H.binary_metrics(y, s); m['auc_by_kind'] = {k: dict(auc=H.binary_metrics(y[kinds == k], s[kinds == k])['auc'], n=int((kinds == k).sum()), pos=int(y[kinds == k].sum())) for k in sorted(set(kinds))}
    log(f'conflict {variant}: auc {m["auc"]:.3f} ap {m["ap"]:.3f} f1max {m["f1_max"]:.3f}')
    writer.add(W, repo, 'nli_conflict', variant, m, n=len(PR), notes='extra: both directions of the same_key_pairs; target = values differ', **base)
# ---- anchor
A = H.nearest_anchors(rows, k=2); Q = [r for r in sf if r['label'] in ('true', 'false') and A[r['idx']]]
pairs_f = [(rows[a['idx']]['text'], r['text']) for r in Q for a in A[r['idx']]]
fa = np.load(f'/tmp/veridyct-emb/w10/probs_anchor_{key_name}.npy'); assert len(fa) == len(pairs_f)
t0 = time.time(); ra = probs([(b, a) for a, b in pairs_f]); log(f'anchor reverse {len(pairs_f)} pairs {time.time() - t0:.0f}s')
own = np.array([qi for qi, r in enumerate(Q) for _ in A[r['idx']]]); first = {}
for k, qi in enumerate(own): first.setdefault(qi, k)
yf = np.array([r['label'] == 'false' for r in Q], int); near_same = np.array([A[r['idx']][0]['same_value'] for r in Q])
def agg(pc, pe):
    cm = np.array([pc[own == q].max() for q in range(len(Q))]); em = np.array([pe[own == q].max() for q in range(len(Q))]); cn = np.array([pc[first[q]] for q in range(len(Q))])
    return cm, em, cn
cf, ef, nf = agg(fa[:, IDX['C']], fa[:, IDX['E']]); cr, er, nr = agg(ra[:, IDX['C']], ra[:, IDX['E']])
for variant, s in (('p_contra_max reverse (premise=row, hyp=anchor)', cr), ('p_contra_max mean(fwd, rev)', (cf + cr) / 2), ('p_contra_nearest mean(fwd, rev)', (nf + nr) / 2),
                   ('net: p_contra_max - p_entail_max (fwd)', cf - ef), ('1-p_entail_max mean(fwd, rev)', 1 - (ef + er) / 2)):
    m = H.binary_metrics(yf, s)
    for nm, mask in (('diff', ~near_same), ('same', near_same)):
        ms = H.binary_metrics(yf[mask], s[mask]); m.update({f'auc_nearest_{nm}': ms['auc'], f'n_nearest_{nm}': ms['n'], f'pos_nearest_{nm}': ms['pos']})
    log(f'anchor {variant}: auc {m["auc"]:.3f} ap {m["ap"]:.3f} f1max {m["f1_max"]:.3f} | diff {m["auc_nearest_diff"]:.3f} same {m["auc_nearest_same"]:.3f}')
    writer.add(W, repo, 'nli_anchor', variant, m, n=len(Q), notes='extra: reverse/symmetrised/net scores from the same anchor pairs', **base)
log('DONE extra', key_name)
