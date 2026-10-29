"""Streaming input-only preparation and scoring for the million development pool.

The bridge processes features/ only. Annotation sidecars are never mounted there.
No original dataset generator, oracle or frozen-bank code is imported.
"""
from __future__ import annotations
import argparse,collections,csv,gzip,hashlib,json,shutil,time
from decimal import Decimal
from pathlib import Path
from protocol import Protocol,ProtocolError,leaves,kleene

ROOT=Path(__file__).resolve().parents[2]
LABELS=('true','false','unsure')
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def write(stream,v):stream.write(canonical(v)+'\n')
def rows(path):
    with gzip.open(path,'rt',encoding='utf-8') if path.suffix=='.gz' else path.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():yield json.loads(line)
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def checked_output(path):
    path=path.resolve()
    if not path.is_relative_to(ROOT/'artifacts'):raise ValueError('Write only ignored evaluation artifacts')
    return path

class Requests:
    def __init__(self):self.items={};self.keys={}
    def add(self,mode,text,date,previous=''):
        key=(mode,text,date,previous)
        if key not in self.keys:
            rid=f'r{len(self.keys):07d}';self.keys[key]=rid
            self.items[rid]={'id':rid,'mode':mode,'text':text,'date':date,'previous_text':previous}
        return self.keys[key]

