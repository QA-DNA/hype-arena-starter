param(
    [string]$Image='veridyct:competition-candidate',
    [string]$BuilderImage='rust:1.90.0-bookworm'
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
& docker build --platform linux/amd64 --build-arg "BUILDER_IMAGE=$BuilderImage" -f (Join-Path $taskRoot 'Dockerfile') -t $Image $taskRoot
if($LASTEXITCODE -ne 0){throw 'Competition build failed'}
$taskInspect=(& docker image inspect $Image | ConvertFrom-Json)[0]
if($taskInspect.Config.User -ne '10001'){throw 'Expected USER 10001'}
if($taskInspect.Size -ge 3GB){throw 'Image exceeds 3 GiB'}
Write-Output "Built $Image ($($taskInspect.Id)), $($taskInspect.Size) unpacked bytes."
