"""Background downloader: safetensors-only snapshots into /tmp/veridyct-emb/w4/models/<repo--name>. Skips the 3 models already
complete in the shared read-only cache (resolved by path, never written). No trust_remote_code anywhere (no repo ships .py)."""
import os, sys, time
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w4/hf'   # keep xet/hub scratch out of the shared cache
from huggingface_hub import snapshot_download
ORDER = """cross-encoder/nli-deberta-v3-small
cross-encoder/nli-distilroberta-base
tasksource/deberta-small-long-nli
MoritzLaurer/deberta-v3-base-zeroshot-v2.0
MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
MoritzLaurer/ModernBERT-base-zeroshot-v2.0
tals/albert-xlarge-vitaminc-mnli
facebook/bart-large-mnli
MoritzLaurer/deberta-v3-large-zeroshot-v2.0""".split()
PAT = ['*.json', '*.txt', '*.safetensors', '*.model', 'README.md']
for rid in ORDER:
    d = '/tmp/veridyct-emb/w4/models/' + rid.replace('/', '--')
    t0 = time.time()
    try:
        snapshot_download(rid, allow_patterns=PAT, local_dir=d)
        open(d + '/.dl_done', 'w').write(f'{time.time()-t0:.1f}s\n')
        print(f'OK   {rid} {time.time()-t0:.1f}s', flush=True)
    except Exception as e:
        print(f'FAIL {rid} {type(e).__name__}: {str(e)[:200]}', flush=True)
print('ALL DONE', flush=True)
