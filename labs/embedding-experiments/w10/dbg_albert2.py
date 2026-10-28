import os, sys
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
import torch; torch.set_num_threads(1)
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import sentencepiece as spm
p = snapshot_download('tals/albert-base-vitaminc-mnli', allow_patterns=['*.json', '*.safetensors', '*.model', '*.txt'])
tok = AutoTokenizer.from_pretrained(p); print(type(tok).__name__)
sp = spm.SentencePieceProcessor(model_file=os.path.join(p, 'spiece.model'))
s = 'Pixel 10 costs €799.'
print('hf  :', tok.tokenize(s)); print('sp  :', sp.encode(s, out_type=str)); print('sp lower:', sp.encode(s.lower(), out_type=str))
enc = tok('Pixel 10 costs €799.', 'Pixel 10 costs €549.'); print(enc)
print(tok.convert_ids_to_tokens(enc['input_ids']))
m = AutoModelForSequenceClassification.from_pretrained(p).eval()
pairs = [('A man is sleeping on the couch.', 'A man is awake.'), ('The Eiffel Tower is in Paris.', 'The Eiffel Tower is in Paris.'), ('The Eiffel Tower is in Paris.', 'The Eiffel Tower is in Rome.'),
         ('Pixel 10 costs €799.', 'Pixel 10 costs €549.'), ('pixel 10 costs 799 euros.', 'pixel 10 costs 549 euros.')]
with torch.inference_mode():
    for a, b in pairs:
        e = tok(a, b, return_tensors='pt'); print(a, '|', b, torch.softmax(m(**e).logits, -1).numpy().round(3), 'tti' in str(e.keys()), list(e.keys()))
    # manual lowercase path via sentencepiece ids
    ids = [tok.cls_token_id] + sp.encode('the eiffel tower is in paris.') + [tok.sep_token_id] + sp.encode('the eiffel tower is in rome.') + [tok.sep_token_id]
    tt = [0] * (len(sp.encode('the eiffel tower is in paris.')) + 2) + [1] * (len(sp.encode('the eiffel tower is in rome.')) + 1)
    print('manual-lower', torch.softmax(m(input_ids=torch.tensor([ids]), token_type_ids=torch.tensor([tt])).logits, -1).numpy().round(3))
