import csv
import json
from collections import Counter, defaultdict

with open('output/output.csv', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

sample_rows = [x for x in rows if x['id'].startswith('s-')]
claims_rows = [x for x in rows if x['type']]
practice_rows = [x for x in rows if not x['id'].startswith('s-') and not x['type']]

print(f"Total rows in output.csv: {len(rows):,}")
print(f"  - Practice rows (Section A): {len(practice_rows):,}")
print(f"  - Sample rows (Section B)  : {len(sample_rows):,}")
print(f"  - Generated claims (Sec C) : {len(claims_rows):,}")

print("\n" + "=" * 95)
print(f"{'ID':<6} | {'Label':<8} | {'Confidence':<12} | Text")
print("=" * 95)
with open('sample/sample.csv', encoding='utf-8') as f:
    sample_inputs = {r['id']: r for r in csv.DictReader(f)}

for s in sample_rows:
    sid = s['id']
    inp = sample_inputs.get(sid, {})
    text = inp.get('text', '')
    date = inp.get('date', '')
    conf = s['confidence'] if s['confidence'] else "(empty)"
    print(f"{sid:<6} | {s['label']:<8} | {conf:<12} | [{date}] {text}")

print("\n" + "=" * 95)
print("CLAIMS BREAKDOWN:")
claim_types = Counter(c['type'] for c in claims_rows)
print("Distribution by Type:", dict(claim_types))

confidences = [float(c['confidence']) for c in claims_rows if c['confidence']]
print(f"Confidence range: min={min(confidences):.2f}, max={max(confidences):.2f}, mean={sum(confidences)/len(confidences):.3f}")

print("\nSample Generated Claims (first 2 of each type):")
seen_types = defaultdict(int)
for c in claims_rows:
    t = c['type']
    if seen_types[t] < 2:
        seen_types[t] += 1
        print(f"\n[{t.upper()}] ID: {c['id']} | Conf: {c['confidence']}")
        print(f"  Text: {c['text']}")
        print(f"  Form: {c['form']}")
