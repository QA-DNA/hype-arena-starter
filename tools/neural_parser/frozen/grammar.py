"""Text-only typed value candidates. No facts, gold spans or verdicts at inference."""
import calendar
import json
import re
from decimal import Decimal

KINDS = ['quantity', 'date', 'boolean', 'money', 'percent', 'duration', 'name', 'version']
ONES = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(20)))
TENS = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
WORDS = '|'.join([*ONES, *TENS])
NUM = rf'(?:-?\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|-?\d+(?:\.\d+)?|(?:{WORDS})(?:[- ](?:{WORDS}))?|a dozen|a hundred|an|a)'
NUMBER = re.compile(rf'(?<![\w.])(?P<n>{NUM})(?:\s*(?P<scale>million|billion|thousand|bn|k|(?-i:M)))?(?!\w)', re.I)
MONTHS = {name.casefold(): i for i in range(1, 13) for name in [calendar.month_name[i], calendar.month_abbr[i]]}
MONTHS['sept'] = 9
MONTH = '(?:' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?'
DURATIONS = {'ms':'ms','millisecond':'ms','s':'s','sec':'s','second':'s','min':'min','minute':'min','h':'h','hr':'h','hour':'h','d':'day','day':'day','wk':'week','week':'week','mo':'month','month':'month','yr':'year','year':'year'}
UNITS = {'gb':'GB','gigabyte':'GB','gig':'GB','mb':'MB','megabyte':'MB','tb':'TB','terabyte':'TB','kb':'KB','kilobyte':'KB','b':'B','byte':'B','mah':'mAh','w':'W','watt':'W','g':'g','gram':'g','kg':'kg','kilogram':'kg','km':'km','kilometre':'km','kilometer':'km','m':'m','metre':'m','meter':'m','in':'inch','inch':'inch','hz':'Hz','hertz':'Hz','ghz':'GHz','mhz':'MHz'}
CURRENCIES = {'€':'EUR','$':'USD','£':'GBP','eur':'EUR','euro':'EUR','usd':'USD','dollar':'USD','gbp':'GBP','lei':'RON','ron':'RON','chf':'CHF','cad':'CAD','aud':'AUD','jpy':'JPY','cny':'CNY','inr':'INR','pln':'PLN','czk':'CZK','huf':'HUF','sek':'SEK','nok':'NOK','dkk':'DKK'}
OPERATORS = [(r'(?:at least|no less than|not less than|no earlier than|no older than|>=|≥)\s*(?:the\s+)?$', 'ge'),(r'(?:at most|no more than|not more than|no later than|no newer than|up to|within|<=|≤)\s*(?:the\s+)?$','le'),(r'(?:more than|greater than|over|above|newer than|after|>)\s*(?:the\s+)?$','gt'),(r'(?:less than|fewer than|under|below|older than|before|<)\s*(?:the\s+)?$','lt')]

def canonical(value):
    v = dict(value)
    if v.get('op') == 'eq': v.pop('op')
    # Archive arithmetic leaves binary float noise (0.5800000000000001).
    # Numeric equivalence is explicitly separate from strict JSON equality.
    if isinstance(v.get('value'),(int,float)) and not isinstance(v['value'],bool):
        n=round(v['value'],9);v['value']=int(n) if n==int(n) else n
    return json.dumps(v, sort_keys=True, separators=(',', ':'))

def singular(word):
    w = word.casefold()
    if w in ['people', 'persons']: return 'person'
    if w.endswith('ies'): return w[:-3]+'y'
    if w.endswith('ches'): return w[:-2]
    if w.endswith('s') and not w.endswith('ss') and w not in {'ms','s'}: return w[:-1]
    return w

def number(text):
    t = text.casefold().replace(',', '')
    if t == 'a dozen': return 12
    if t == 'a hundred': return 100
    if t in {'a','an'}:return 1
    try:
        n = Decimal(t)
        return int(n) if n == int(n) else float(n)
    except Exception:
        return sum((ONES | TENS)[w] for w in re.split('[- ]',t))

