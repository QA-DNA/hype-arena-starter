import os, sys, json
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
from huggingface_hub import snapshot_download
from safetensors import safe_open
p = snapshot_download('tals/albert-base-vitaminc-mnli', allow_patterns=['*.json', '*.safetensors', '*.model', '*.txt'])
print(os.listdir(p))
with safe_open(os.path.join(p, 'model.safetensors'), 'pt') as f:
    ks = list(f.keys())
print(len(ks)); print(ks)
print(open(os.path.join(p, 'config.json')).read()[:900])
print(open(os.path.join(p, 'tokenizer_config.json')).read()[:600])
