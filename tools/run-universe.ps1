param(
    [Parameter(Mandatory=$true)][string]$Universe,
    [string]$Image='veridyct:evidence-native',
    [string]$Context='none',
    [ValidateSet('padded','exact-length')][string]$Batching='padded',
    [switch]$Structured,
    [switch]$Diagnostics,
    [int]$Minutes=30
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskSource=(Resolve-Path -LiteralPath $Universe).Path
$taskRun=Join-Path $taskRoot ('artifacts/universe-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$taskInput=Join-Path $taskRun 'universe'
$taskOutput=Join-Path $taskRun 'output'
$taskName='veridyct-universe-'+(Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Force -Path $taskInput,$taskOutput | Out-Null
foreach($taskFile in @('universe.csv','lexicon.json')) {
    Copy-Item -LiteralPath (Join-Path $taskSource $taskFile) -Destination $taskInput
}
$taskImage=(& docker image inspect $Image | ConvertFrom-Json)[0]
if($LASTEXITCODE -ne 0){throw 'Cannot inspect image'}
if($taskImage.Config.User -ne '10001'){throw 'Expected image USER10001'}
if($taskImage.Size -ge 3GB){throw 'Image exceeds3GiB'}
$taskDeadline=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()+60*$Minutes
$taskMonitor=@'
/app/veridyct run & arena_pid=$!
wait $arena_pid
arena_code=$?
echo ARENA_MEMORY_PEAK=$(cat /sys/fs/cgroup/memory.peak)
exit $arena_code
'@
$taskArgs=@('run','-d','--name',$taskName,'--network','none','--read-only','--user','10001:10001','--cpus','2','--memory','6g','--memory-swap','6g','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=128m,mode=1777','-v',"${taskInput}:/universe:ro",'-v',"${taskOutput}:/output",'-e',"ARENA_DEADLINE=$taskDeadline",'-e',"VERIDYCT_PARSER_CONTEXT=$Context",'--entrypoint','/bin/sh',$Image,'-c',$taskMonitor)
if($Diagnostics){$taskArgs=@('run','-e','VERIDYCT_DIAGNOSTICS=1')+$taskArgs[1..($taskArgs.Length-1)]}
if($Structured){$taskArgs=@('run','-e','VERIDYCT_STRUCTURED_PARSER=1')+$taskArgs[1..($taskArgs.Length-1)]}
$taskArgs=@('run','-e',"VERIDYCT_PARSER_BATCHING=$Batching")+$taskArgs[1..($taskArgs.Length-1)]
$taskTimer=[Diagnostics.Stopwatch]::StartNew()
try {
    & docker @taskArgs | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Container start failed'}
    while((& docker inspect -f '{{.State.Running}}' $taskName) -eq 'true') {
        if([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge $taskDeadline){
            & docker stop -t 10 $taskName | Out-Null
            throw 'Arena deadline reached'
        }
        Start-Sleep -Milliseconds 500
    }
    # Windows PowerShell represents native stderr as ErrorRecords even on exit0.
    # Capture diagnostics without treating those records as a process failure;
    # the actual container exit status is checked below.
    $taskPriorPreference=$ErrorActionPreference
    $ErrorActionPreference='Continue'
    $taskLogs=& docker logs $taskName 2>&1 | ForEach-Object {"$_"}
    $ErrorActionPreference=$taskPriorPreference
    $taskLogs | Set-Content -LiteralPath (Join-Path $taskRun 'container.log') -Encoding utf8
    $taskLogs | Write-Output
    $taskExit=& docker inspect -f '{{.State.ExitCode}}' $taskName
    $taskTimer.Stop()
    $taskBytes=(Get-ChildItem -LiteralPath $taskOutput -File | Measure-Object -Property Length -Sum).Sum
    $taskMetadata=[ordered]@{
        image=$taskImage.Id;image_bytes=$taskImage.Size;source_commit=(& git -C $taskRoot rev-parse HEAD).Trim();
        uncommitted=$true;context=$Context;batching=$Batching;structured=[bool]$Structured;wall_seconds=$taskTimer.Elapsed.TotalSeconds;exit_code=[int]$taskExit;
        cpus=2;memory_bytes=6442450944;output_bytes=$taskBytes;input_sha256=(Get-FileHash -LiteralPath (Join-Path $taskInput 'universe.csv')).Hash;
        scope='Complete offline solver; two public input files only. Gold never mounted. Windows output bind mount size measured after execution, no filesystem quota.'
    }
    $taskMetadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'run.json') -Encoding utf8
    $taskMetadata | ConvertTo-Json -Depth 5 | Write-Output
    Write-Output "Artifacts: $taskRun"
    if($taskExit -ne '0'){throw "Solver exited with code$taskExit"}
    if($taskBytes -gt 256MB){throw 'Output mount contents exceed256MiB'}
    if((Get-Item -LiteralPath (Join-Path $taskOutput 'output.csv')).Length -gt 16MB){throw 'CSV exceeds16MiB'}
} finally {& docker rm -f $taskName 2>$null | Out-Null}
