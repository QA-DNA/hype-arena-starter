"""Reuse deterministic extraction only; evidence availability is always per row.

Keys contain mode, full text, date and full explicit prior text. Labels, targets,
IDs, profile/case metadata and the existence of any cached fact are not evidence.
"""
import argparse,json
from pathlib import Path

def read(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]
def key(row):return tuple(row[k] for k in ('mode','text','date','previous_text'))
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','merge']);p.add_argument('--from-run',type=Path,required=True);p.add_argument('--to-run',type=Path,required=True);a=p.parse_args()
    old_requests={r['id']:r for r in read(a.from_run/'features/requests.jsonl')}
    old_parsed={key(old_requests[r['id']]):r for r in read(a.from_run/'parsed/parsed.jsonl')}
    new_requests=read(a.to_run/'features/requests.jsonl');cached=[];pending=[]
    for request in new_requests:
        if key(request) in old_parsed:
            value=old_parsed[key(request)];cached.append({**value,'id':request['id']})
        else:pending.append(request)
    if a.mode=='prepare':
        with (a.to_run/'features/pending-requests.jsonl').open('x',encoding='utf-8') as f:
            for r in pending:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        report={'total':len(new_requests),'cached_extraction':len(cached),'new_extraction':len(pending),'key_fields':['mode','text','date','previous_text'],'evidence_reused':False}
        (a.to_run/'extraction-cache.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    else:
        inferred=read(a.to_run/'parsed/pending-parsed.jsonl')
        if {r['id'] for r in inferred}!={r['id'] for r in pending}:raise ValueError('Missing or extra pending inference output')
        results={r['id']:r for r in cached+inferred}
        with (a.to_run/'parsed/parsed.jsonl').open('x',encoding='utf-8') as f:
            for r in new_requests:f.write(json.dumps(results[r['id']],ensure_ascii=False)+'\n')
        print(json.dumps({'merged':len(results),'cached':len(cached),'new':len(inferred)}))
if __name__=='__main__':main()
