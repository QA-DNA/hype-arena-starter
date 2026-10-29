"""TEST ONLY: compare the adapter's exact arithmetic with the supplied oracle.

The oracle and bank are used exclusively to create an isolated expected-answer
sidecar. Neither is imported by the benchmark inference or protocol code.
"""
import argparse,importlib.util,itertools,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','score']);p.add_argument('--dataset',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.mode=='prepare':
        a.out.mkdir(parents=True,exist_ok=False);(a.out/'features').mkdir();(a.out/'scoring').mkdir()
        source=a.dataset.parent/'labs/semantic-million/oracle.py';spec=importlib.util.spec_from_file_location('unit_expected_only',source);oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
        bank=json.loads((a.dataset/'frozen-bank.json').read_text(encoding='utf-8'));values=[r['form'][0]['value'] for r in bank.values()];count=0
        with (a.out/'features/pairs.jsonl').open('w',encoding='utf-8') as inputs,(a.out/'scoring/expected.jsonl').open('w',encoding='utf-8') as expected:
            def emit(left,right,op,semantics,label):
                nonlocal count
                rid=f't{count:07d}';inputs.write(json.dumps({'id':rid,'left':left,'right':right,'op':op,'semantics':semantics})+'\n');expected.write(json.dumps({'id':rid,'label':label})+'\n');count+=1
            for left,right in itertools.combinations(values,2):
                for op in ('eq','lt','le','gt','ge'):
                    try:label=oracle.compare_values(left,right,op)
                    except ValueError:continue
                    emit(left,right,op,'compare',label)
            print('Compatible public-source comparison tests',count)
            q=lambda x,u:{'kind':'quantity','value':x,'unit':u}
            emit(q(1,'MB'),q(1000,'KB'),'eq','recorded','false')
            emit(q(1,'MB'),q(1000,'KB'),'eq','compare','true')
            emit(q(1,'user'),q(1.0,'user'),'eq','recorded','true')
            emit(q(9007199254740993,'user'),q(9007199254740992,'user'),'gt','compare','true')
            emit({'kind':'date','value':'2026'},{'kind':'date','value':'2026-01-01'},'eq','recorded','false')
            emit({'kind':'version','value':'2.3'},{'kind':'version','value':'2.3.0'},'eq','recorded','false')
        print('Total tests',count)
    else:
        expected={r['id']:r['label'] for r in map(json.loads,(a.out/'scoring/expected.jsonl').read_text().splitlines())}
        actual=list(map(json.loads,(a.out/'parsed/comparisons.jsonl').read_text().splitlines()));errors=[{'id':r['id'],'expected':expected[r['id']],'actual':r['label']} for r in actual if r['label']!=expected[r['id']]]
        report={'tests':len(expected),'outputs':len(actual),'mismatches':len(errors),'first_errors':errors[:20],'scope':'Comparison/literal protocol unit tests only; no benchmark expected answers in solver input.'}
        (a.out/'parity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
        if errors or len(actual)!=len(expected):raise SystemExit(1)
if __name__=='__main__':main()
