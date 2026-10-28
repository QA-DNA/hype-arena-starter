"""Contract 'Not read' table: does the extractor still emit the forbidden value as an UNFLAGGED candidate?"""
import sys, json
sys.path.insert(0, '/tmp/veridyct-emb/w7')
import values as V
L = json.load(open('/tmp/veridyct-emb/common/lexicon.json', encoding='utf-8'))
lex = dict(subjects={s['name']: dict(aliases=s['aliases'], attributes=s['attributes']) for s in L['subjects']}, events=L['events'])
Q = lambda v, u, **k: dict(kind='quantity', value=v, unit=u, **k)
NOT_READ = [
 ('12/03/2026', dict(kind='date', value='2026-03-12')), ('12.03.2026', dict(kind='date', value='2026-03-12')),
 ('March 12', dict(kind='date', value='2026-03-12')), ('Q4 2026', dict(kind='date', value='2026')),
 ('12 March 2026', dict(kind='date', value='2026-03')), ('1.000.000 users', Q(1000000, 'user')), ('1,5 GB', Q(1.5, 'GB')),
 ('1,5 GB', Q(5, 'GB')), ('99,9% uptime', dict(kind='percent', value=9)), ('1.500 mAh', Q(1500, 'mAh')),
 ('99.6% uptime', dict(kind='percent', value=6)), ('we do not offer 99.9% uptime', dict(kind='percent', value=99.9)),
 ('no 14-day trial', dict(kind='duration', value=14, unit='day')), ('not founded by Gavin Bellson', dict(kind='name', value='Gavin Bellson')),
 ('about 10,000 customers', Q(10000, 'customer')), ('~10 GB', Q(10, 'GB')), ('40 languages or so', Q(40, 'language')),
 ('10–20 GB', Q(20, 'GB')), ('10 GB to 20 GB', Q(10, 'GB')), ('10 GB to 20 GB', Q(20, 'GB')), ('between 10 and 20 GB', Q(20, 'GB')),
 ('1 or 2 days', dict(kind='duration', value=2, unit='day')), ('10m users', Q(10000000, 'user')), ('2026 customers', Q(2026, 'customer')),
 ('half an hour', dict(kind='duration', value=30, unit='min')), ('1,000 requests a day', dict(kind='duration', value=1, unit='day')),
 ('€49 a month', dict(kind='money', value=49, currency='EUR')), ('5 pounds', dict(kind='money', value=5, currency='GBP')),
 ('Hooly Gemini 11', dict(kind='version', value='11')), ('30 days', dict(kind='duration', value=1, unit='month')),
 ('over 10,000 customers', Q(10000, 'customer')), ('10,000 of our happy loyal customers', Q(10000, 'customer'))]
bad = []
for text, forbidden in NOT_READ:
    C = V.extract_values(text, lex)
    raw = [c for c in C if c['value'] == forbidden]
    live = [c for c in raw if not ({'neg', 'approx', 'range'} & set(c['flags']))]
    status = 'LEAK' if live else ('flagged' if raw else 'absent')
    if live: bad.append((text, forbidden))
    print(f'{status:8s} {text!r:42s} {json.dumps(forbidden, ensure_ascii=False)}')
print(f'{len(NOT_READ) - len(bad)}/{len(NOT_READ)} correctly not read (absent or flagged)')
