"""Shared helpers for the /tmp/veridyct-rev analyses: load practice rows (harness), template a sentence.
Reuses harness.py (rows, pages, gold forms) and w7/values.py (typed values, entity mentions); nothing is re-implemented."""
import re, sys
sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w7')
import harness as H, values as V

PH = dict(quantity='<QTY>', money='<MONEY>', duration='<DUR>', percent='<PCT>', date='<DATE>', version='<VER>', name='<NAME>')

def load():
    rows, lex = H.load()
    lex['events_set'] = set(lex['events'])
    return rows, lex

def spans(r, lex):
    """Non-overlapping (start, end, placeholder) spans: gold subject -> <SUBJ>, other lexicon subject -> <ENT>,
    event -> <EVENT>, every typed value (values.py, not flagged alt/boolean) -> <QTY>/<MONEY>/... (gold name -> <NAME>)."""
    t = r['text']
    subj = {f['subject'] for f in r['facts']}
    gold_names = {f['value']['value'] for f in r['facts'] if f['value']['kind'] == 'name'}
    cand = []
    for s, e, name in V.find_entities(t, lex):
        ph = '<SUBJ>' if name in subj else '<NAME>' if name in gold_names else '<EVENT>' if name in lex['events_set'] else '<ENT>'
        cand.append((s, e, ph, 2))
    for c in V.extract_values(t, lex):
        if c['kind'] == 'boolean' or 'alt' in c['flags']: continue
        if c['kind'] == 'name' and c['rule'] == 'name_lexicon': continue  # already an entity span
        if c['kind'] == 'name' and c['value']['value'] not in gold_names: continue  # capitalised word, not a value
        cand.append((c['start'], c['end'], PH[c['kind']], 1))
    cand.sort(key=lambda x: (-(x[1] - x[0]), x[3], x[0]))  # longest first, entity wins a tie
    taken, out = [], []
    for s, e, ph, _ in cand:
        if any(s < b and a < e for a, b in taken): continue
        taken.append((s, e)); out.append((s, e, ph))
    return sorted(out)

def template(r, lex):
    t, out, last = r['text'].replace('’', "'"), [], 0
    for s, e, ph in spans(r, lex):
        out.append(t[last:s]); out.append(ph); last = e
    out.append(t[last:])
    return ''.join(out)

def loose(tpl):
    """Looser normalisation on top of the template: lower-case, digits -> 0, punctuation dropped, spaces collapsed."""
    t = re.sub(r'<([a-z]+)>', lambda m: f' ph{m.group(1)} ', tpl.lower())
    t = re.sub(r'\d', '0', t)
    t = re.sub(r"[^\w\s]", ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

CONV = {'ms': ('s', 1e-3), 's': ('s', 1), 'min': ('s', 60), 'h': ('s', 3600), 'day': ('s', 86400), 'week': ('s', 604800),
        'B': ('B', 1), 'KB': ('B', 1e3), 'MB': ('B', 1e6), 'GB': ('B', 1e9), 'TB': ('B', 1e12), 'mm': ('m', 1e-3), 'cm': ('m', 1e-2),
        'm': ('m', 1), 'km': ('m', 1e3), 'g': ('g', 1), 'kg': ('g', 1e3), 'Hz': ('Hz', 1), 'kHz': ('Hz', 1e3), 'MHz': ('Hz', 1e6),
        'GHz': ('Hz', 1e9), 'mW': ('W', 1e-3), 'W': ('W', 1), 'kW': ('W', 1e3)}
def canon(v):
    """(dimension key, comparable value): units convert (contract), op kept in the key, dates as text, versions as int tuples."""
    k = v['kind']
    if k in ('quantity', 'duration'):
        u, m = CONV.get(v.get('unit'), (v.get('unit'), 1)); return (k, u, v.get('op')), round(float(v['value']) * m, 9)
    if k == 'money': return (k, v.get('currency'), v.get('per'), v.get('op')), float(v['value'])
    if k == 'percent': return (k, v.get('op')), float(v['value'])
    if k == 'version': return (k,), tuple(int(x) for x in str(v['value']).split('.') if x.isdigit())
    return (k,), v['value']

if __name__ == '__main__':
    rows, lex = load()
    r = rows[0]
    assert template(r, lex) == '<SUBJ> started at <ENT> on <DATE>.', template(r, lex)
    assert loose('<SUBJ> has 4 <QTY>!') == 'phsubj has 0 phqty', loose('<SUBJ> has 4 <QTY>!')
    assert canon({'kind': 'duration', 'value': 2, 'unit': 'week'}) == canon({'kind': 'duration', 'value': 14, 'unit': 'day'})
    print('ok')
