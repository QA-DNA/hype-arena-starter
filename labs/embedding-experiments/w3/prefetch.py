"""Download every w3 model into w3's own HF_HOME (never the shared cache). Runs in the background."""
import os, sys, time, json
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w3/hf'
from huggingface_hub import snapshot_download, list_repo_files
MODELS = ['minishlab/potion-base-8M', 'minishlab/potion-base-32M', 'minishlab/potion-retrieval-32M',
          'sentence-transformers/static-retrieval-mrl-en-v1', 'sentence-transformers/static-similarity-mrl-multilingual-v1',
          'intfloat/multilingual-e5-small', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
          'Qwen/Qwen3-Embedding-0.6B', 'nomic-ai/nomic-embed-text-v2-moe', 'google/embeddinggemma-300m',
          'sentence-transformers/average_word_embeddings_glove.6B.300d']
IGN = ['onnx/*', 'openvino/*', '*.onnx', '*.h5', '*.msgpack', '*.ot', 'flax_model*', 'tf_model*', 'coreml/*', '*.mlpackage/*',
       '*.gguf', 'imgs/*', '*.png', '*.jpg', 'rust_model*', '*.tflite']
status = {}
for mid in (sys.argv[1:] or MODELS):
    t0 = time.time()
    try:
        files = list_repo_files(mid)
        ign = IGN + (['*.bin'] if any(f.endswith('.safetensors') for f in files) else [])
        p = snapshot_download(mid, ignore_patterns=ign)
        status[mid] = dict(ok=True, path=p, secs=round(time.time() - t0, 1))
    except Exception as e:
        status[mid] = dict(ok=False, err=f'{type(e).__name__}: {str(e)[:300]}', secs=round(time.time() - t0, 1))
    print(mid, status[mid], flush=True)
    json.dump(status, open('/tmp/veridyct-emb/w3/prefetch_status.json', 'w'), indent=1)
print('DONE', flush=True)
