import json, re, sys, os
import pandas as pd
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.abspath("src"))
from label_rows import (Lexicon, Router, build_kb, add_context, train_features,
                        make_judge, featurize, to_output, primary, text_tokens,
                        value_token, pdate)

lex = Lexicon("data/lexicon.json")
practice_df = pd.read_csv("data/practice.csv", dtype=str, keep_default_na=False)
sample_df = pd.read_csv("sample/sample.csv", dtype=str, keep_default_na=False)

practice = add_context(practice_df, lex)
uni = add_context(sample_df, lex)

Ftr, _ = train_features(practice)
judge = make_judge().fit(Ftr, practice.label)
router = Router().fit(practice.router_text.tolist(), [primary(f) for f in practice.form])
kb = build_kb(practice)

r_all = router.predict(uni.router_text.tolist())
from label_rows import build_votes
votes = build_votes(uni, r_all, kb)

F_test = featurize(uni, r_all, kb, votes)
res = to_output(uni.id, judge, F_test)

print("=" * 80)
print(f"{'ID':<6} | {'Label':<7} | {'Conf':<6} | {'Date':<10} | {'Router Best Match':<35}")
print("=" * 80)
for i, row in res.iterrows():
    r_item = r_all[i]
    print(f"{row['id']:<6} | {row['label']:<7} | {str(row['confidence']):<6} | {uni.date[i]:<10} | {r_item[0]:<35} (p={r_item[1]:.2f})")
    print(f"       Text: {uni.text[i]}")
    tokens = text_tokens(uni.text[i])
    s, a = r_item[0].split("||")
    dd = pdate(uni.date[i])
    cur, past, fut, days = kb.at((s, a), dd)
    lies = kb.lies.get((s, a), set())
    print(f"       Tokens: {tokens}")
    print(f"       KB current: {cur} | past: {past} | fut: {fut} | lies: {lies} | days: {days}")
    print("-" * 80)
