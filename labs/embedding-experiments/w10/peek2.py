import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
rows, lex = H.load(); sf = H.single_fact_rows(rows)
import collections
n = [len(H.candidates(lex, r['facts'][0]['subject'])) for r in sf]
print('cand per row: min', min(n), 'max', max(n), 'mean', sum(n)/len(n))
print(sorted(collections.Counter(len(s['attributes']) for s in lex['subjects'].values()).items()))
print([ (k, len(v['attributes'])) for k, v in lex['subjects'].items() if len(v['attributes']) >= 14])
print(sum(1 for r in sf if not H.candidates(lex, r['facts'][0]['subject'])))
# do row texts mention the subject?
import re
ment = sum(1 for r in sf if r['facts'][0]['subject'].lower() in r['text'].lower())
print('subject literally in text', ment, '/', len(sf))
