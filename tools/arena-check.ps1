param(
    [string]$Image = 'veridyct:mvp',
    [int]$Minutes = 30,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskRun = Join-Path $taskRoot "artifacts/arena-$taskStamp"
$taskUniverse = Join-Path $taskRun 'universe'
$taskOutput = Join-Path $taskRun 'output'
$taskName = "veridyct-arena-$taskStamp"
New-Item -ItemType Directory -Force -Path $taskUniverse, $taskOutput | Out-Null
if (-not $SkipBuild) {
    & docker build --platform linux/amd64 -t $Image $taskRoot
    if ($LASTEXITCODE -ne 0) { throw 'Docker build failed.' }
}
$taskUser = & docker image inspect $Image --format '{{.Config.User}}'
if ($LASTEXITCODE -ne 0 -or $taskUser -match '^(|root|0)(:|$)') { throw 'The image must use a non-root USER.' }
& py -3 (Join-Path $taskRoot 'scripts/input.py') (Join-Path $taskRoot 'data/practice.csv') (Join-Path $taskUniverse 'universe.csv')
if ($LASTEXITCODE -ne 0) { throw 'Input preparation failed.' }
Copy-Item -LiteralPath (Join-Path $taskRoot 'data/lexicon.json') -Destination (Join-Path $taskUniverse 'lexicon.json')
$taskDeadline = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + $Minutes * 60
$taskArgs = @('run', '-d', '--name', $taskName, '--platform', 'linux/amd64',
    '--network', 'none', '--read-only', '--user', '10001:10001', '--cpus', '2',
    '--memory', '6g', '--memory-swap', '6g', '--pids-limit', '256', '--cap-drop', 'ALL',
    '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,size=128m,mode=1777',
    '-v', "${taskUniverse}:/universe:ro", '-v', "${taskOutput}:/output",
    '-e', "ARENA_DEADLINE=$taskDeadline", $Image)
try {
    & docker @taskArgs
    if ($LASTEXITCODE -ne 0) { throw 'Container start failed.' }
    while ((& docker inspect -f '{{.State.Running}}' $taskName) -eq 'true') {
        if ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge $taskDeadline) {
            & docker stop -t 10 $taskName | Out-Null
            break
        }
        Start-Sleep -Seconds 2
    }
    & docker logs $taskName
    & docker inspect $taskName | Set-Content -LiteralPath (Join-Path $taskRun 'container.json') -Encoding utf8
    $taskExit = & docker inspect -f '{{.State.ExitCode}}' $taskName
    Write-Host "Container exit: $taskExit. Artifacts: $taskRun"
    & py -3 (Join-Path $taskRoot 'scripts/check_output.py') $taskOutput (Join-Path $taskRoot 'data/practice.csv') (Join-Path $taskUniverse 'universe.csv')
    if ($LASTEXITCODE -ne 0 -or $taskExit -ne '0') { throw 'Arena run or official output validation failed.' }
} finally {
    & docker rm -f $taskName 2>$null | Out-Null
}
