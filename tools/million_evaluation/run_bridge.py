"""Run the research bridge with public feature files and frozen CPU models only."""
import argparse,hashlib,json,subprocess,time,uuid
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['parse','compare']);p.add_argument('--run',type=Path,required=True);p.add_argument('--binary',type=Path,default=Path('artifacts/million-runtime/bin/bridge'));p.add_argument('--image',default='veridyct:merged-million-baseline');p.add_argument('--input-name');p.add_argument('--output-name');a=p.parse_args()
    root=Path(__file__).resolve().parents[2];run=a.run.resolve();binary=a.binary.resolve()
    if not run.is_relative_to(root/'artifacts') or not binary.is_relative_to(root/'artifacts'):raise ValueError('Use ignored local artifacts')
    features=run/'features';output=run/'parsed';output.mkdir(exist_ok=True)
    output_name=a.output_name or ('parsed.jsonl' if a.mode=='parse' else 'comparisons.jsonl')
    input_name=a.input_name or ('requests.jsonl' if a.mode=='parse' else 'pairs.jsonl')
    if any(Path(n).name!=n or not n.endswith('.jsonl') for n in (input_name,output_name)):raise ValueError('Use JSONL basenames only')
    destination=output/output_name
    if destination.exists():raise ValueError('Preserve previous output; use a new run or explicitly retain failed output')
    input_file=features/input_name
    info=json.loads(subprocess.check_output(['docker','image','inspect',a.image],text=True))[0]
    if info['Config']['User']!='10001':raise ValueError('Unexpected runtime UID')
    arguments=[a.mode,'/inputs/'+input_file.name,'/output/'+destination.name]
    if a.mode=='parse':arguments+=['/opt/veridyct-extractor/model','/app/verifier.json','/inputs/practice.csv']
    name='veridyct-million-'+uuid.uuid4().hex[:12]
    wrapper='/app/million-bridge "$@"; bench_exit=$?; echo BENCH_MEMORY_PEAK=$(cat /sys/fs/cgroup/memory.peak); exit "$bench_exit"'
    argv=['docker','run','--name',name,'--network','none','--read-only','--user','10001:10001','--cpus','2','--memory','6g','--memory-swap','6g','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=128m,mode=1777','-v',f'{features}:/inputs:ro','-v',f'{output}:/output','-v',f'{binary}:/app/million-bridge:ro','--entrypoint','/bin/sh',a.image,'-c',wrapper,'bench',*arguments]
    started=time.perf_counter();report={'mode':a.mode,'argv':argv,'image':info['Id'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'input_sha256':hashlib.sha256(input_file.read_bytes()).hexdigest(),'annotation_mounts':False,'protocol_adapter':'research interface, not the unmodified competition CLI'}
    try:
        with (run/(a.mode+'-container.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        state=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
        report.update(exit_code=result.returncode,wall_seconds=time.perf_counter()-started,oom=state['State']['OOMKilled'],cpus=2,memory_limit=6442450944,output_bytes=destination.stat().st_size if destination.exists() else None)
        (run/(a.mode+'-run.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report),flush=True)
        print((run/(a.mode+'-container.log')).read_text(encoding='utf-8')[-2500:],flush=True)
        if result.returncode:raise SystemExit(result.returncode)
    finally:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if __name__=='__main__':main()
