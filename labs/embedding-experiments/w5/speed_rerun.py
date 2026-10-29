"""Back-to-back 2-thread inference speed of the saved fine-tuned models, so the numbers share one machine load.
Bi-encoders: sentences/s (the 514 descriptions are encoded once, so this is the per-claim cost). Cross-encoder:
pairs/s on real (text, candidate description) pairs; per-claim cost = pairs/s / candidates per claim (14.3)."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import os, logging
from sentence_transformers import SentenceTransformer, CrossEncoder
from transformers import AutoModelForSequenceClassification, AutoTokenizer
logging.getLogger('transformers').setLevel(logging.ERROR)
rows, lex = H.load(); sf = H.single_fact_rows(rows); texts = [r['text'] for r in rows]
W, M, load = H.ResultWriter(H.results_path('w5')), '/tmp/veridyct-emb/w5/models/', os.getloadavg()[0]
pairs = [(r['text'], H.describe(r['facts'][0]['subject'], a)) for r in sf[::4] for a in H.candidates(lex, r['facts'][0]['subject'])]
out = {}
for d, short in (('f1_bge-small-en-v1.5', 'bge-small-en-v1.5'), ('f1_all-MiniLM-L6-v2', 'all-MiniLM-L6-v2')):
    m = SentenceTransformer(M + d, device='cpu')
    out[short] = s = H.encode_speed(lambda b: m.encode(b, batch_size=32), texts)
    W.add('w5', short, 'finetune_bi_attr', 'speed_2threads_rerun', s, n=len(texts), sents_per_s=round(s['sentences_per_s'], 1),
          notes=f'threads=2; back-to-back rerun; loadavg_1m={load:.1f}')
ce = CrossEncoder(M + 'f2_ms-marco-MiniLM-L-6-v2', device='cpu')
out['ce'] = s = H.encode_speed(lambda b: ce.predict(b, batch_size=32, show_progress_bar=False), pairs)
W.add('w5', 'ms-marco-MiniLM-L-6-v2', 'finetune_ce_attr', 'speed_2threads_rerun', s, n=len(pairs),
      pairs_per_s=round(s['sentences_per_s'], 1), notes=f'threads=2; back-to-back rerun; loadavg_1m={load:.1f}; '
      f'claims/s at 14.3 candidates = {s["sentences_per_s"] / 14.3:.1f}; est_sec_20k_x86 is per 20k PAIRS')
tok = AutoTokenizer.from_pretrained(M + 'f3_bge-small-en-v1.5')
clf = AutoModelForSequenceClassification.from_pretrained(M + 'f3_bge-small-en-v1.5').eval()
def fwd(b):
    with torch.no_grad(): clf(**tok(b, padding=True, truncation=True, max_length=96, return_tensors='pt'))
out['clf'] = s = H.encode_speed(fwd, texts)
W.add('w5', 'bge-small-en-v1.5', 'finetune_truth_text', 'speed_2threads_rerun', s, n=len(texts),
      sents_per_s=round(s['sentences_per_s'], 1), notes=f'threads=2; back-to-back rerun; loadavg_1m={load:.1f}')
print(f'loadavg {load:.1f}', {k: round(v['sentences_per_s'], 1) for k, v in out.items()}, flush=True)
