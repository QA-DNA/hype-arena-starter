"""w10: NLI cross-encoders on VERIDYCT sentence pairs. Usage: python -I nli_run.py <key> [--no-attr-full]
Tasks: sanity, nli_conflict (+ speed on a seeded 2000-pair subset of the conflict pairs), nli_anchor, nli_attr."""
import inspect, sys, os, time, json, random
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'          # private cache; set BEFORE H.set_threads (it uses setdefault)
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
try: torch.set_num_interop_threads(1)
except Exception: pass
import numpy as np
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from huggingface_hub import snapshot_download

KEYS = {'finecat-xxs': 'dleemiller/finecat-nli-xxs', 'finecat-xs': 'dleemiller/finecat-nli-xs', 'finecat-s': 'dleemiller/finecat-nli-s',
        'finecat-v2-m': 'dleemiller/finecat-nli-v2-m', 'finecat-ultra-m': 'dleemiller/finecat-nli-ultra-m',
        'modernbert-nli': 'tasksource/ModernBERT-base-nli', 'albert-vitaminc': 'tals/albert-base-vitaminc-mnli'}
TRUST = {'finecat-ultra-m'}
W = 'w10'
key_name = sys.argv[1]; repo = KEYS[key_name]
SWAP = '--swap' in sys.argv            # premise/hypothesis order swapped (only for the VitaminC order check)
only = [a.split('=')[1] for a in sys.argv if a.startswith('--only=')]
writer = H.ResultWriter(H.results_path(W))
log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)

path = snapshot_download(repo, allow_patterns=['*.json', '*.safetensors', '*.py', '*.model', '*.txt'])
tok = AutoTokenizer.from_pretrained(path, trust_remote_code=key_name in TRUST)
model = AutoModelForSequenceClassification.from_pretrained(path, trust_remote_code=key_name in TRUST).eval()
id2label = {int(k): v for k, v in model.config.id2label.items()}
IDX = {}
if all(n.lower().startswith('label_') for n in id2label.values()):  # finecat s/xs/xxs: config has LABEL_n; the model card gives E=0 N=1 C=2 (sanity check verifies)
    IDX = {'E': 0, 'N': 1, 'C': 2}; id2label = {0: 'entailment', 1: 'neutral', 2: 'contradiction'}; log0 = 'config id2label is LABEL_n; used card map E0 N1 C2'
else:
    log0 = ''
    for i, n in id2label.items():
        n = n.lower()
        IDX['E' if n.startswith(('entail', 'support')) else 'C' if n.startswith(('contra', 'refute')) else 'N'] = i
assert set(IDX) == {'E', 'N', 'C'}, id2label
params_m = sum(p.numel() for p in model.parameters()) / 1e6
# transformers 5.x AutoTokenizer (ALBERT) omits token_type_ids for pairs unless asked; BERT-style models need them, ModernBERT does not take them
USE_TTI = 'token_type_ids' in inspect.signature(model.forward).parameters and getattr(model.config, 'type_vocab_size', 0) > 1
TTI = dict(return_token_type_ids=True) if USE_TTI else {}
disk_mb = sum(os.path.getsize(os.path.realpath(os.path.join(path, f))) for f in os.listdir(path) if f.endswith('.safetensors')) / 2**20
log(log0); log(f'{repo}: params {params_m:.1f}M disk {disk_mb:.1f}MB id2label {id2label} -> {IDX} swap={SWAP}')
variant_sfx = ' swapped-order' if SWAP else ''

@torch.inference_mode()
def probs(pairs, bs=32, max_len=128, timed=False):
    """softmax probs (n, 3) in the model's own label order, original pair order; length-sorted batches (longest first)."""
    if SWAP: pairs = [(b, a) for a, b in pairs]
    order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]), reverse=True)
    batches = [order[i:i + bs] for i in range(0, len(order), bs)]
    out = np.zeros((len(pairs), 3), np.float32)
    def run(b):
        enc = tok([pairs[i][0] for i in b], [pairs[i][1] for i in b], truncation=True, max_length=max_len, padding=True, return_tensors='pt', **TTI)
        return torch.softmax(model(**enc).logits.float(), -1).numpy()
    if timed: run(batches[0])  # warm-up batch, as H.encode_speed
    t0 = time.perf_counter()
    for b in batches: out[b] = run(b)
    wall = time.perf_counter() - t0
    return (out, wall) if timed else out

def P(p, c): return p[:, IDX[c]]
base = dict(params_m=params_m, disk_mb=disk_mb)
def add(task, variant, metrics, n, notes, **extra): return writer.add(W, repo, task, variant + variant_sfx, metrics, n=n, notes=notes, **{**base, **extra})

