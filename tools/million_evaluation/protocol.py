"""Public note-query protocol adapter. No annotations, oracle or bank imports.

This adds a declared grammar/logic interface to the existing value/evidence kernel;
it must be reported separately from the unmodified competition CLI.
"""
from __future__ import annotations
import re
from datetime import date

WORDS = dict(zip(('one','two','three','four','five','six','seven','eight'), range(1,9)))
MONTHS = {name.casefold(): i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
PREDICATES={'no higher than':'le','no lower than':'ge','no earlier than':'ge','no later than':'le','on the same day as':'eq','equal to':'eq','lower than':'lt','higher than':'gt','earlier than':'lt','later than':'gt'}

class ProtocolError(ValueError): pass

def natural_date(text):
    text=text.strip().rstrip('.')
    m=re.fullmatch(r'(\d{1,2})(?:st|nd|rd|th)? (\w+) (\d{4})',text,re.I)
    if not m or m[2].casefold() not in MONTHS: raise ProtocolError('Unsupported reference date')
    return date(int(m[3]),MONTHS[m[2].casefold()],int(m[1])).isoformat()

class Protocol:
    def __init__(self,lexicon,render_vocabulary,source_attributes=None):
        self.subjects={}
        self.fields={}
        self.legal={}
        for item in lexicon['subjects']:
            name=item['name'];self.legal[name]=set(item['attributes'])
            for a in [name,*item.get('aliases',[])]:self.subjects.setdefault(a.casefold(),set()).add(name)
            for a in item['attributes']:
                for phrase in [a,a.replace('_',' '),render_vocabulary.get('attributes',{}).get(a,a.replace('_',' '))]:
                    self.fields.setdefault(phrase.casefold(),set()).add(a)
        # The public rendering contract also documents source-specific field
        # names. Learn only their attribute names from the already-public
        # practice annotations; never read per-query targets or a hidden bank.
        for sid,phrase in render_vocabulary.get('source_attribute_words',{}).items():
            attrs=(source_attributes or {}).get(sid,set())
            if len(attrs)==1:self.fields.setdefault(phrase.casefold(),set()).update(attrs)

    def descriptor(self,who,field,when,source_id=None):
        owners=self.subjects.get(who.strip().casefold(),set())
        phrase=field.strip().casefold();attrs=self.fields.get(phrase,set())
        if not attrs and phrase.endswith(' status'):attrs=self.fields.get(phrase.removesuffix(' status'),set())
        candidates=[(s,a) for s in owners for a in attrs if a in self.legal[s]]
        if len(candidates)!=1:raise ProtocolError('Unresolved subject/attribute descriptor')
        s,a=candidates[0]
        return {'subject':s,'attribute':a,'date':natural_date(when),'source_id':source_id}

    def bindings(self,context):
        bindings={}
        for note in context:
            if note.get('role')!='discourse':continue
            m=re.fullmatch(r"Here, note (\w+) means the note about (.+?)'s (.+?) dated (.+)\.",note.get('text',''),re.I)
            if not m:continue
            ordinal=m[1].casefold()
            source_id=note.get('id','').removeprefix('binding-') if note.get('id','').startswith('binding-') else None
            value=self.descriptor(m[2],m[3],m[4],source_id)
            if ordinal in bindings and bindings[ordinal]!=value:raise ProtocolError('Ambiguous ordinal declaration')
            bindings[ordinal]=value
        return bindings

    def reference(self,text,bindings):
        m=re.fullmatch(r'the value in note (\w+)',text,re.I)
        if m:
            if m[1].casefold() not in bindings:raise ProtocolError('Missing ordinal declaration')
            return bindings[m[1].casefold()].copy()
        m=re.fullmatch(r"the value recorded for (.+?)'s (.+?) on (.+)",text,re.I)
        if not m:raise ProtocolError('Unknown comparison reference')
        return self.descriptor(*m.groups())

    def leaf(self,text,bindings):
        m=re.fullmatch(r'(.+?) is ('+'|'.join(map(re.escape,sorted(PREDICATES,key=len,reverse=True)))+r') (.+)',text,re.I)
        if m:return {'type':'compare','left':self.reference(m[1],bindings),'right':self.reference(m[3],bindings),'op':PREDICATES[m[2].casefold()]}
        m=re.fullmatch(r'note (\w+) records (.+) for that entry',text,re.I)
        if m:
            if m[1].casefold() not in bindings:raise ProtocolError('Missing ordinal declaration')
            desc=bindings[m[1].casefold()].copy();value=m[2]
        else:
            patterns=[
                r"the entry for (?P<who>.+?)'s (?P<field>.+?) in the note of (?P<when>.+?) reads (?P<value>.+)",
                r"the note about (?P<who>.+?) dated (?P<when>.+?) gives (?P<value>.+?) for the (?P<field>.+?) entry",
                r"on (?P<when>[^,]+), the entry for (?P<who>.+?)'s (?P<field>.+?) is recorded as (?P<value>.+)",
                r"the (?P<field>.+?) entry for (?P<who>.+?) is listed as (?P<value>.+?) in the note dated (?P<when>.+)"]
            match=next((m for p in patterns if (m:=re.fullmatch(p,text,re.I))),None)
            if match is None:raise ProtocolError('Unknown recorded-value clause')
            desc=self.descriptor(match['who'],match['field'],match['when']);value=match['value']
        literal=f"{desc['subject']}'s {desc['attribute']} is {value}."
        return {'type':'recorded','reference':desc,'literal':literal,'value_text':value}

    def parse(self,inp):
        if inp.get('evidence_policy')!='provided_notes_only':raise ProtocolError('Not the supplied-notes protocol')
        text=inp['text'];prefix='Using only the supplied notes, '
        if len(text)>65536 or not text.startswith(prefix):raise ProtocolError('Unsupported query prefix or length')
        bindings=self.bindings(inp.get('context',[]));nodes=0
        def whitespace(i):
            while i<len(text) and text[i].isspace():i+=1
            return i
        def expression(i,depth=0):
            nonlocal nodes
            nodes+=1;i=whitespace(i)
            if depth>16 or nodes>64:raise ProtocolError('Program size/depth limit')
            for lead,op in [('all of these statements are true:','all'),('at least one of these statements is true:','any')]:
                if text.startswith(lead,i):
                    i=whitespace(i+len(lead));children=[]
                    while i<len(text) and text[i]=='(':
                        child,i=expression(i+1,depth+1);i=whitespace(i)
                        if i>=len(text) or text[i]!=')':raise ProtocolError('Missing closing parenthesis')
                        children.append(child);i=whitespace(i+1)
                        if i<len(text) and text[i]==';':i=whitespace(i+1)
                        else:break
                    if not children:raise ProtocolError('Empty logical group')
                    return {'type':op,'children':children},i
            lead='it is not true that ('
            if text.startswith(lead,i):
                child,j=expression(i+len(lead),depth+1);j=whitespace(j)
                if j>=len(text) or text[j]!=')':raise ProtocolError('Missing negation parenthesis')
                return {'type':'not','child':child},j+1
            end=text.find(')',i)
            if end<0:raise ProtocolError('Ungrouped leaf')
            return self.leaf(text[i:end].strip(),bindings),end
        tree,end=expression(len(prefix))
        if not text[end:].startswith('.'):raise ProtocolError('Unconsumed logical text')
        return tree

def leaves(tree):
    if tree['type'] in ('all','any'):
        for child in tree['children']:yield from leaves(child)
    elif tree['type']=='not':yield from leaves(tree['child'])
    else:yield tree

def kleene(tree,lookup):
    kind=tree['type']
    if kind=='not':return {'true':'false','false':'true','unsure':'unsure'}[kleene(tree['child'],lookup)]
    if kind not in ('all','any'):return lookup(tree)
    values=[kleene(c,lookup) for c in tree['children']]
    if kind=='all':return 'false' if 'false' in values else 'unsure' if 'unsure' in values else 'true'
    return 'true' if 'true' in values else 'unsure' if 'unsure' in values else 'false'
