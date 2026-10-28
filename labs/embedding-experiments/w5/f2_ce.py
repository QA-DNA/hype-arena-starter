"""F2: fine-tune a cross-encoder on (text, describe(subject, attr)) -> 1 gold / 0 for up to 5 hard negatives (other
attributes of the same subject). Predict argmax over the subject's candidates. Page folds + attribute folds.
Usage: python -I f2_ce.py MODEL [lexneg] [nobase]
  default negatives: only attributes present in the TRAINING fold (held-out descriptions never seen in training);
  lexneg: negatives from the full lexicon (held-out attribute descriptions appear as negatives: lexicon known up front)."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(4)
import torch; torch.set_num_threads(4)
import os, random, shutil, time, logging
import numpy as np
from datasets import Dataset
from sentence_transformers import CrossEncoder, CrossEncoderTrainer, CrossEncoderTrainingArguments
from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss

logging.getLogger('transformers').setLevel(logging.ERROR)
MODEL, LEXNEG, NOBASE = sys.argv[1], 'lexneg' in sys.argv[2:], 'nobase' in sys.argv[2:]
SHORT = MODEL.split('/')[-1]
EPOCHS, BS, LR, THREADS, NNEG = 2, 32, 2e-5, 4, 5
W = H.ResultWriter(H.results_path('w5'))
rows, lex = H.load(); sf = H.single_fact_rows(rows)
y = [r['facts'][0]['attribute'] for r in sf]
subj = [r['facts'][0]['subject'] for r in sf]
texts = [r['text'] for r in sf]
FOLDS = {'page': H.page_folds(sf), 'attr': H.attribute_folds(sf)}
if LEXNEG: FOLDS.pop('page')  # the lexicon-negatives question only matters for unseen attributes
TASK = {'page': 'finetune_ce_attr', 'attr': 'finetune_ce_unseen'}

def load(): return CrossEncoder(MODEL, num_labels=1, device='cpu')

def predict(ce, idx):
    pairs, own = [], []
    for i in idx:
        C = H.candidates(lex, subj[i])
        pairs += [(texts[i], H.describe(subj[i], a)) for a in C]; own.append(C)
    s, out, o = ce.predict(pairs, batch_size=64, convert_to_numpy=True, show_progress_bar=False), [], 0
    for C in own:
        out.append(C[int(np.argmax(s[o:o + len(C)]))]); o += len(C)
    return out, pairs

def size(ce):
    d = f'/tmp/veridyct-emb/w5/models/f2_{SHORT}'
    shutil.rmtree(d, ignore_errors=True); ce.save(d)
    mb = sum(os.path.getsize(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs) / 1e6
    return round(sum(p.numel() for p in ce.model.parameters()) / 1e6, 2), round(mb, 1)

if not (LEXNEG or NOBASE):  # control: un-tuned cross-encoder, same evaluation
    p0, _ = predict(load(), range(len(sf)))
    for fk, F in FOLDS.items():
        m = H.attr_metrics(y, p0, H.train_counts(sf, F))
        W.add('w5', SHORT, TASK[fk], 'base_zeroshot', m, n=len(sf), notes=f'no training; folds={fk}; threads={THREADS}')
        print(fk, 'base', {k: round(v, 3) for k, v in m.items() if k.startswith('acc')}, flush=True)

variant = 'bce_hardneg_lexicon' if LEXNEG else 'bce_hardneg'
for fk, F in FOLDS.items():
    pred, train_s, steps, npairs = np.empty(len(sf), dtype=object), 0.0, 0, 0
    for k, (tr, te) in enumerate(F):
        torch.manual_seed(k); rng = random.Random(k)
        seen = {y[i] for i in tr}
        a, b, lab = [], [], []
        for i in tr:
            neg = [c for c in H.candidates(lex, subj[i]) if c != y[i] and (LEXNEG or c in seen)]
            for c, l in [(y[i], 1.0)] + [(c, 0.0) for c in rng.sample(neg, min(NNEG, len(neg)))]:
                a.append(texts[i]); b.append(H.describe(subj[i], c)); lab.append(l)
        ce = load()
        args = CrossEncoderTrainingArguments(
            output_dir=f'/tmp/veridyct-emb/w5/out/f2_{SHORT}', num_train_epochs=EPOCHS, per_device_train_batch_size=BS,
            learning_rate=LR, warmup_ratio=0.1, save_strategy='no', report_to='none', use_cpu=True, seed=k,
            logging_steps=1000, disable_tqdm=True, dataloader_num_workers=0)
        t = CrossEncoderTrainer(model=ce, args=args, train_dataset=Dataset.from_dict({'text': a, 'desc': b, 'label': lab}),
                                loss=BinaryCrossEntropyLoss(ce))
        t0 = time.perf_counter(); out = t.train(); dt = time.perf_counter() - t0
        train_s += dt; steps += out.global_step; npairs += len(a)
        pred[te], test_pairs = predict(ce, te)
        print(f'{fk} fold {k}: pairs {len(a)} train {dt:.0f}s steps {out.global_step} loss {out.training_loss:.3f} '
              f'fold acc {np.mean([pred[i] == y[i] for i in te]):.3f}', flush=True)
    m = H.attr_metrics(y, list(pred), H.train_counts(sf, F))
    params_m, mb = size(ce)
    W.add('w5', SHORT, TASK[fk], variant, m, n=len(sf), params_m=params_m, disk_mb=mb, train_s=round(train_s, 1),
          notes=f'epochs={EPOCHS}; train_s={train_s:.0f} (5 folds); steps={steps}; train_pairs={npairs} (5 folds); '
                f'threads={THREADS}; bs={BS}; lr={LR}; warmup=0.1; negs<={NNEG} same-subject '
                f'{"full lexicon" if LEXNEG else "train-fold attributes only"}; folds={fk}')
    print(fk, variant, {k: round(v, 3) for k, v in m.items() if k.startswith('acc')}, flush=True)

if not LEXNEG:  # pairs/s at 2 threads on the last fold's candidate pairs (same architecture as the base model)
    torch.set_num_threads(2); H.set_threads(2)
    s = H.encode_speed(lambda b_: ce.predict(b_, batch_size=32, show_progress_bar=False), test_pairs)
    cpc = len(test_pairs) / len(te)
    W.add('w5', SHORT, 'finetune_ce_attr', 'speed_2threads', s, n=len(test_pairs), pairs_per_s=round(s['sentences_per_s'], 1),
          params_m=params_m, disk_mb=mb, notes=f'threads=2; predict bs=32; {cpc:.1f} candidate pairs per row; '
          f'rows/s={s["sentences_per_s"] / cpc:.1f}; est_sec_20k_x86 is per 20k PAIRS')
    print('speed', s, 'cands/row', cpc, flush=True)
