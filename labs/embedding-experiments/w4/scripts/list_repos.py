import os, sys
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w4/hf'
from huggingface_hub import HfApi
api = HfApi()
IDS = """cross-encoder/nli-deberta-v3-xsmall
cross-encoder/nli-deberta-v3-small
cross-encoder/nli-deberta-v3-base
cross-encoder/nli-MiniLM2-L6-H768
cross-encoder/nli-distilroberta-base
MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
MoritzLaurer/deberta-v3-base-zeroshot-v2.0
MoritzLaurer/deberta-v3-large-zeroshot-v2.0
MoritzLaurer/ModernBERT-base-zeroshot-v2.0
tasksource/deberta-small-long-nli
tals/albert-xlarge-vitaminc-mnli
facebook/bart-large-mnli""".split()
for i in IDS:
    try:
        info = api.model_info(i, files_metadata=True)
        fs = [(s.rfilename, s.size or 0) for s in info.siblings]
        st = [(n, s) for n, s in fs if n.endswith('.safetensors')]
        bn = [(n, s) for n, s in fs if n.endswith('.bin')]
        print(f"{i}: files={len(fs)} safetensors={[(n, round(s/1e6)) for n,s in st]} bin={[(n, round(s/1e6)) for n,s in bn]} py={[n for n,_ in fs if n.endswith('.py')]} tags={info.tags[:6]}")
    except Exception as e:
        print(f"{i}: ERROR {type(e).__name__}: {str(e)[:150]}")
