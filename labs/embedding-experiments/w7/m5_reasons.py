"""M5 failure reasons, mutually exclusive, priority order. Prints counts and examples."""
import sys, re, json
sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w7')
import harness as H, values as V
from collections import Counter, defaultdict
rows, lex = H.load()
PRON = re.compile(r'^\W*(?:It|Its|He|She|They|This|That|These|Those|His|Her|Their|Them)\b|\b(?:it|its|he|she|they|his|her|their|them|this|these)\b')
WE = re.compile(r'\b(?:we|our|us|we\'re|we\'ve)\b', re.I)
reasons, ex = Counter(), defaultdict(list)
miss_subj = Counter()
for r in rows:
    ents = V.find_entities(r['text'], lex, strict_case=False)
    found = {e[2] for e in ents}
    gs = {f['subject'] for f in r['facts']}
    if gs <= found: continue
    miss = sorted(gs - found)
    t = r['text']
    toks = [w for m in miss for w in re.findall(r"[A-Za-z0-9/]+", m) if w.lower() not in ('hooly', 'the', 'by', 'of')]
    partial = [w for w in toks if len(w) >= 3 and re.search(r'\b' + re.escape(w) + r'\b', t)]
    if re.match(r'^\s*[A-Z][a-z]+:', t): why = 'speaker_tag_only (Gavin: ...)'
    elif miss == ['Hooly'] and WE.search(t): why = 'implicit company ("we", "our")'
    elif PRON.search(t) and not ents: why = 'pronoun / anaphora, no entity'
    elif partial: why = 'partial name only (' + ','.join(sorted(set(partial)))[:30] + ')'
    elif not ents and len(t.split()) <= 7: why = 'headline / label fragment, no entity'
    elif not ents: why = 'no entity, full sentence about an unnamed thing'
    elif PRON.search(t): why = 'pronoun + other entity present'
    else: why = 'other entity present, gold subject unnamed'
    key = why.split(' (')[0] if why.startswith('partial') else why
    reasons[key] += 1; ex[key].append((r['id'], miss, t[:95]))
    for m in miss: miss_subj[m] += 1
tot = sum(reasons.values())
print('failed rows', tot)
for k, n in reasons.most_common():
    print(f'{n:4d} {n / tot:.3f}  {k}')
    for e in ex[k][:2]: print('       ', e)
print(miss_subj.most_common(10))
