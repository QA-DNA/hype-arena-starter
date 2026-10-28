"""F1: contrastive fine-tune of a bi-encoder on (text -> describe(subject, attribute)), MNRL in-batch negatives.
Usage: python -I f1_bi.py MODEL [aug]   (aug = F5: also add 'attr words' alone as an extra positive pair)
Logs finetune_bi_attr (page folds) and finetune_bi_unseen (attribute folds) + base_zeroshot controls + 2-thread speed."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(4)
import torch; torch.set_num_threads(4)
import os, shutil, time, logging
import numpy as np
from datasets import Dataset
from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer, SentenceTransformerTrainingArguments
from sentence_transformers.base.sampler import BatchSamplers
from sentence_transformers.sentence_transformer.losses import MultipleNegativesRankingLoss

logging.getLogger('transformers').setLevel(logging.ERROR)
MODEL, AUG = sys.argv[1], 'aug' in sys.argv[2:]
SHORT = MODEL.split('/')[-1]
EPOCHS, BS, LR, THREADS = 3, 32, 2e-5, 4
W = H.ResultWriter(H.results_path('w5'))
rows, lex = H.load(); sf = H.single_fact_rows(rows)
y = [r['facts'][0]['attribute'] for r in sf]
texts = [r['text'] for r in sf]
FOLDS = {'page': H.page_folds(sf), 'attr': H.attribute_folds(sf)}
TASK = {'page': 'finetune_bi_attr', 'attr': 'finetune_bi_unseen'}
if AUG: FOLDS.pop('page')  # ponytail: F5 asks only about unseen attributes; page folds would double its cost

def oof_pred(model, idx):
    """Restricted argmax over the gold subject's candidate descriptions for rows sf[idx] (harness zeroshot_attr)."""
    E = model.encode([texts[i] for i in idx], batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
    sim = lambda descs: E @ model.encode(descs, batch_size=64, normalize_embeddings=True, convert_to_numpy=True).T
    return H.zeroshot_attr(sim, [sf[i] for i in idx], lex)[1]

def size(model):
    d = f'/tmp/veridyct-emb/w5/models/f1_{SHORT}'
    shutil.rmtree(d, ignore_errors=True); model.save(d)
    mb = sum(os.path.getsize(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs) / 1e6
    return round(sum(p.numel() for p in model.parameters()) / 1e6, 2), round(mb, 1)

if not AUG:  # control: un-tuned base model, same evaluation
    base = SentenceTransformer(MODEL, device='cpu')
    p0 = oof_pred(base, list(range(len(sf))))
    params_m = round(sum(p.numel() for p in base.parameters()) / 1e6, 2)
    for fk, F in FOLDS.items():
        m = H.attr_metrics(y, p0, H.train_counts(sf, F))
        W.add('w5', SHORT, TASK[fk], 'base_zeroshot', m, n=len(sf), notes=f'no training; folds={fk}; threads={THREADS}', params_m=params_m)
        print(fk, 'base', {k: round(v, 3) for k, v in m.items() if k.startswith('acc')}, flush=True)
    del base

variant = 'mnrl_aug' if AUG else 'mnrl'
for fk, F in FOLDS.items():
    pred, train_s, steps = np.empty(len(sf), dtype=object), 0.0, 0
    for k, (tr, te) in enumerate(F):
        torch.manual_seed(k)
        model = SentenceTransformer(MODEL, device='cpu')
        a = [texts[i] for i in tr]; p = [H.describe(sf[i]['facts'][0]['subject'], y[i]) for i in tr]
        if AUG:  # F5: LLM-free augmentation, attribute-name words alone as an extra positive
            a, p = a + [texts[i] for i in tr], p + [H.attr_words(y[i]) for i in tr]
        args = SentenceTransformerTrainingArguments(
            output_dir=f'/tmp/veridyct-emb/w5/out/f1_{SHORT}', num_train_epochs=EPOCHS, per_device_train_batch_size=BS,
            learning_rate=LR, warmup_ratio=0.1, batch_sampler=BatchSamplers.NO_DUPLICATES, save_strategy='no',
            report_to='none', use_cpu=True, seed=k, logging_steps=1000, disable_tqdm=True, dataloader_num_workers=0)
        tr_ = SentenceTransformerTrainer(model=model, args=args, train_dataset=Dataset.from_dict({'anchor': a, 'positive': p}),
                                         loss=MultipleNegativesRankingLoss(model))
        t0 = time.perf_counter(); out = tr_.train(); dt = time.perf_counter() - t0
        train_s += dt; steps += out.global_step
        pred[te] = oof_pred(model, list(te))
        print(f'{fk} fold {k}: train {dt:.0f}s steps {out.global_step} loss {out.training_loss:.3f} '
              f'fold acc {np.mean([pred[i] == y[i] for i in te]):.3f}', flush=True)
    m = H.attr_metrics(y, list(pred), H.train_counts(sf, F))
    params_m, mb = size(model)
    W.add('w5', SHORT, TASK[fk], variant, m, n=len(sf), params_m=params_m, disk_mb=mb, train_s=round(train_s, 1),
          notes=f'epochs={EPOCHS}; train_s={train_s:.0f} (5 folds); steps={steps}; threads={THREADS}; bs={BS}; lr={LR}; '
                f'warmup=0.1; no_duplicates sampler; folds={fk}')
    print(fk, variant, {k: round(v, 3) for k, v in m.items() if k.startswith('acc')}, flush=True)

if not AUG:  # inference speed at 2 threads (fine-tuning does not change the architecture)
    torch.set_num_threads(2); H.set_threads(2)
    s = H.encode_speed(lambda b: model.encode(b, batch_size=32), [r['text'] for r in rows])
    W.add('w5', SHORT, 'finetune_bi_attr', 'speed_2threads', s, n=len(rows), notes='threads=2; encode, bs=32; fine-tuned weights',
          sents_per_s=round(s['sentences_per_s'], 1), params_m=params_m, disk_mb=mb)
    print('speed', s, flush=True)