rows, lex = H.load(); sf = H.single_fact_rows(rows)
la0 = os.getloadavg()[0]; note = 'sanity not run'; pps = 0.0

# ------------------------------------------------------------------ sanity
if not only or 'sanity' in only:
    s_pairs = [('Pixel 10 costs €799.', 'Pixel 10 costs €799.'), ('Pixel 10 costs €799.', 'Pixel 10 costs €549.'),
               ('Pixel 10 costs €799.', 'Pixel 10 ships in black.')]
    sp = probs(s_pairs); want = ['E', 'C', 'N']; got = []
    for (a, b), p, w in zip(s_pairs, sp, want):
        g = id2label[int(p.argmax())]; got.append(g)
        log(f'sanity {b!r}: {dict((id2label[i], round(float(p[i]), 3)) for i in range(3))} want {w}')
    ok = [IDX[w] == int(p.argmax()) for w, p in zip(want, sp)]
    note = 'sanity (self/549/black): ' + ', '.join(f'{g}({p.max():.3f})' for g, p in zip(got, sp)) + (' ALL OK' if all(ok) else f' MISMATCH {ok}')
    log(note)

# ------------------------------------------------------------------ nli_conflict (+ speed on a seeded 2000-pair subset)
if not only or 'conflict' in only:
    PR = H.same_key_pairs(rows)
    kind = lambda i: rows[i]['facts'][0]['value']['kind']
    pairs = [(rows[i]['text'], rows[j]['text']) for i, j, _ in PR]
    rng = random.Random(0); sel = sorted(rng.sample(range(len(PR)), 2000)); rest = sorted(set(range(len(PR))) - set(sel))
    p_sel, wall = probs([pairs[k] for k in sel], timed=True)
    p_rest = probs([pairs[k] for k in rest]) if rest else np.zeros((0, 3), np.float32)
    PRB = np.zeros((len(PR), 3), np.float32); PRB[sel] = p_sel; PRB[rest] = p_rest
    pps = 2000 / wall
    log(f'speed: {pps:.1f} pairs/s (2000 pairs, bs 32, length-sorted, tokenization included, load {la0:.2f}->{os.getloadavg()[0]:.2f})')
    add('speed', 'pairs bs32 len<=128 2000 conflict-pairs', {'pairs_per_s': pps, 'wall_s': wall, 'est_sec_20k_pairs_x86': 20000 / pps * 2.0, 'bs': 32},
        2000, f'2 threads, tokenization included, 1 warm-up batch, machine load avg {la0:.2f} before / {os.getloadavg()[0]:.2f} after (shared machine, noisy); ' + note,
        pairs_per_s=pps)
    y_diff = np.array([0 if same else 1 for _, _, same in PR]); kinds = np.array([kind(i) for i, _, _ in PR])
    pc, pe = P(PRB, 'C'), P(PRB, 'E')
    for variant, score in (('p_contra(i->j)', pc), ('1-p_entail(i->j)', 1 - pe)):
        m = H.binary_metrics(y_diff, score)
        per_kind = {}
        for k in sorted(set(kinds)):
            mk = H.binary_metrics(y_diff[kinds == k], score[kinds == k])
            per_kind[k] = dict(auc=mk['auc'], n=mk['n'], pos=mk['pos'])
        m['auc_by_kind'] = per_kind
        log(f'conflict {variant}: auc {m["auc"]:.3f} ap {m["ap"]:.3f} f1max {m["f1_max"]:.3f} | ' + ' '.join(f'{k}:{v["auc"]:.3f}' for k, v in per_kind.items()))
        add('nli_conflict', variant, m, len(PR), 'pairs=H.same_key_pairs(rows) (i->j: premise rows[i], hypothesis rows[j]); target = values differ; premise-hypothesis order i<j by idx; ' + note,
            pairs_per_s=pps)
    np.save(f'/tmp/veridyct-emb/w10/probs_conflict_{key_name}{"_swap" if SWAP else ""}.npy', PRB)

