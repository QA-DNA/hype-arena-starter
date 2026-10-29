param(
    [string]$Practice = 'data/practice.csv',
    [string]$Lexicon = 'data/lexicon.json',
    [string]$Assignments = 'analysis/practice/outputs/split_assignments.csv',
    [string]$Output = 'artifacts/evaluation-splits/report.json',
    [string]$External = '',
    [string]$TestIds = '',
    [string]$Predictions = '',
    [string]$Splits = 'random,bundle_group,template_group,forward_time,every_fifth',
    [switch]$Docker,
    [string]$Image = 'veridyct:dev',
    [string]$TargetVolume = '',
    [string]$RegistryVolume = 'veridyct-mvp-registry',
    [ValidateRange(1, 64)][int]$Cpus = 2,
    [string]$Memory = '6g'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot

function Resolve-TaskPath([string]$Value) {
    if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
    return [IO.Path]::GetFullPath((Join-Path $taskRoot $Value))
}

function Get-TaskFingerprint([string]$Path) {
    return [ordered]@{
        path = $Path
        bytes = (Get-Item -LiteralPath $Path).Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$taskPractice = Resolve-TaskPath $Practice
$taskLexicon = Resolve-TaskPath $Lexicon
$taskAssignments = Resolve-TaskPath $Assignments
$taskOutput = Resolve-TaskPath $Output
$taskExternal = if ($External) { Resolve-TaskPath $External } else { '' }
$taskTestIds = if ($TestIds) { Resolve-TaskPath $TestIds } else { '' }
$taskPredictions = if ($Predictions) { Resolve-TaskPath $Predictions } else { '' }
foreach ($taskInput in @($taskPractice, $taskLexicon, $taskAssignments)) {
    if (-not (Test-Path -LiteralPath $taskInput -PathType Leaf)) { throw "Missing input: $taskInput" }
}
if ($taskExternal -and -not (Test-Path -LiteralPath $taskExternal -PathType Leaf)) {
    throw "Missing external gold CSV: $taskExternal"
}
$taskInputs = @($taskPractice, $taskLexicon, $taskAssignments)
if ($taskExternal) { $taskInputs += $taskExternal }
if ($taskTestIds) { $taskInputs += $taskTestIds }
if ($taskPredictions) { $taskInputs += $taskPredictions }
foreach ($taskInput in $taskInputs) {
    if (-not (Test-Path -LiteralPath $taskInput -PathType Leaf)) { throw "Missing input: $taskInput" }
}
if ($taskPredictions -and -not $taskTestIds) { throw '-Predictions requires -TestIds to prevent parser training leakage across named splits.' }
if ($taskInputs -contains $taskOutput) { throw 'Output must not overwrite an input file.' }
$taskOutputDir = Split-Path -Parent $taskOutput
New-Item -ItemType Directory -Force -Path $taskOutputDir | Out-Null

$taskHasher = [Security.Cryptography.SHA256]::Create()
try {
    $taskCheckoutId = ([BitConverter]::ToString($taskHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskRoot)))).Replace('-', '').Substring(0, 12).ToLowerInvariant()
} finally { $taskHasher.Dispose() }
if (-not $TargetVolume) { $TargetVolume = "veridyct-evaluation-$taskCheckoutId-target" }
$taskNativeTarget = Join-Path $taskRoot "target/evaluation-$taskCheckoutId"
$taskCommit = (& git -C $taskRoot rev-parse HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Cannot record source revision.' }
$taskDirty = [bool](& git -C $taskRoot status --porcelain)
$taskMode = if ($Docker -or -not (Get-Command cargo -ErrorAction SilentlyContinue)) { 'docker' } else { 'native' }
$taskSourceHashes = @()
foreach ($taskSource in (Get-ChildItem -LiteralPath (Join-Path $taskRoot 'crates/core/src') -Filter '*.rs' -Recurse)) {
    $taskSourceHashes += Get-TaskFingerprint $taskSource.FullName
}
$taskSourceHashes += Get-TaskFingerprint (Join-Path $taskRoot 'crates/core/examples/evaluate_splits.rs')
$taskSourceHashes += Get-TaskFingerprint (Join-Path $taskRoot 'Cargo.lock')
$taskSourceHashes += Get-TaskFingerprint (Join-Path $taskRoot 'Cargo.toml')
$taskSourceHashes += Get-TaskFingerprint (Join-Path $taskRoot 'crates/core/Cargo.toml')
$taskSourceHashes += Get-TaskFingerprint $PSCommandPath
$taskInputHashes = @($taskInputs | ForEach-Object { Get-TaskFingerprint $_ })
$taskImageId = $null
$taskToolchain = $null
$taskTimer = [Diagnostics.Stopwatch]::StartNew()

if ($taskMode -eq 'docker') {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Neither Cargo nor Docker is available.' }
    $taskImageInfo = & docker image inspect $Image --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0) { throw "Development image is unavailable: $Image" }
    $taskImageId = "$taskImageInfo".Trim()
    $taskArgs = @(
        'run', '--rm', '--network', 'none', '--user', '0:0', '--cpus', "$Cpus",
        '--memory', $Memory, '--memory-swap', $Memory, '--pids-limit', '256',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--mount', "type=bind,source=$taskRoot,target=/workspace,readonly",
        '--mount', "type=bind,source=$taskPractice,target=/evaluation-inputs/practice.csv,readonly",
        '--mount', "type=bind,source=$taskLexicon,target=/evaluation-inputs/lexicon.json,readonly",
        '--mount', "type=bind,source=$taskAssignments,target=/evaluation-inputs/assignments.csv,readonly",
        '--mount', "type=bind,source=$taskOutputDir,target=/evaluation-output",
        '--mount', "type=volume,source=$TargetVolume,target=/evaluation-target",
        '--mount', "type=volume,source=$RegistryVolume,target=/usr/local/cargo/registry",
        '-e', 'CARGO_TARGET_DIR=/evaluation-target', '-e', "VERIDYCT_EVAL_COMMIT=$taskCommit",
        '-w', '/workspace'
    )
    if ($taskExternal) {
        $taskArgs += @('--mount', "type=bind,source=$taskExternal,target=/evaluation-inputs/external.csv,readonly")
    }
    if ($taskTestIds) {
        $taskArgs += @('--mount', "type=bind,source=$taskTestIds,target=/evaluation-inputs/test-ids.txt,readonly")
    }
    if ($taskPredictions) {
        $taskArgs += @('--mount', "type=bind,source=$taskPredictions,target=/evaluation-inputs/predictions.jsonl,readonly")
    }
    $taskArgs += @('--entrypoint', '/usr/local/cargo/bin/cargo', $Image,
        'run', '--locked', '--offline', '--release', '-p', 'veridyct-core', '--example', 'evaluate_splits', '--',
        '--practice', '/evaluation-inputs/practice.csv', '--lexicon', '/evaluation-inputs/lexicon.json',
        '--assignments', '/evaluation-inputs/assignments.csv', '--splits', $Splits,
        '--output', "/evaluation-output/$([IO.Path]::GetFileName($taskOutput))")
    if ($taskExternal) { $taskArgs += @('--external', '/evaluation-inputs/external.csv') }
    if ($taskTestIds) { $taskArgs += @('--test-ids', '/evaluation-inputs/test-ids.txt') }
    if ($taskPredictions) { $taskArgs += @('--predictions', '/evaluation-inputs/predictions.jsonl') }
    & docker @taskArgs
    if ($LASTEXITCODE -ne 0) { throw "Evaluation failed with exit code $LASTEXITCODE." }
    $taskTimer.Stop()
    $taskToolchain = @(& docker run --rm --network none --entrypoint /bin/sh $Image -c '/usr/local/cargo/bin/cargo --version; /usr/local/cargo/bin/rustc --version')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record Docker toolchain.' }
} else {
    $taskPreviousTarget = $env:CARGO_TARGET_DIR
    $taskPreviousCommit = $env:VERIDYCT_EVAL_COMMIT
    Push-Location -LiteralPath $taskRoot
    try {
        $env:CARGO_TARGET_DIR = $taskNativeTarget
        $env:VERIDYCT_EVAL_COMMIT = $taskCommit
        $taskArgs = @('run', '--locked', '--release', '-p', 'veridyct-core', '--example', 'evaluate_splits', '--',
            '--practice', $taskPractice, '--lexicon', $taskLexicon, '--assignments', $taskAssignments,
            '--output', $taskOutput, '--splits', $Splits)
        if ($taskExternal) { $taskArgs += @('--external', $taskExternal) }
        if ($taskTestIds) { $taskArgs += @('--test-ids', $taskTestIds) }
        if ($taskPredictions) { $taskArgs += @('--predictions', $taskPredictions) }
        & cargo @taskArgs
        if ($LASTEXITCODE -ne 0) { throw "Evaluation failed with exit code $LASTEXITCODE." }
        $taskTimer.Stop()
        $taskToolchain = @(& cargo --version; & rustc --version)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot record native toolchain.' }
    } finally {
        $env:CARGO_TARGET_DIR = $taskPreviousTarget
        $env:VERIDYCT_EVAL_COMMIT = $taskPreviousCommit
        Pop-Location
    }
}

$taskReport = Get-Content -LiteralPath $taskOutput -Raw | ConvertFrom-Json
$taskCpu = if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
    (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)
} else { $env:PROCESSOR_IDENTIFIER }
$taskMetadata = [ordered]@{
    source_commit = $taskCommit
    source_dirty = $taskDirty
    source_sha256 = $taskSourceHashes
    input_sha256 = $taskInputHashes
    report_sha256 = (Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant()
    mode = $taskMode
    image_id = $taskImageId
    toolchain = $taskToolchain
    host_cpu = $taskCpu
    container_cpus = if ($taskMode -eq 'docker') { $Cpus } else { $null }
    container_memory = if ($taskMode -eq 'docker') { $Memory } else { $null }
    target_cache = if ($taskMode -eq 'docker') { $TargetVolume } else { $taskNativeTarget }
    registry_cache = if ($taskMode -eq 'docker') { $RegistryVolume } else { $null }
    wall_including_build_seconds = $taskTimer.Elapsed.TotalSeconds
    scope = 'Development-time release CPU diagnostics; Docker build/run is offline, with a checkout-specific target cache. Runtime peak RSS and stage timings are in the report; wrapper wall time includes compilation.'
}
$taskMetadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$taskOutput.metadata.json" -Encoding UTF8
$taskReport.splits | ForEach-Object {
    [pscustomobject]@{
        split = $_.split
        train = $_.training_rows
        test = $_.test_rows
        accuracy = [Math]::Round($_.classification.accuracy, 6)
        macroF1 = [Math]::Round($_.classification.macro_f1, 6)
        majority = [Math]::Round($_.majority_baseline.metrics.accuracy, 6)
        tupleExact = if ($null -ne $_.extraction) { [Math]::Round($_.extraction.exact_accuracy, 6) } else { $null }
        tupleF1 = if ($null -ne $_.extraction) { [Math]::Round($_.extraction.micro_f1, 6) } else { $null }
        seconds = [Math]::Round($_.timing.elapsed_seconds, 3)
    }
} | Format-Table -AutoSize
Write-Host "Report: $taskOutput"
Write-Host "Reproducibility metadata: $taskOutput.metadata.json"
