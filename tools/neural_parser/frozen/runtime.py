"""Offline ONNX CPU runtime. Predictor inputs contain text/context only."""
import argparse
import json
import pathlib
import sys
import numpy as np
from grammar import Grammar, KINDS, clauses, canonical
from prepare import tokens

INPUT_NAMES=['words','chars','spans','clauses','kinds']

def encode_input(text, previous, meta, grammar, row_id=''):
    ct=tokens(previous)[-96:];tt=tokens(text)
    seq=['<ctx>']+[t[0] for t in ct]+['<current>']+[t[0] for t in tt];offset=len(ct)+2
    if len(seq)>meta['max_tokens']:raise ValueError('Input exceeds the supported 384 tokens; no silent truncation')
    candidates=grammar.candidates(text);cs=clauses(text)
    for c in candidates:
        ix=[i+offset for i,(_,a,b) in enumerate(tt) if a<c['end'] and b>c['start']]
        if not ix:raise ValueError('Candidate has no token span')
        c['lo']=min(ix);c['hi']=max(ix)+1;c['kind']=KINDS.index(c['value']['kind'])
        if c['value']['kind']=='boolean':c['kind']=8+int(c['value']['value'])
        ca,cb=next(((a,b) for a,b in cs if a<=c['start']<b),(0,len(text)))
        ci=[i+offset for i,(_,a,b) in enumerate(tt) if a<cb and b>ca]
        c['clo']=min(ci);c['chi']=max(ci)+1
    return {'id':row_id,'text':text,'previous_text':previous,'tokens':[meta['vocab'].get(w,1) for w in seq],'chars':[[meta['chars'].get(ch,1) for ch in w[:24]] for w in seq],'candidates':candidates,'current_offset':offset,'has_context':bool(previous)}

def numpy_batch(rows):
    b=len(rows);t=max(len(r['tokens']) for r in rows);c=max(1,max(len(r['candidates']) for r in rows))
    words=np.zeros((b,t),np.int64);chars=np.zeros((b,t,24),np.int64);spans=np.zeros((b,c,t),np.float32);clause=np.zeros_like(spans);kinds=np.zeros((b,c),np.int64)
    for i,r in enumerate(rows):
        words[i,:len(r['tokens'])]=r['tokens']
        for j,w in enumerate(r['chars']):chars[i,j,:len(w)]=w
        for j,v in enumerate(r['candidates']):
            spans[i,j,v['lo']:v['hi']]=1/(v['hi']-v['lo']);clause[i,j,v['clo']:v['chi']]=1/(v['chi']-v['clo']);kinds[i,j]=v['kind']
    return dict(zip(INPUT_NAMES,[words,chars,spans,clause,kinds]))

def decode(rows,logits,pairs,threshold=.5):
    prob=np.exp(logits-logits.max(-1,keepdims=True));prob/=prob.sum(-1,keepdims=True)
    result=[]
    for i,r in enumerate(rows):
        pred=[];seen=set()
        for j,c in enumerate(r['candidates']):
            label=int(prob[i,j].argmax());score=float(prob[i,j,label])
            if label==0 or score<threshold:continue
            s,a=pairs[label-1];atom={'subject':s,'attribute':a,'value':c['value']};key=(s,a,canonical(c['value']))
            if key in seen:continue
            seen.add(key)
            pred.append({'atom':atom,'model_score':score,'value_span_chars':[c['start'],c['end']],'value_text':r['text'][c['start']:c['end']]})
        result.append(pred)
    return result

class CpuExtractor:
    def __init__(self,bundle,model='model.onnx',threads=2):
        import onnxruntime as ort
        root=pathlib.Path(bundle);self.meta=json.loads((root/'meta.json').read_text());self.lexicon=json.loads((root/'lexicon.json').read_text());self.grammar=Grammar(self.lexicon,self.meta['extra_names'])
        opt=ort.SessionOptions();opt.intra_op_num_threads=threads;opt.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(root/model),sess_options=opt,providers=['CPUExecutionProvider']);self.inputs={i.name for i in self.session.get_inputs()}
    def predict_encoded(self,rows):
        feed=numpy_batch(rows);logits=self.session.run(None,{k:v for k,v in feed.items() if k in self.inputs})[0]
        return decode(rows,logits,self.meta['pairs'])
    def extract(self,text,previous=''):
        row=encode_input(text,previous,self.meta,self.grammar);p=self.predict_encoded([row])[0];atoms=[a['atom'] for a in p]
        return {'form':atoms,'assertions':p,'subjects':sorted({a['subject'] for a in atoms}),'relations':[{'subject':a['subject'],'attribute':a['attribute'],'object':a['value']['value']} for a in atoms if a['value']['kind']=='name'],'context_supplied':bool(previous),'truth_verdict':None,'score_semantics':'uncalibrated extraction score; not truth confidence'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--text');p.add_argument('--previous',default='');p.add_argument('--model',default='model.onnx');a=p.parse_args();engine=CpuExtractor(a.bundle,a.model)
    if a.text is not None:print(json.dumps(engine.extract(a.text,a.previous),ensure_ascii=False,indent=2))
    else:
        for line in sys.stdin:
            req=json.loads(line);print(json.dumps(engine.extract(req['text'],req.get('previous_text','')),ensure_ascii=False),flush=True)
