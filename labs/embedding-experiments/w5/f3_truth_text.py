"""F3: fine-tune an encoder as a 3-class (true/false/unsure) classifier on TEXT ONLY, class-weighted CE
(weight = n_majority / n_class, capped at 5x, per training fold), page folds over ALL rows.
Control: frozen sentence embeddings + harness LR probes (run_probe_three / run_probe_false).
Usage: python -I f3_truth_text.py MODEL. Saves out-of-fold softmax to out/f3_oof_<model>.npy (LABELS order)."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(4)
import torch; torch.set_num_threads(4)
import os, shutil, time, logging
import numpy as np
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup
from sentence_transformers import SentenceTransformer

logging.getLogger('transformers').setLevel(logging.ERROR)
MODEL = sys.argv[1]; SHORT = MODEL.split('/')[-1]
EPOCHS, BS, LR, THREADS, CAP = 3, 32, 5e-5, 4, 5.0
W = H.ResultWriter(H.results_path('w5'))
rows, lex = H.load()
texts = [r['text'] for r in rows]
y = np.array([H.LABELS.index(r['label']) for r in rows])
yf = (y == 1).astype(int)
F = H.page_folds(rows)
tok = AutoTokenizer.from_pretrained(MODEL)

# control: frozen embeddings + the harness probes
st = SentenceTransformer(MODEL, device='cpu')
X = st.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True); del st
m3, _ = H.run_probe_three(X, rows, F); mb_, _ = H.run_probe_false(X, rows, F)
for part, mm in (('three', m3), ('false', mb_)):
    W.add('w5', SHORT, 'finetune_truth_text', f'frozen_probe:{part}', mm, n=len(rows),
          notes='control: frozen embeddings + harness LR(balanced, C=1) probes; page_folds(rows)')
print('frozen probe: false auc %.3f ap %.3f | arena_best %.3f macro_f1 %.3f' % (mb_['auc'], mb_['ap'], m3['arena_best'], m3['macro_f1']), flush=True)

P, train_s, steps = np.zeros((len(rows), 3)), 0.0, 0
for k, (tr, te) in enumerate(F):
    torch.manual_seed(k); g = torch.Generator().manual_seed(k)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL, num_labels=3)
    cnt = np.bincount(y[tr], minlength=3)
    w = torch.tensor(np.minimum(cnt.max() / np.maximum(cnt, 1), CAP), dtype=torch.float32)
    lossf = torch.nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    nb = (len(tr) + BS - 1) // BS
    sch = get_linear_schedule_with_warmup(opt, int(0.1 * nb * EPOCHS), nb * EPOCHS)
    t0 = time.perf_counter(); model.train()
    for ep in range(EPOCHS):
        perm = torch.randperm(len(tr), generator=g).numpy()
        for b in range(nb):
            ids = tr[perm[b * BS:(b + 1) * BS]]
            enc = tok([texts[i] for i in ids], padding=True, truncation=True, max_length=96, return_tensors='pt')
            loss = lossf(model(**enc).logits, torch.as_tensor(y[ids]))
            loss.backward(); opt.step(); sch.step(); opt.zero_grad(); steps += 1
    dt = time.perf_counter() - t0; train_s += dt
    model.eval()
    with torch.no_grad():
        for b in range(0, len(te), 64):
            ids = te[b:b + 64]
            enc = tok([texts[i] for i in ids], padding=True, truncation=True, max_length=96, return_tensors='pt')
            P[ids] = torch.softmax(model(**enc).logits, -1).numpy()
    print(f'fold {k}: train {dt:.0f}s weights {w.numpy().round(2)} last loss {loss.item():.3f} '
          f'fold false auc {H.binary_metrics(yf[te], P[te, 1])["auc"]:.3f}', flush=True)

np.save(f'/tmp/veridyct-emb/w5/out/f3_oof_{SHORT}.npy', P)
m3, mb_ = H.three_class_metrics([r['label'] for r in rows], P), H.binary_metrics(yf, P[:, 1])
d = f'/tmp/veridyct-emb/w5/models/f3_{SHORT}'; shutil.rmtree(d, ignore_errors=True); model.save_pretrained(d); tok.save_pretrained(d)
mb = round(sum(os.path.getsize(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs) / 1e6, 1)
params_m = round(sum(p.numel() for p in model.parameters()) / 1e6, 2)
torch.set_num_threads(2); H.set_threads(2)
def fwd(b):
    with torch.no_grad(): model(**tok(b, padding=True, truncation=True, max_length=96, return_tensors='pt'))
s = H.encode_speed(fwd, texts)
for part, mm in (('three', m3), ('false', mb_)):
  W.add('w5', SHORT, 'finetune_truth_text', f'ce_weighted_cap5:{part}', mm, n=len(rows), params_m=params_m,
      disk_mb=mb, train_s=round(train_s, 1), sents_per_s=round(s['sentences_per_s'], 1),
      notes=f'epochs={EPOCHS}; train_s={train_s:.0f} (5 folds); steps={steps}; threads={THREADS} (speed at 2); bs={BS}; '
            f'lr={LR}; warmup=0.1; wd=0.01; class weights n_max/n_c capped {CAP}; raw softmax (no calibration); page_folds(rows)')
print('fine-tuned: false', {k: round(v, 3) for k, v in mb_.items() if isinstance(v, float)}, flush=True)
print('fine-tuned: three', {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m3.items()}, flush=True)
print('speed', s, flush=True)