def clauses(text):
    # Do not split decimal points, numeric grouping commas, or date commas.
    ends = list(re.finditer(r';\s*|[.!?](?=\s+[A-Z]|\s*$)\s*|,?\s+and\s+', text))
    start = 0
    spans = []
    for m in ends:
        if m.start()>start: spans.append((start,m.start()))
        start=m.end()
    if start<len(text):spans.append((start,len(text)))
    return spans

class Grammar:
    def __init__(self, lexicon, extra_names=()):
        self.lexicon = lexicon
        names = {}
        for s in lexicon['subjects']:
            for a in [s['name'], *s.get('aliases',[])]: names[a.casefold()] = s['name']
        # Named objects such as cities are also in the public lexicon when provided.
        for key in ['names','values']:
            for obj in lexicon.get(key,[]):
                if isinstance(obj,str): names[obj.casefold()] = obj
                elif isinstance(obj,dict) and 'name' in obj:
                    for a in [obj['name'],*obj.get('aliases',[])]:names[a.casefold()]=obj['name']
        for name in extra_names: names.setdefault(name.casefold(),name)
        self.names = names
        self.name_re = re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(x) for x in sorted(names,key=len,reverse=True))+r')(?!\w)',re.I)

    def candidates(self, text):
        result=[]; occupied=[]
        def add(start,end,value,priority=False):
            if value['kind'] in ['money','percent','quantity','duration','date','version']:
                before=text[max(0,start-28):start]
                for pattern,op in OPERATORS:
                    match=re.search(pattern,before,re.I)
                    if match:
                        if re.search(r'\b(after|before|earlier|later)\b',match.group()) and value['kind']!='date':continue
                        if re.search(r'\b(newer|older)\b',match.group()) and value['kind']!='version':continue
                        value=dict(value,op=op);break
                if re.search(r'\bgoes up to\s*$',before,re.I):value.pop('op',None)
                if value['kind']=='percent' and re.match(r'\s+SLA\b',text[end:]):value.pop('op',None)
            result.append({'start':start,'end':end,'value':value})
            if priority:occupied.append((start,end))
        def overlaps(a,b):return any(a<e and b>s for s,e in occupied)
        # Full dates precede generic numbers; text offsets are Python characters.
        for m in re.finditer(r'(?<!\d)(20\d{2}|19\d{2})-(\d{2})(?:-(\d{2}))?(?!\d)',text):
            add(*m.span(),{'kind':'date','value':m.group()},True)
        date_patterns = [rf'(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s*(?P<m>{MONTH})\s+(?P<y>\d{{4}})',rf'(?P<m>{MONTH})\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(?P<y>\d{{4}})']
        for pat in date_patterns:
            for m in re.finditer(pat,text,re.I):
                if not overlaps(*m.span()):add(*m.span(),{'kind':'date','value':f"{m['y']}-{MONTHS[m['m'].rstrip('.').casefold()]:02d}-{int(m['d']):02d}"},True)
        for m in re.finditer(rf'(?P<m>{MONTH})\s+(?P<y>\d{{4}})',text,re.I):
            if not overlaps(*m.span()):add(*m.span(),{'kind':'date','value':f"{m['y']}-{MONTHS[m['m'].rstrip('.').casefold()]:02d}"},True)
        for m in re.finditer(r'(?<!\w)(?:v|version\s+|ver\.\s*)(\d+(?:\.\d+)*)(?!\w)|(?<![\w.])(\d+\.\d+\.\d+(?:\.\d+)*)(?!\w|\.\d)',text,re.I):
            add(*m.span(),{'kind':'version','value':m.group(1) or m.group(2)},True)
        for m in re.finditer(r'(?<![\w.])\d+\.\d+(?!\w|\.\d)',text):
            if not overlaps(*m.span()) and re.search(r'\bversion\b[^;.!?]{0,35}$',text[:m.start()],re.I):
                add(*m.span(),{'kind':'version','value':m.group()},True)
            elif not overlaps(*m.span()) and re.search(r'[A-Z][A-Za-z]*(?:\s+CLI)?\s+$',text[:m.start()]):
                add(*m.span(),{'kind':'version','value':m.group()})
        for m in self.name_re.finditer(text):
            add(*m.span(),{'kind':'name','value':self.names[m.group().casefold()]})
        name_spans=[(c['start'],c['end']) for c in result if c['value']['kind']=='name']
        for m in re.finditer(r'(?<!\w)[A-Z][a-zA-Z-]+(?:\s+[A-Z][a-zA-Z-]+){0,3}(?!\w)',text):
            if not any(m.start()<b and m.end()>a for a,b in name_spans) and m.group() not in {'It','Its','They','The','My','Anyway','At','In','You','We','That','This','Please'}:
                raw=m.group();trim=re.match(r'(?:At|In|The|From|To)\s+',raw);skip=trim.end() if trim else 0
                add(m.start()+skip,m.end(),{'kind':'name','value':raw[skip:]})
        for m in NUMBER.finditer(text):
            if overlaps(*m.span()):continue
            start,end=m.span(); val=number(m['n'])
            if m['n'].casefold() in {'a','an'} and not re.search(r'\b(?:under|within|in|for|over|than|least|most|to|only|just|lasting)\s*$',text[max(0,start-15):start],re.I):continue
            if m['scale']:val*= {'million':1e6,'billion':1e9,'thousand':1e3,'bn':1e9,'k':1e3,'m':1e6}[m['scale'].casefold()]
            if isinstance(val,float) and val.is_integer():val=int(val)
            before=text[max(0,start-8):start];after=text[end:end+70]
            cm=re.search(r'(€|\$|£|\bEUR|\bUSD|\bGBP|\bCHF|\bRON|\bPLN|\bCZK|\bHUF|\bSEK|\bNOK|\bDKK|\bJPY|\bCNY|\bINR|\bCAD|\bAUD)\s*$',before,re.I)
            ca=re.match(r'\s*(euros?|dollars?|lei|EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD)\b',after,re.I)
            if cm or ca:
                currency=(cm.group(1) if cm else ca.group(1)).casefold().rstrip('s')
                v={'kind':'money','value':val,'currency':CURRENCIES[currency]}
                a=start-len(cm.group()) if cm else start;b=end+(ca.end() if ca else 0)
                period=re.match(r'\s*(?:(?:per (?:user|terabyte)|/seat)\s*)?(?:(?:per|a|each|/)\s*(month|mo|year|yr|week|day)|(?P<annual>annually|per annum)|(?P<monthly>monthly))\b',text[b:],re.I)
                if period:
                    p=period.group(1) or ('year' if period['annual'] else 'month');v['per']={'mo':'month','yr':'year'}.get(p.casefold(),p.casefold());b+=period.end()
                add(a,b,v);continue
            pm=re.match(r'\s*(%|percent\b|per cent\b)',after,re.I)
            if pm:add(start,end+pm.end(),{'kind':'percent','value':val});continue
            unit=re.match(r'(?:[-\s]*)([A-Za-z]+|["″])\b',after)
            if unit:
                raw=unit.group(1);u=singular(raw)
                if u in DURATIONS:add(start,end+unit.end(),{'kind':'duration','value':val,'unit':DURATIONS[u]})
                elif raw not in ['of','in','on','is','and','or','down','a','the','from','at','per','for']:
                    add(start,end+unit.end(),{'kind':'quantity','value':val,'unit':UNITS.get(u,{'meeting':'sitting'}.get(u,u))})
                    if u not in UNITS:
                        words=list(re.finditer(r'[A-Za-z]+',after))[:3]
                        for extra in words[1:]:
                            between=after[unit.end():extra.start()]
                            if re.search(r'[^A-Za-z\s-]',between):break
                            noun=singular(extra.group())
                            if noun in {'is','has','ha','and','or','in','at','for','per','on','a','of','the','it','its','down','to','with','from'}:break
                            add(start,end+extra.end(),{'kind':'quantity','value':val,'unit':UNITS.get(noun,noun)})
            if isinstance(val,int) and 1900<=val<=2099 and not m['scale'] and ',' not in m['n']:
                add(start,end,{'kind':'date','value':str(val)})
        # One positive and negative boolean proposal per independently parsed clause.
        for start,end in clauses(text):
            for val in [True,False]:add(start,end,{'kind':'boolean','value':val})
        unique={ (c['start'],c['end'],canonical(c['value'])):c for c in result }
        return sorted(unique.values(),key=lambda c:(c['start'],c['end'],canonical(c['value'])))
