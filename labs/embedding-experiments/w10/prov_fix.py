"""Append a provenance sentence to the notes of every w10 record (atomic rewrite; run once, when no run is writing)."""
import json, os
P = '/tmp/veridyct-emb/results/w10.jsonl'
KD27 = 'provenance: logit distillation from an NLI finetune of Qwen3.8-27B (27B LLM teacher, per model card); the deployed model is still the encoder'
PROV = {'dleemiller/finecat-nli-v2-m': KD27, 'dleemiller/finecat-nli-ultra-m': KD27,
        'dleemiller/finecat-nli-s': 'provenance: logit distillation from dleemiller/finecat-nli-l (an encoder teacher, not the 27B LLM) per model card',
        'dleemiller/finecat-nli-xs': 'provenance: logit distillation from dleemiller/finecat-nli-l (an encoder teacher, not the 27B LLM) per model card',
        'dleemiller/finecat-nli-xxs': 'provenance: logit distillation from dleemiller/finecat-nli-l (an encoder teacher, not the 27B LLM) per model card',
        'tasksource/ModernBERT-base-nli': 'provenance: supervised multi-task NLI fine-tune of ModernBERT-base (tasksource), no distillation stated',
        'tals/albert-base-vitaminc-mnli': 'provenance: supervised on VitaminC + MNLI (Schuster et al. 2021), no distillation',
        'knowledgator/gliclass-edge-v3.0': 'provenance: GLiClass v3, trained on logic datasets with LoRA (per model card), no teacher stated',
        'knowledgator/gliclass-modern-base-v3.0': 'provenance: GLiClass v3, trained on logic datasets with LoRA (per model card), no teacher stated'}
recs = [json.loads(l) for l in open(P)]
for r in recs:
    p = PROV.get(r['model'])
    if p and 'provenance:' not in (r.get('notes') or ''): r['notes'] = (r.get('notes') or '') + '; ' + p
tmp = P + '.tmp'
with open(tmp, 'w') as f:
    for r in recs: f.write(json.dumps(r, ensure_ascii=False) + '\n')
os.replace(tmp, P); print(len(recs), 'records rewritten')
