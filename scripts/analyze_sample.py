import csv
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath("src"))

from label_rows import Lexicon, Router, build_kb, add_context, train_features, make_judge, featurize, to_output, primary
import pandas as pd

lex = Lexicon("data/lexicon.json")
practice_df = pd.read_csv("data/practice.csv", dtype=str, keep_default_na=False)
sample_df = pd.read_csv("sample/sample.csv", dtype=str, keep_default_na=False)

practice = add_context(practice_df, lex)
uni = add_context(sample_df, lex)

router = Router().fit(practice.router_text.tolist(), [primary(f) for f in practice.form])
kb = build_kb(practice)
r_all = router.predict(uni.router_text.tolist())

print(f"{'ID':<6} | {'Date':<10} | {'Subject/Attr Predicted':<35} | Text")
print("-" * 100)
for idx, r in uni.iterrows():
    pred_fact = r_all[idx]
    fact_str = f"{pred_fact[0]}||{pred_fact[1]}"
    text = r['text']
    print(f"{r['id']:<6} | {r['date']:<10} | {fact_str:<35} | {text}")

print("\n--- Knowledge Base timeline for matched (subject, attribute) ---")
for idx, r in uni.iterrows():
    pred_fact = r_all[idx]
    fact_str = f"{pred_fact[0]}||{pred_fact[1]}"
    tl = kb.get(pred_fact, [])
    print(f"\n[{r['id']}] {fact_str} (Date: {r['date']}):")
    print(f"  Sentence: {r['text']}")
    print(f"  KB entries ({len(tl)}):")
    for item in tl[:5]:
        print(f"    - Date: {item.get('date')} | Label: {item.get('label')} | Val: {item.get('val')}")
