"""F4: cross-encoder on (anchor text, row text) -> row is false. Anchors = H.nearest_anchors(rows, k=2) (TRUE rows on
other pages sharing the key). Train: nearest before + nearest after (up to 2 pairs per row, the row's label);
test: score = max over all the row's nearest anchors. Single-fact rows with >= 1 anchor, page_folds(rows) filtered
(so the out-of-fold scores line up with F3's). Head re-initialised to 1 logit; BCE with pos_weight = n_neg/n_pos capped 5.
Usage: python -I f4_truth_pair.py [strict]   strict = anchors only from TRAINING-fold pages, for train AND test rows."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(4)
import torch; torch.set_num_threads(4)
import os, time, logging
import numpy as np
from datasets import Dataset
from sentence_transformers import CrossEncoder, CrossEncoderTrainer, CrossEncoderTrainingArguments, SentenceTransformer
from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss

logging.getLogger('transformers').setLevel(logging.ERROR)
MODEL = 'cross-encoder/ms-marco-MiniLM-L-6-v2'; SHORT = MODEL.split('/')[-1]
STRICT = 'strict' in sys.argv[1:]
EPOCHS, BS, LR, THREADS = 3, 32, 2e-5, 4
W = H.ResultWriter(H.results_path('w5'))
rows, lex = H.load()
assert all(r['idx'] == i for i, r in enumerate(rows))
A = H.nearest_anchors(rows, k=2)
page = np.array([r['page'] for r in rows])
yf = np.array([r['label'] == 'false' for r in rows], int)
elig = np.array([len(r['facts']) == 1 and len(A[i]) > 0 for i, r in enumerate(rows)])
F = H.page_folds(rows)
score, train_s, steps, npairs = np.full(len(rows), np.nan), 0.0, 0, 0
sig = lambda z: 1 / (1 + np.exp(-z))

for k, (tr, te) in enumerate(F):
    ok_pages = set(page[tr].tolist()) if STRICT else None
    anc = lambda i: [x for x in A[i] if ok_pages is None or page[x['idx']] in ok_pages]
    a, b, lab = [], [], []
    for i in tr:
        if not elig[i]: continue
        L = anc(i)
        for x in [x for x in L if x['days'] <= 0][:1] + [x for x in L if x['days'] > 0][:1]:
            a.append(rows[x['idx']]['text']); b.append(rows[i]['text']); lab.append(float(yf[i]))
    torch.manual_seed(k)
    ce = CrossEncoder(MODEL, num_labels=1, device='cpu')
    torch.nn.init.normal_(ce.model.classifier.weight, std=0.02); torch.nn.init.zeros_(ce.model.classifier.bias)
    npos = sum(lab); pw = min(5.0, (len(lab) - npos) / max(npos, 1))
    args = CrossEncoderTrainingArguments(
        output_dir=f'/tmp/veridyct-emb/w5/out/f4', num_train_epochs=EPOCHS, per_device_train_batch_size=BS,
        learning_rate=LR, warmup_ratio=0.1, save_strategy='no', report_to='none', use_cpu=True, seed=k,
        logging_steps=1000, disable_tqdm=True, dataloader_num_workers=0)
    t = CrossEncoderTrainer(model=ce, args=args, train_dataset=Dataset.from_dict({'anchor': a, 'row': b, 'label': lab}),
                            loss=BinaryCrossEntropyLoss(ce, pos_weight=torch.tensor(pw)))
    t0 = time.perf_counter(); out = t.train(); dt = time.perf_counter() - t0
    train_s += dt; steps += out.global_step; npairs += len(a)
    pairs, own = [], []
    for i in te:
        if elig[i] and anc(i):
            P_ = [(rows[x['idx']]['text'], rows[i]['text']) for x in anc(i)]
            pairs += P_; own.append((i, len(P_)))
    s, o = sig(ce.predict(pairs, batch_size=64, convert_to_numpy=True, show_progress_bar=False)), 0
    for i, n_ in own:
        score[i] = s[o:o + n_].max(); o += n_
    ev = [i for i, _ in own]
    print(f'fold {k}: pairs {len(a)} pos_weight {pw:.2f} train {dt:.0f}s loss {out.training_loss:.3f} '
          f'fold auc {H.binary_metrics(yf[ev], score[ev])["auc"]:.3f} (n={len(ev)})', flush=True)

ev = np.flatnonzero(~np.isnan(score))
m = H.binary_metrics(yf[ev], score[ev])
variant = 'anchor_pair_strict' if STRICT else 'anchor_pair'
params_m = round(sum(p.numel() for p in ce.model.parameters()) / 1e6, 2)
d = f'/tmp/veridyct-emb/w5/models/f4_{SHORT}'; ce.save(d)
mb = round(sum(os.path.getsize(os.path.join(p_, f)) for p_, _, fs in os.walk(d) for f in fs) / 1e6, 1)
torch.set_num_threads(2); H.set_threads(2)
sp = H.encode_speed(lambda b_: ce.predict(b_, batch_size=32, show_progress_bar=False), pairs)
W.add('w5', SHORT, 'finetune_truth_pair', variant, m, n=len(ev), params_m=params_m, disk_mb=mb,
      train_s=round(train_s, 1), pairs_per_s=round(sp['sentences_per_s'], 1),
      notes=f'epochs={EPOCHS}; train_s={train_s:.0f} (5 folds); steps={steps}; train_pairs={npairs} (5 folds); '
            f'threads={THREADS} (speed at 2); bs={BS}; lr={LR}; warmup=0.1; head re-init; pos_weight<=5; '
            f'{len(pairs) / max(len(own), 1):.1f} anchor pairs per test row; '
            f'{"anchors from training-fold pages only" if STRICT else "anchors from any other page (incl. test-fold pages)"}')
print(variant, {k: round(v, 3) for k, v in m.items() if isinstance(v, float)}, flush=True)
print('speed', sp, flush=True)
np.save(f'/tmp/veridyct-emb/w5/out/f4_scores_{variant}.npy', score)

if not STRICT:  # controls on the SAME rows: F3 text-only fine-tuned OOF, frozen bge-small 1 - max cos(anchor, row)
    f3 = '/tmp/veridyct-emb/w5/out/f3_oof_bge-small-en-v1.5.npy'
    if os.path.exists(f3):
        c = H.binary_metrics(yf[ev], np.load(f3)[ev, 1])
        W.add('w5', 'bge-small-en-v1.5', 'finetune_truth_pair', 'control_f3_text_only_same_rows', c, n=len(ev),
              notes='F3 fine-tuned text-only OOF p(false) restricted to the F4 rows (same page folds)')
        print('control F3 same rows', {k: round(v, 3) for k, v in c.items() if isinstance(v, float)}, flush=True)
    st = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
    X = st.encode([r['text'] for r in rows], batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
    cs = np.array([1 - max(float(X[x['idx']] @ X[i]) for x in A[i]) for i in ev])
    c = H.binary_metrics(yf[ev], cs)
    W.add('w5', 'bge-small-en-v1.5', 'finetune_truth_pair', 'control_frozen_cos', c, n=len(ev),
          notes='no training: score = 1 - max cosine(anchor, row), frozen bge-small, same anchors and rows')
    print('control frozen cos', {k: round(v, 3) for k, v in c.items() if isinstance(v, float)}, flush=True)
