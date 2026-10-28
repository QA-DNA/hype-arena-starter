"""Build-time only: pull the eight finalist models (safetensors + tokenizer/config files, no onnx/openvino/bin) into /app/models/<key>."""
import os, shutil
os.environ['HF_HOME'] = '/tmp/hf-build'  # throwaway cache, removed below so it never lands in the image
from huggingface_hub import snapshot_download

MODELS = {  # local dir -> repo actually downloaded
    'all-MiniLM-L6-v2': 'sentence-transformers/all-MiniLM-L6-v2',
    'all-MiniLM-L12-v2': 'sentence-transformers/all-MiniLM-L12-v2',
    'mxbai-embed-xsmall-v1': 'mixedbread-ai/mxbai-embed-xsmall-v1',
    'bge-small-en-v1.5': 'BAAI/bge-small-en-v1.5',
    'potion-base-8M': 'minishlab/potion-base-8M',
    'static-similarity-mrl-multilingual-v1': 'sentence-transformers/static-similarity-mrl-multilingual-v1',
    'nli-deberta-v3-xsmall': 'cross-encoder/nli-deberta-v3-xsmall',
    # the requested id cross-encoder/ms-marco-MiniLM-L-6-v2 is a 307 redirect to this renamed repo
    'ms-marco-MiniLM-L-6-v2': 'cross-encoder/ms-marco-MiniLM-L6-v2',
}
ALLOW = ['*.json', '*.txt', '*.safetensors', '*.model']
IGNORE = ['onnx/*', 'openvino/*', 'gguf/*', 'img/*', '*.onnx', '*.bin', '*.h5', '*.msgpack', '*.ot', '*.gguf']

for d, repo in MODELS.items():
    p = snapshot_download(repo, local_dir=f'/app/models/{d}', allow_patterns=ALLOW, ignore_patterns=IGNORE)
    shutil.rmtree(f'{p}/.cache', ignore_errors=True)
    files = sorted(os.path.relpath(os.path.join(r, f), p) for r, _, fs in os.walk(p) for f in fs)
    assert any(f.endswith('.safetensors') for f in files), f'{repo}: no safetensors'
    mb = sum(os.path.getsize(os.path.join(p, f)) for f in files) / 1e6
    print(f'{d:42s} {repo:62s} {mb:7.1f} MB  {len(files)} files', flush=True)
shutil.rmtree('/tmp/hf-build', ignore_errors=True)
