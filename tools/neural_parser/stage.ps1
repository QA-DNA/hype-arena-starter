param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [string]$Output = "artifacts/neural-parser/build"
)
$ErrorActionPreference = "Stop"
$taskRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$taskBundleRoot = (Resolve-Path -LiteralPath $Bundle).Path
$taskOutputRoot = [IO.Path]::GetFullPath((Join-Path $taskRepoRoot $Output))
if (Test-Path -LiteralPath $taskOutputRoot) {
    throw "Use a fresh staging directory: $taskOutputRoot"
}
$taskManifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "provenance.json") | ConvertFrom-Json
foreach ($taskEntry in $taskManifest.frozen_sources.PSObject.Properties) {
    $taskSource = Join-Path (Join-Path $PSScriptRoot "frozen") $taskEntry.Name
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $taskSource).Hash.ToLowerInvariant() -ne $taskEntry.Value) {
        throw "Frozen source hash mismatch: $($taskEntry.Name)"
    }
}
foreach ($taskEntry in $taskManifest.bundle.PSObject.Properties) {
    $taskSource = Join-Path $taskBundleRoot $taskEntry.Name
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $taskSource).Hash.ToLowerInvariant() -ne $taskEntry.Value) {
        throw "Frozen bundle hash mismatch: $($taskEntry.Name)"
    }
}
New-Item -ItemType Directory -Path (Join-Path $taskOutputRoot "model") -Force | Out-Null
foreach ($taskEntry in $taskManifest.bundle.PSObject.Properties) {
    Copy-Item -LiteralPath (Join-Path $taskBundleRoot $taskEntry.Name) -Destination (Join-Path $taskOutputRoot "model")
}
foreach ($taskName in @("batch.py", "provenance.json", "requirements-runtime.txt", "__init__.py")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $taskName) -Destination $taskOutputRoot
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "frozen") -Destination $taskOutputRoot -Recurse
Copy-Item -LiteralPath (Join-Path $taskRepoRoot "Dockerfile.neural") -Destination $taskOutputRoot
Write-Output "Verified frozen bundle and staged Docker build context: $taskOutputRoot"