def prepare(dataset,out):
    out=checked_output(out);out.mkdir(parents=True,exist_ok=False)
    features=out/'features';features.mkdir();scoring=out/'scoring';scoring.mkdir()
    lexicon=json.loads((dataset/'lexicon.json').read_text(encoding='utf-8'))
    vocabulary=json.loads((dataset.parent/'labs/semantic-million/render-contract.json').read_text(encoding='utf-8'))
    with (ROOT/'data/practice.csv').open(encoding='utf-8-sig',newline='') as f:
        source_attributes={r['id']:{a['attribute'] for a in json.loads(r['form'] or '[]')} for r in csv.DictReader(f)}
    protocol=Protocol(lexicon,vocabulary,source_attributes);requests=Requests();counts=collections.Counter();errors=collections.Counter();started=time.perf_counter()
    shutil.copyfile(ROOT/'data/practice.csv',features/'practice.csv')
    with gzip.open(features/'plans.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as plans,gzip.open(scoring/'targets.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as targets:
        for row in rows(dataset/'pool.jsonl.gz'):
            inp=row['input'];plan={'id':row['id']}
            if inp.get('evidence_policy')=='provided_notes_only':
                plan['kind']='provided';counts['provided']+=1
                try:
                    tree=protocol.parse(inp)
                    for leaf in leaves(tree):
                        if leaf['type']=='recorded':leaf['request_id']=requests.add('literal',leaf['literal'],leaf['reference']['date'])
                    context=[]
                    for note in inp.get('context',[]):
                        if note.get('role')=='evidence':context.append({'source_id':note['id'],'date':note['date'],'request_id':requests.add('note',note['text'],note['date'])})
                    plan.update(tree=tree,context=context)
                except (ProtocolError,ValueError,KeyError) as error:
                    plan.update(error=str(error));errors[str(error)]+=1
            else:
                plan['kind']='pilot';counts['pilot']+=1
                plan['request_none']=requests.add('pilot',inp['text'],inp['date'])
                previous='\n'.join(n['text'] for n in inp.get('context',[])[-3:])
                plan['request_context']=requests.add('pilot',inp['text'],inp['date'],previous)
            write(plans,plan)
            write(targets,{'id':row['id'],'target':row['target'],'metadata':row.get('metadata',{})})
            counts['rows']+=1
            if counts['rows']%100000==0:print(canonical({'prepared':counts['rows'],'requests':len(requests.items),'seconds':time.perf_counter()-started}),flush=True)
    with (features/'requests.jsonl').open('w',encoding='utf-8') as f:
        for row in requests.items.values():write(f,row)
    result={'counts':dict(counts),'requests':len(requests.items),'request_modes':dict(collections.Counter(r['mode'] for r in requests.items.values())),'protocol_errors':dict(errors),'seconds':time.perf_counter()-started,'policy':'Only input text/date/context and declared evidence_policy become features; targets/metadata stay in scoring/.'}
    save(out/'preparation.json',result);print(canonical(result),flush=True)

class PairRequests:
    def __init__(self):self.keys={};self.items={}
    def add(self,left,right,op,semantics):
        key=canonical([left,right,op,semantics])
        if key not in self.keys:
            pid=f'c{len(self.keys):07d}';self.keys[key]=pid;self.items[pid]={'id':pid,'left':left,'right':right,'op':op,'semantics':semantics}
        return self.keys[key]

def plans(out):return rows(out/'features/plans.jsonl.gz')
def load_parsed(out):return {r['id']:r['parsed'] for r in rows(out/'parsed/parsed.jsonl')}
def fact_for(reference,context,parsed):
    found=[]
    for note in context:
        if note['date']!=reference['date']:continue
        # A source-ID supplied in an ordinal declaration is authoritative binding.
        if reference.get('source_id') and note['source_id']!=reference['source_id']:continue
        for fact in parsed[note['request_id']]['facts']:
            if fact['subject']==reference['subject'] and fact['attribute']==reference['attribute']:
                found.append((note['source_id'],fact))
    values={canonical(f['value']) for _,f in found}
    if len(values)!=1:return None,None
    source_ids={sid for sid,_ in found}
    return next(iter(source_ids)) if len(source_ids)==1 else None,found[0][1]

def make_pairs(out):
    out=checked_output(out);parsed=load_parsed(out);pairs=PairRequests();counter=collections.Counter();started=time.perf_counter()
    with gzip.open(out/'features/evaluable-plans.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as stream:
        for plan in plans(out):
            if plan['kind']=='provided' and 'tree' in plan:
                for leaf in leaves(plan['tree']):
                    if leaf['type']=='recorded':
                        sid,fact=fact_for(leaf['reference'],plan['context'],parsed)
                        proposals=parsed[leaf['request_id']]['facts']
                        chosen=[f for f in proposals if f['subject']==leaf['reference']['subject'] and f['attribute']==leaf['reference']['attribute']]
                        leaf['source_id']=sid
                        if len(chosen)==1:leaf['value']=chosen[0]['value']
                        if fact is not None and len(chosen)==1:leaf['comparison_id']=pairs.add(fact['value'],chosen[0]['value'],'eq','recorded')
                        else:counter['unresolved_recorded_leaves']+=1
                    else:
                        left_id,left=fact_for(leaf['left'],plan['context'],parsed);right_id,right=fact_for(leaf['right'],plan['context'],parsed)
                        leaf.update(left_id=left_id,right_id=right_id)
                        if left is not None and right is not None:leaf['comparison_id']=pairs.add(left['value'],right['value'],leaf['op'],'compare')
                        else:counter['unresolved_comparison_leaves']+=1
                plan.pop('context',None)
            write(stream,plan);counter['rows']+=1
            if counter['rows']%100000==0:print(canonical({'planned':counter['rows'],'typed_pairs':len(pairs.items),'seconds':time.perf_counter()-started}),flush=True)
    with (out/'features/pairs.jsonl').open('w',encoding='utf-8') as f:
        for item in pairs.items.values():write(f,item)
    result={'counts':dict(counter),'typed_pairs':len(pairs.items),'seconds':time.perf_counter()-started};save(out/'planning.json',result);print(canonical(result),flush=True)

def normalized_facts(value):
    # Comparison only in the scorer; no annotation enters the inference adapter.
    def key(v):
        if isinstance(v,dict):return ('object',tuple((k,key(x)) for k,x in sorted(v.items())))
        if isinstance(v,list):return ('list',tuple(key(x) for x in v))
        if type(v) in (int,float):return ('number',Decimal(str(v)))
        return (type(v).__name__,v)
    if isinstance(value,list):return sorted({key(v) for v in value})
    return []
def projected_structure(node):
    kind=node['type']
    if kind in ('all','any'):return {'type':kind,'children':[projected_structure(c) for c in node['children']]}
    if kind=='not':return {'type':'not','child':projected_structure(node['child'])}
    if kind=='compare':return {'type':kind,'left':node.get('left_id') or node['left'].get('source_id'),'right':node.get('right_id') or node['right'].get('source_id'),'op':node['op']}
    ref=node['reference']
    return {'type':'recorded','subject':ref['subject'],'attribute':ref['attribute'],'date':ref['date'],'source_id':node.get('source_id') or ref.get('source_id'),'value':node.get('value')}

class Metrics:
    def __init__(self):self.confusion={a:{b:0 for b in LABELS} for a in LABELS};self.counts=collections.Counter();self.gold=collections.Counter()
    def add(self,expected,predicted):
        self.counts['rows']+=1
        if expected is None:self.counts['null_label_rows']+=1;return
        self.confusion[expected][predicted]+=1;self.gold[expected]+=1;self.counts['label_rows']+=1;self.counts['correct']+=expected==predicted;self.counts['answered']+=predicted!='unsure';self.counts['answered_correct']+=predicted!='unsure' and expected==predicted
    def result(self):
        per={}
        for a in LABELS:
            tp=self.confusion[a][a];support=sum(self.confusion[a].values());total=sum(self.confusion[b][a] for b in LABELS)
            p=tp/total if total else 0;r=tp/support if support else 0
            per[a]={'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0,'support':support}
        n=self.counts['label_rows'];answered=self.counts['answered']
        return {'counts':dict(self.counts),'accuracy':self.counts['correct']/n if n else None,'macro_f1':sum(v['f1'] for v in per.values())/3,'coverage':answered/n if n else None,'answered_accuracy':self.counts['answered_correct']/answered if answered else None,'majority_baseline':max(self.gold.values())/n if n else None,'confusion':self.confusion,'per_label':per}

def score(out):
    out=checked_output(out);parsed=load_parsed(out);pairs={r['id']:r['label'] for r in rows(out/'parsed/comparisons.jsonl')};metrics={};parsing=collections.Counter();errors=[];started=time.perf_counter()
    def metric(name):return metrics.setdefault(name,Metrics())
    with gzip.open(out/'predictions.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as predictions:
        for plan,gold in zip(rows(out/'features/evaluable-plans.jsonl.gz'),rows(out/'scoring/targets.jsonl.gz'),strict=True):
            if plan['id']!=gold['id']:raise ValueError('Prediction/annotation identity mismatch')
            target=gold['target'];metadata=gold['metadata'];expected=target['label'];kind=plan['kind'];record={'id':plan['id'],'kind':kind}
            if kind=='provided':
                predicted=kleene(plan['tree'],lambda leaf:pairs.get(leaf.get('comparison_id'),'unsure')) if 'tree' in plan else 'unsure'
                structure=projected_structure(plan['tree']) if 'tree' in plan else None
                parsing['provided_rows']+=1;parsing['provided_protocol_parsed']+='tree' in plan;parsing['provided_exact_ast']+=structure==target['structure']
                record.update(label=predicted,protocol_parsed='tree' in plan)
            else:
                a=parsed[plan['request_none']];b=parsed[plan['request_context']]
                predicted=b.get('label','unsure');record.update(label=predicted,no_context_label=a.get('label','unsure'))
                metric('pilot_no_context').add(expected,a.get('label','unsure'))
                parsing['pilot_rows']+=1
                if target['structure']['type']=='assertions':
                    parsing['pilot_assertion_rows']+=1
                    parsing['pilot_assertion_exact_no_context']+=normalized_facts(a['facts'])==normalized_facts(target['structure']['assertions'])
                    parsing['pilot_assertion_exact_context']+=normalized_facts(b['facts'])==normalized_facts(target['structure']['assertions'])
                else:parsing['pilot_other_structure:'+target['structure']['type']]+=1
            metric('all').add(expected,predicted);metric(kind).add(expected,predicted)
            metric('schema:'+str(metadata.get('task_schema',kind))).add(expected,predicted)
            metric('profile:'+str(metadata.get('profile_id','pilot'))).add(expected,predicted)
            metric('family:'+str(metadata.get('family',metadata.get('profile_id',kind)))).add(expected,predicted)
            if len(errors)<150 and expected is not None and expected!=predicted:errors.append({'id':plan['id'],'expected':expected,'predicted':predicted,'kind':kind})
            write(predictions,record)
    report={'scope':'Development pool, practice-derived sources; protocol-adapted note logic is distinct from the unmodified competition CLI. No training or target/proof features.','metrics':{k:v.result() for k,v in metrics.items()},'parsing':dict(parsing),'first_errors':errors,'seconds_scoring':time.perf_counter()-started,'model':'selected-v2 + committed schema binder + exact Rust typed kernel; pilot production GBT, predeclared no-context and provided-previous3 ablations'}
    save(out/'score.json',report);print(canonical({'all':report['metrics']['all'],'pilot':report['metrics']['pilot'],'provided':report['metrics']['provided'],'parsing':report['parsing']}),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','pairs','score']);p.add_argument('--dataset',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.mode=='prepare':prepare(a.dataset.resolve(),a.out)
    elif a.mode=='pairs':make_pairs(a.out)
    else:score(a.out)
if __name__=='__main__':main()
