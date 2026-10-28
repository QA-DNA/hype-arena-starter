"""Encode all practice texts once with bge-small-en-v1.5, L2-normalised, cached to cache/bge_small.npy (+ texts.json)."""
import sys, json, time
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
H.set_threads(2)
import numpy as np, torch
torch.set_num_threads(2)
from sentence_transformers import SentenceTransformer
rows, _ = H.load()
texts = [r['text'] for r in rows]
m = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
t0 = time.time()
E = m.encode(texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
print('encoded', E.shape, f'{time.time() - t0:.1f}s', flush=True)
np.save('/tmp/veridyct-emb/w6/cache/bge_small.npy', E.astype(np.float32))
json.dump(dict(ids=[r['id'] for r in rows], texts=texts), open('/tmp/veridyct-emb/w6/cache/texts.json', 'w'))
