import os
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w10/hf'
import torch; torch.set_num_threads(1)
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import inspect
p = snapshot_download('tals/albert-base-vitaminc-mnli', allow_patterns=['*.json', '*.safetensors', '*.model', '*.txt'])
tok = AutoTokenizer.from_pretrained(p); m = AutoModelForSequenceClassification.from_pretrained(p).eval()
print('forward has token_type_ids:', 'token_type_ids' in inspect.signature(m.forward).parameters, '| model_input_names', tok.model_input_names)
pairs = [('Pixel 10 costs €799.', 'Pixel 10 costs €799.'), ('Pixel 10 costs €799.', 'Pixel 10 costs €549.'), ('Pixel 10 costs €799.', 'Pixel 10 ships in black.')]
with torch.inference_mode():
    e = tok([a for a, _ in pairs], [b for _, b in pairs], padding=True, return_tensors='pt', return_token_type_ids=True)
    print(list(e.keys()), e['token_type_ids'][0].tolist())
    print(torch.softmax(m(**e).logits, -1).numpy().round(3))
