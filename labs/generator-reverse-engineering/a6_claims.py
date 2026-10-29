"""A6 claim types: event mentions, two-subject rows, change and comparison phrasing; map rows onto the 5 claim types."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import re
from collections import Counter
from rev_common import load, V

rows, lex = load()
EV = set(lex['events'])
CHANGE = re.compile(r"\bfrom\b[^.]{0,40}\bto\b|\b(rose|rises|risen|dropped|drops|fell|falls|grew|grows|increased|decreased|climbed|jumped|"
                    r"doubled|halved|went up|went down|up from|down from|no longer|used to|anymore|was .{0,30} now|cut to|raised to|lowered to)\b", re.I)
NOW = re.compile(r"\bnow\b", re.I)
COMP = re.compile(r"\b(more than|less than|fewer than|cheaper than|faster than|slower than|bigger than|larger than|smaller than|"
                  r"higher than|lower than|same as|as many|as much|outnumber\w*|ahead of|behind|exceeds?|than)\b", re.I)
REL = re.compile(r"\b(CEO|CTO|headquarters|Series A lead|head of product|primary region|cloud provider|lead|led by|leads|city)\b", re.I)
EVPH = re.compile(r"\b(at|during|on the day of|by|before|after|ahead of|for)\s+(the\s+)?$", re.I)
c = Counter(); types = Counter(); ex = {}
for r in rows:
    ents = V.find_entities(r['text'], lex)
    names = {n for _, _, n in ents}
    gs = {f['subject'] for f in r['facts']}
    ev = names & EV - gs
    subj2 = len(names - EV) >= 2
    f = dict(event=bool(ev), two_subjects=subj2, change=bool(CHANGE.search(r['text'])), now=bool(NOW.search(r['text'])),
             compare=bool(COMP.search(r['text'])), relation_words=bool(REL.search(r['text'])),
             value_is_entity=any(f['value']['kind'] == 'name' and f['value']['value'] in lex['subjects'] for f in r['facts']))
    for k, v in f.items(): c[k] += v
    t = ('compare' if f['compare'] and subj2 else 'change' if f['change'] else 'at_event' if f['event'] else
         'relation' if subj2 and f['relation_words'] and not f['value_is_entity'] else 'fact')
    types[t] += 1; ex.setdefault(t, []).append(r['text'])
print('rows', len(rows), 'feature counts:', dict(c))
print('claim type mapping (priority compare > change > at_event > relation > fact):', dict(types))
for t, L in ex.items(): print(t, '|', ' || '.join(L[:4])[:400])
print('gold forms: every practice form is a list of plain facts (subject, attribute, value); none carries event, link, from/to or op between two facts')
