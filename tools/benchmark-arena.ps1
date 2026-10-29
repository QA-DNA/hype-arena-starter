param(
    [string]$Image = 'veridyct:mvp',
    [int]$Rows = 20000,
    [string]$SourceCommit = ''
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskRun = Join-Path $taskRoot "artifacts/benchmark-$taskStamp"
$taskUniverse = Join-Path $taskRun 'universe'
$taskOutput = Join-Path $taskRun 'output'
$taskName = "veridyct-benchmark-$taskStamp"
New-Item -ItemType Directory -Force -Path $taskUniverse, $taskOutput | Out-Null
$taskImage = (& docker image inspect $Image | ConvertFrom-Json)[0]
if ($LASTEXITCODE -ne 0) { throw 'Image inspection failed.' }
if ($taskImage.Config.User -ne '10001') { throw 'Expected image USER 10001.' }
if ($taskImage.Size -ge 3GB) { throw 'Image exceeds the 3 GiB contract.' }
@'
import csv, hashlib, json, pathlib, sys
root, universe, count = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), int(sys.argv[3])
with (root/'data/practice.csv').open(encoding='utf-8-sig', newline='') as f:
    source = list(csv.DictReader(f))
if count < len(source):
    raise SystemExit('Rows must include every practice row')
path = universe/'universe.csv'
with path.open('w', encoding='utf-8', newline='') as f:
    w=csv.writer(f);w.writerow(['id','text','date','label'])
    for r in source:
        w.writerow([r['id'],r['text'],r['date'],r['label']])
    for i in range(count-len(source)):
        r=source[i%len(source)]
        text=r['text'].rstrip('.!? ') + f'; QA performance probe {i+1}.'
        w.writerow([f'stress-{i+1:05d}',text,r['date'],''])
