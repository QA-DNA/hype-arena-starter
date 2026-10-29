param(
    [string]$Image='veridyct:competition-candidate',
    [string]$Verifier='artifacts/verifier-lab/models/PRODUCTION-all-practice-gbt.json',
    [string]$BuilderImage='rust:1.90.0-bookworm'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskVerifier=(Resolve-Path -LiteralPath $Verifier).Path
$taskExpected='007d278c95e5cffc785efb89a66ca0b2d2b9428b74f02986798dd2da716c8f59'
if((Get-FileHash -Algorithm SHA256 -LiteralPath $taskVerifier).Hash.ToLowerInvariant() -ne $taskExpected){throw 'Production verifier hash mismatch'}
foreach($taskFile in @('tools/native_parser/model/model.onnx','tools/native_parser/model/meta.json','tools/native_parser/model/lexicon.json','tools/native_parser/runtime/libonnxruntime.so.1.23.2','tools/native_parser/runtime/libonnxruntime_providers_shared.so')) {
    if(-not (Test-Path -LiteralPath (Join-Path $taskRoot $taskFile))){throw "Stage the frozen native assets first: missing $taskFile"}
}
Copy-Item -LiteralPath $taskVerifier -Destination (Join-Path $taskRoot 'tools/native_parser/model/verifier.json') -Force
& docker build --platform linux/amd64 --build-arg "BUILDER_IMAGE=$BuilderImage" -f (Join-Path $taskRoot 'Dockerfile.competition') -t $Image $taskRoot
if($LASTEXITCODE -ne 0){throw 'Competition candidate build failed'}
$taskInspect=(& docker image inspect $Image | ConvertFrom-Json)[0]
if($taskInspect.Config.User -ne '10001'){throw 'Expected USER 10001'}
if($taskInspect.Size -ge 3GB){throw 'Image exceeds 3 GiB'}
Write-Output "Built $Image ($($taskInspect.Id)), $($taskInspect.Size) unpacked bytes."