# ------------------------------------------------------------------ nli_anchor
if not only or 'anchor' in only:
    A = H.nearest_anchors(rows, k=2)
    Q = [r for r in sf if r['label'] in ('true', 'false') and A[r['idx']]]
    pairs, owner = [], []
    for qi, r in enumerate(Q):
        for a in A[r['idx']]:
            pairs.append((rows[a['idx']]['text'], r['text'])); owner.append((qi, a['same_value']))
    t0 = time.time(); PB = probs(pairs); log(f'anchor: {len(Q)} rows, {len(pairs)} pairs, {time.time() - t0:.0f}s')
    owner_q = np.array([o[0] for o in owner]); pcm, pem, pcn = np.zeros(len(Q)), np.zeros(len(Q)), np.zeros(len(Q))
    first = {}
    for k, (qi, _) in enumerate(owner): first.setdefault(qi, k)
    for qi in range(len(Q)):
        ks = np.flatnonzero(owner_q == qi)
        pcm[qi], pem[qi], pcn[qi] = P(PB, 'C')[ks].max(), P(PB, 'E')[ks].max(), P(PB, 'C')[first[qi]]
    y_false = np.array([r['label'] == 'false' for r in Q], int)
    near_same = np.array([A[r['idx']][0]['same_value'] for r in Q])
    for variant, score in (('p_contra_max', pcm), ('1-p_entail_max', 1 - pem), ('p_contra_nearest', pcn)):
        m = H.binary_metrics(y_false, score)
        for nm, mask in (('diff', ~near_same), ('same', near_same)):
            ms = H.binary_metrics(y_false[mask], score[mask])
            m.update({f'auc_nearest_{nm}': ms['auc'], f'n_nearest_{nm}': ms['n'], f'pos_nearest_{nm}': ms['pos']})
        log(f'anchor {variant}: auc {m["auc"]:.3f} ap {m["ap"]:.3f} f1max {m["f1_max"]:.3f} | nearest-diff auc {m["auc_nearest_diff"]:.3f} (n {m["n_nearest_diff"]}, pos {m["pos_nearest_diff"]}) same auc {m["auc_nearest_same"]:.3f} (n {m["n_nearest_same"]}, pos {m["pos_nearest_same"]})')
        add('nli_anchor', variant, m, len(Q), f'single-fact true/false rows with >=1 anchor of H.nearest_anchors(k=2); {len(pairs)} pairs, premise=anchor text, hypothesis=row text; label false = positive; score aggregated over anchors (max) or nearest anchor only')
    np.save(f'/tmp/veridyct-emb/w10/probs_anchor_{key_name}{"_swap" if SWAP else ""}.npy', PB)

# ------------------------------------------------------------------ nli_attr (zero-shot, NLI hypothesis per candidate attribute)
if not only or 'attr' in only:
    rng = random.Random(0); sample_ids = sorted(rng.sample(range(len(sf)), 400))
    def run_attr(ids):
        pairs, owner = [], []
        for n_, i in enumerate(ids):
            r = sf[i]; subj = r['facts'][0]['subject']
            for a in H.candidates(lex, subj) or sorted({s['facts'][0]['attribute'] for s in sf}):
                pairs.append((r['text'], f'This sentence states the {H.attr_words(a)} of {subj}.')); owner.append((n_, a))
        t0 = time.time(); PA = probs(pairs); el = time.time() - t0
        best = {}
        for k, (n_, a) in enumerate(owner):
            if n_ not in best or PA[k, IDX['E']] > best[n_][0]: best[n_] = (PA[k, IDX['E']], a)
        pred = [best[n_][1] for n_ in range(len(ids))]
        y = [sf[i]['facts'][0]['attribute'] for i in ids]
        return H.attr_metrics(y, pred, np.zeros(len(ids), int)), len(pairs), el, dict(zip(ids, pred))
    m, npairs, el, pred400 = run_attr(sample_ids)
    log(f'attr sample400: acc {m["acc_all"]:.3f} ({npairs} pairs, {el:.0f}s, {npairs / el:.1f} pairs/s)')
    add('nli_attr', 'sample400 hyp="This sentence states the {attr} of {subject}."', m, 400, f'seeded random.Random(0) sample of 400 of the 1467 single-fact rows; {npairs} pairs; gold-subject candidates; p_entail argmax; train_counts all zero', pairs_per_s=npairs / el)
    if npairs / el >= 50 and pps >= 100 and '--no-attr-full' not in sys.argv:  # time-box: full 1467 rows only for the fast models
        rest_ids = [i for i in range(len(sf)) if i not in set(sample_ids)]
        t0 = time.time(); m2, np2, el2, pred_rest = run_attr(rest_ids)
        allp = {**pred400, **pred_rest}
        y_all = [sf[i]['facts'][0]['attribute'] for i in range(len(sf))]
        mf = H.attr_metrics(y_all, [allp[i] for i in range(len(sf))], np.zeros(len(sf), int))
        log(f'attr full: acc {mf["acc_all"]:.3f} ({time.time() - t0:.0f}s for the remaining 1067 rows)')
        add('nli_attr', 'full1467 hyp="This sentence states the {attr} of {subject}."', mf, len(sf), 'all single-fact rows (model was >= 50 pairs/s on attr and >= 100 pairs/s on conflict); gold-subject candidates; p_entail argmax; train_counts all zero', pairs_per_s=np2 / el2)
log('DONE', key_name)
