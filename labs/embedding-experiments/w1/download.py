import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w1')
import harness as H; H.set_threads(2)
import os, time, json
from huggingface_hub import snapshot_download, list_repo_files
from models import MODELS, REMOTE_CODE_REPOS, PATTERNS
status = {}
for mid in list(MODELS) + REMOTE_CODE_REPOS:
    t0 = time.time()
    try:
        files = list_repo_files(mid)
    except Exception as e:
        status[mid] = f'MISSING/ERR: {type(e).__name__}: {str(e)[:120]}'; print(mid, status[mid], flush=True); continue
    pats = PATTERNS
    has_st = any(f.endswith('.safetensors') for f in files)
    if not has_st and mid not in REMOTE_CODE_REPOS:  # fall back to pytorch .bin weights only when no safetensors exist
        pats = PATTERNS + ['pytorch_model.bin']
    try:
        p = snapshot_download(mid, allow_patterns=pats)
        status[mid] = f'ok {p} safetensors={has_st} {time.time()-t0:.0f}s'
    except Exception as e:
        status[mid] = f'FAIL: {type(e).__name__}: {str(e)[:200]}'
    print(mid, status[mid], flush=True)
json.dump(status, open('/tmp/veridyct-emb/w1/download_status.json', 'w'), indent=1)
print('DONE', flush=True)
