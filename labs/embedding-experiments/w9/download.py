"""Download every w9 model into /tmp/veridyct-emb/w9/hf (own cache, nothing outside w9). Usage: python -I download.py [id ...]"""
import os, sys, time
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w9/hf'
from huggingface_hub import snapshot_download
PAT = ['*.json', '*.txt', '*.safetensors', '*.model', '*.py', '*.jsonl']
ORDER = ['MongoDB/mdbr-leaf-mt', 'avsolatorio/GIST-small-Embedding-v0', 'prdev/mini-gte', 'hotchpotch/bekko-static-embedding-v1',
         'hotchpotch/bekko-embedding-v1-a8m', 'dmis-lab/UltraBERT-Embed-150M', 'WhereIsAI/UAE-Large-V1',
         'jinaai/jina-embeddings-v5-text-nano', 'lightonai/DenseOn', 'jxm/cde-small-v2']
for mid in (sys.argv[1:] or ORDER):
    t = time.time()
    try:
        p = snapshot_download(mid, allow_patterns=PAT)
        print(f'OK   {mid} -> {p} ({time.time() - t:.0f}s)', flush=True)
    except Exception as e:
        print(f'FAIL {mid}: {type(e).__name__}: {str(e)[:300]}', flush=True)
