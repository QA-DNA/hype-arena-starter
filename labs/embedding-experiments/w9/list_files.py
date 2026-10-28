import os, sys
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w9/hf'
from huggingface_hub import HfApi
api = HfApi()
IDS = ['MongoDB/mdbr-leaf-mt','prdev/mini-gte','avsolatorio/GIST-small-Embedding-v0','dmis-lab/UltraBERT-Embed-150M','WhereIsAI/UAE-Large-V1',
       'jinaai/jina-embeddings-v5-text-nano','hotchpotch/bekko-static-embedding-v1','hotchpotch/bekko-embedding-v1-a8m','jxm/cde-small-v2','lightonai/DenseOn']
for i in IDS:
    try:
        info = api.model_info(i, files_metadata=True)
        fs = [(s.rfilename, s.size) for s in info.siblings]
        tot = sum((s or 0) for _, s in fs)
        print(f'== {i}  gated={info.gated} private={info.private} lib={info.library_name} tags={[t for t in info.tags if t.startswith("license") or t in ("sentence-transformers","model2vec","static-embeddings")]}')
        for n, s in fs:
            if n.endswith(('.safetensors','.bin','.py','.model','.onnx','.gguf')) or n.count('/') == 0 and n.endswith('.json'):
                print(f'    {n:60s} {((s or 0)/2**20):9.1f} MB')
    except Exception as e:
        print(f'== {i}  ERROR {type(e).__name__}: {str(e)[:200]}')
