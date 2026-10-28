import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(1)
import os; os.environ['HF_HUB_OFFLINE'] = '1'
import torch; torch.set_num_threads(1)
import warnings; warnings.filterwarnings('ignore')
from sentence_transformers import SentenceTransformer
mid = sys.argv[1]
m = SentenceTransformer(mid, device='cpu', trust_remote_code=True)
e = m.encode(['Holdan team size is 12.', 'hello world'], convert_to_numpy=True)
print('OK', mid, e.shape, m.max_seq_length, float((e[0]*e[0]).sum()**.5))
