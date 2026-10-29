import os, sys, time
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
from huggingface_hub import snapshot_download
models = sys.argv[1:]
for m in models:
    t = time.time()
    try:
        p = snapshot_download(m, allow_patterns=['*.json', '*.safetensors', '*.py', '*.model', '*.txt', '*.md'] if 'albert' not in m else ['*.json', '*.safetensors', '*.model', '*.md', '*.txt'])
        print('OK', m, p, f'{time.time()-t:.1f}s', flush=True)
    except Exception as e:
        print('FAIL', m, repr(e)[:300], flush=True)