print(json.dumps({'rows':count,'known':len(source),'unknown':count-len(source),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':'Synthetic near-template throughput fixture; no invented truth labels and no accuracy claim.'}))
'@ | py -3 - $taskRoot $taskUniverse $Rows | Set-Content -LiteralPath (Join-Path $taskRun 'input.json') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Fixture preparation failed.' }
Copy-Item -LiteralPath (Join-Path $taskRoot 'data/lexicon.json') -Destination (Join-Path $taskUniverse 'lexicon.json')
$taskDeadline = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + 30 * 60
$taskArgs = @('run', '-d', '--name', $taskName, '--platform', 'linux/amd64',
    '--network', 'none', '--read-only', '--user', '10001:10001', '--cpus', '2',
    '--memory', '6g', '--memory-swap', '6g', '--pids-limit', '256', '--cap-drop', 'ALL',
    '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,size=128m,mode=1777',
    '-v', "${taskUniverse}:/universe:ro", '-v', "${taskOutput}:/output",
    '-e', "ARENA_DEADLINE=$taskDeadline", '--entrypoint', '/bin/sh', $Image, '-c',
    '/app/veridyct run & arena_pid=$!; arena_peak=0; while kill -0 $arena_pid 2>/dev/null; do if test -r /proc/$arena_pid/status; then while read arena_key arena_value arena_unit; do case $arena_key in VmHWM:) if test $arena_value -gt $arena_peak; then arena_peak=$arena_value; fi;; esac; done < /proc/$arena_pid/status; fi; sleep 0.05; done; wait $arena_pid; arena_code=$?; echo ARENA_RSS_PEAK_KB=$arena_peak; echo ARENA_MEMORY_PEAK=$(cat /sys/fs/cgroup/memory.peak); exit $arena_code')
$taskTimer = [Diagnostics.Stopwatch]::StartNew()
try {
    & docker @taskArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Container start failed.' }
    while ((& docker inspect -f '{{.State.Running}}' $taskName) -eq 'true') {
        if ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge $taskDeadline) {
            & docker stop -t 10 $taskName | Out-Null
            throw 'Benchmark deadline reached.'
        }
        Start-Sleep -Milliseconds 250
    }
    $taskTimer.Stop()
    $taskPreviousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $taskLogs = & docker logs $taskName 2>&1 | ForEach-Object { "$_" }
    $ErrorActionPreference = $taskPreviousErrorPreference
    $taskLogs | Set-Content -LiteralPath (Join-Path $taskRun 'runtime.log') -Encoding utf8
    $taskContainer = (& docker inspect $taskName | ConvertFrom-Json)[0]
    $taskContainer | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $taskRun 'container.json') -Encoding utf8
    if ($taskContainer.State.ExitCode -ne 0 -or $taskContainer.State.OOMKilled) { throw 'Runtime failed.' }
    if ($taskContainer.HostConfig.NetworkMode -ne 'none' -or -not $taskContainer.HostConfig.ReadonlyRootfs) { throw 'Sandbox mismatch.' }
    if ($taskContainer.HostConfig.NanoCpus -ne 2000000000 -or $taskContainer.HostConfig.Memory -ne 6442450944 -or $taskContainer.HostConfig.PidsLimit -ne 256) { throw 'Resource mismatch.' }
    @'
import csv,json,pathlib,sys
universe,output=map(pathlib.Path,sys.argv[1:3])
with (universe/'universe.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
with (output/'output.csv').open(encoding='utf-8',newline='') as f: result=list(csv.DictReader(f))
expected=[r['id'] for r in rows if not r['label']]
labels=[r for r in result if not r['type']]; claims=[r for r in result if r['type']]
assert [r['id'] for r in labels]==expected,'Missing, duplicate or reordered output labels'
assert len(claims)==1000,'Expected exactly 1,000 claims'
assert len({r['id'] for r in result})==len(result),'Duplicate output IDs'
norm=lambda s:' '.join(s.lower().split()).rstrip('.!? ')
source={norm(r['text']) for r in rows}
assert not any(norm(r['text']) in source for r in claims),'Claim copies a runtime input row'
assert len({norm(r['text']) for r in claims})==1000,'Duplicate claim text'
for r in labels:
    assert r['label'] in ('true','false','unsure')
    assert not r['confidence'] if r['label']=='unsure' else .5<=float(r['confidence'])<=1
for r in claims:
    assert r['label']=='true' and .5<=float(r['confidence'])<=1
    assert isinstance(json.loads(r['form']),dict)
size=(output/'output.csv').stat().st_size
assert size<=16*1024*1024
print(json.dumps({'labels':len(labels),'claims':len(claims),'output_bytes':size,'output_order':'matches input','semantic_accuracy':'not evaluated on synthetic rows'}))
'@ | py -3 - $taskUniverse $taskOutput | Set-Content -LiteralPath (Join-Path $taskRun 'validation.json') -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw 'Output validation failed.' }
    $taskPeak = ($taskLogs | Select-String 'ARENA_MEMORY_PEAK=(\d+)').Matches.Groups[1].Value
    $taskRss = ($taskLogs | Select-String 'ARENA_RSS_PEAK_KB=(\d+)').Matches.Groups[1].Value
    $taskReport = [ordered]@{
        image = $taskImage.Id
        image_bytes = $taskImage.Size
        harness_commit = (& git -C $taskRoot rev-parse HEAD)
        image_source_commit_supplied = $SourceCommit
        cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)
        cpus_limit = 2
        memory_limit_bytes = 6442450944
        cgroup_memory_peak_bytes = [long]$taskPeak
        sampled_process_peak_rss_kib = [long]$taskRss
        wall_including_docker_start_seconds = [Math]::Round($taskTimer.Elapsed.TotalSeconds, 3)
        memory_scope = 'Cgroup peak includes page cache and measurement shell. Process VmHWM is sampled every 50ms and can miss a peak after the final sample.'
        runtime_override = 'A measurement shell invokes the unmodified /app/veridyct run, samples its /proc status, then reads cgroup memory.peak. Image digest is authoritative; source revision is supplied by the builder.'
    }
    $taskReport | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'benchmark.json') -Encoding utf8
    $taskLogs | Write-Host
    $taskReport | ConvertTo-Json | Write-Host
    Get-Content -LiteralPath (Join-Path $taskRun 'input.json'), (Join-Path $taskRun 'validation.json') | Write-Host
    Write-Host "Artifacts: $taskRun"
} finally {
    & docker rm -f $taskName 2>$null | Out-Null
}
