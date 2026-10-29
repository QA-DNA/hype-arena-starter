# Sequential background download of the model snapshots (I/O only, no torch). HF_HOME = shared cache.
import os, sys, time
os.environ.setdefault('HF_HOME', '/tmp/veridyct-bench/hf')
from huggingface_hub import snapshot_download, list_repo_files
PAT = ['*.json', '*.txt', '*.safetensors', '*.model', '*.py', '*.jsonl']
ORDER = ['ibm-granite/granite-embedding-small-english-r2', 'nomic-ai/nomic-embed-text-v1.5', 'nomic-ai/modernbert-embed-base',
         'Alibaba-NLP/gte-modernbert-base', 'ibm-granite/granite-embedding-english-r2', 'BAAI/bge-large-en-v1.5',
         'intfloat/e5-large-v2', 'thenlper/gte-large', 'mixedbread-ai/mxbai-embed-large-v1', 'NovaSearch/stella_en_400M_v5',
         'Snowflake/snowflake-arctic-embed-l-v2.0', 'BAAI/bge-m3', 'jinaai/jina-embeddings-v3']
only = sys.argv[1:] or ORDER
for rid in only:
    t0 = time.time()
    try:
        files = list_repo_files(rid)
        pat = list(PAT)
        if not any(f.endswith('.safetensors') and '/' not in f for f in files):
            pat.append('pytorch_model.bin'); print('  no top-level safetensors, adding pytorch_model.bin', flush=True)
        ign = None
        if rid == 'NovaSearch/stella_en_400M_v5':
            ign = [f'2_Dense_{d}/*' for d in (256, 512, 768, 2048, 4096, 6144, 8192)]
        if rid == 'nomic-ai/nomic-embed-text-v1.5':  # code repo referenced by auto_map
            snapshot_download('nomic-ai/nomic-bert-2048', allow_patterns=['*.py', '*.json'])
        p = snapshot_download(rid, allow_patterns=pat, ignore_patterns=ign)
        mb = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs if f.endswith(('.safetensors', '.bin'))) / 1e6
        print(f'OK   {rid} {mb:.0f} MB weights in {time.time()-t0:.0f}s -> {p}', flush=True)
    except Exception as e:
        print(f'FAIL {rid}: {type(e).__name__}: {e}', flush=True)
