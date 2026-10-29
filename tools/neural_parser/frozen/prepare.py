"""Prepare world-held-out extraction data; sealed/calibration gold is never read."""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import zipfile
from grammar import Grammar, canonical, KINDS, clauses

ARCHIVE_SHA='300623a5080ffb69eeb471e7069b88878f010059f73f002afee1995e00d99bc3'
TOKEN=re.compile(r'\d+(?:[.,]\d+)*|[\w]+(?:[-\u2019\'][\w]+)*|[^\w\s]',re.UNICODE)
def norm(s):return ' '.join(s.casefold().split())
def tokens(s):return [(m.group().casefold(),m.start(),m.end()) for m in TOKEN.finditer(s)]
def write_json(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')

def prepare(archive,out,lexicon_path):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    actual=hashlib.sha256(pathlib.Path(archive).read_bytes()).hexdigest()
    if actual!=ARCHIVE_SHA:raise ValueError('Unexpected archive SHA256')
    lex=json.loads(pathlib.Path(lexicon_path).read_text(encoding='utf-8-sig'))
    with zipfile.ZipFile(archive) as z:
        rows=[json.loads(x) for x in z.read('evaluation-data/realistic-training-mmr-20000/training.jsonl').splitlines()]
    pairs=sorted((s['name'],a) for s in lex['subjects'] for a in s['attributes'])
    pair_id={p:i+1 for i,p in enumerate(pairs)}
    # Predeclared whole-world split: no development world in train.
    dev=[r for r in rows if r['source_release'].endswith('/development-20000')]
    dev_texts={norm(r['input']['text']) for r in dev}
    train=[r for r in rows if not r['source_release'].endswith('/development-20000') and norm(r['input']['text']) not in dev_texts]
    extra_names=sorted({a['value']['value'] for r in train for a in r['target']['form'] if a['value']['kind']=='name'})
    grammar=Grammar(lex,extra_names)
    # Vocabulary includes public lexicon, then only TRAIN input text, never gold answers.
    counter=collections.Counter()
    for r in train:
        counter.update(t[0] for t in tokens(r['input']['text']))
        if r['input'].get('previous_row'):counter.update(t[0] for t in tokens(r['input']['previous_row']['text']))
    vocab={'<pad>':0,'<unk>':1,'<ctx>':2,'<current>':3}
    for word,count in counter.most_common():
        if count>=2:vocab.setdefault(word,len(vocab))
    chars={'<pad>':0,'<unk>':1}
    for word in vocab:
        for ch in word:chars.setdefault(ch,len(chars))
    meta={'archive_sha256':actual,'pairs':pairs,'vocab':vocab,'chars':chars,'kinds':KINDS,'split':'entire development-20000 world held out; matching train texts removed','train_worlds':sorted({r['world_id'] for r in train}),'dev_worlds':sorted({r['world_id'] for r in dev}),'context':'Only explicitly supplied previous_row; no CSV adjacency inference','max_tokens':384,'max_chars':24,'features':'No dates/world_id/evidence/verdict/expected_value in network input'}
    meta['extra_names']=extra_names
    write_json(out/'meta.json',meta);write_json(out/'lexicon.json',lex)
    reports={}
    for split,items in [('train',train),('dev',dev)]:
        stats=collections.Counter();miss=[]
        with (out/(split+'.jsonl')).open('w',encoding='utf-8') as f:
            for r in items:
                text=r['input']['text'];previous=(r['input'].get('previous_row') or {}).get('text','')
                # Keep up to 96 context tokens and all current text. Refuse silent truncation.
                ct=tokens(previous)[-96:];tt=tokens(text)
                seq=['<ctx>']+[x[0] for x in ct]+['<current>']+[x[0] for x in tt];offset=len(ct)+2
                if len(seq)>meta['max_tokens']:raise ValueError('max_tokens insufficient')
                cands=grammar.candidates(text)
                clause_spans=clauses(text)
                forms=r['target']['form'];spans=r['target']['assertion_spans'];aligned=set()
                for c in cands:
                    ix=[i+offset for i,(_,a,b) in enumerate(tt) if a<c['end'] and b>c['start']]
                    if not ix:raise ValueError('candidate has no tokens')
                    c['lo']=min(ix);c['hi']=max(ix)+1;c['kind']=KINDS.index(c['value']['kind']);c['label']=0
                    if c['value']['kind']=='boolean':c['kind']=8+int(c['value']['value'])
                    ca,cb=next(((a,b) for a,b in clause_spans if a<=c['start']<b),(0,len(text)))
                    ci=[i+offset for i,(_,a,b) in enumerate(tt) if a<cb and b>ca]
                    c['clo']=min(ci);c['chi']=max(ci)+1
                    # Byte offsets -> characters, including Euro/non-ASCII names.
                    for j,(atom,span) in enumerate(zip(forms,spans)):
                        a=len(text.encode()[:span['start']].decode());b=len(text.encode()[:span['end']].decode())
                        inside=(c['start']>=a and c['end']<=b+2)
                        if c['value']['kind']=='boolean':inside=max(0,min(c['end'],b)-max(c['start'],a))>=.85*(b-a)
                        if inside and canonical(c['value'])==canonical(atom['value']):
                            c['label']=pair_id[(atom['subject'],atom['attribute'])];aligned.add(j);break
                for j,atom in enumerate(forms):
                    stats['gold_'+atom['value']['kind']]+=1
                    if j in aligned:stats['covered_'+atom['value']['kind']]+=1
                    elif len(miss)<150:miss.append({'id':r['id'],'text':text,'atom':atom})
                stats['rows']+=1;stats['atoms']+=len(forms);stats['covered']+=len(aligned);stats['candidates']+=len(cands);stats['complete_rows']+=len(aligned)==len(forms)
                encoded={'id':r['id'],'world_id':r['world_id'],'text':text,'previous_text':previous,'form':forms,'tokens':[vocab.get(w,1) for w in seq],'chars':[[chars.get(ch,1) for ch in w[:24]] for w in seq],'candidates':cands,'current_offset':offset,'has_context':bool(previous)}
                f.write(json.dumps(encoded,ensure_ascii=False)+'\n')
        reports[split]=dict(stats);write_json(out/(split+'-misses.json'),miss)
    write_json(out/'preparation.json',reports)
    print(json.dumps(reports,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--out',required=True);p.add_argument('--lexicon',required=True);a=p.parse_args();prepare(a.archive,a.out,a.lexicon)
