param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [string]$RuntimeImage = 'veridyct-neural-parser:integration'
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$manifest = Get-Content -Encoding UTF8 -Raw -LiteralPath (Join-Path $here 'provenance.json') | ConvertFrom-Json
foreach ($section in @('bundle', 'frozen_sources')) {
    $dest = if ($section -eq 'bundle') { Join-Path $here 'model' } else { Join-Path $here 'frozen' }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    foreach ($file in $manifest.$section.PSObject.Properties) {
        $source = Join-Path $Bundle $file.Name
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
        if ($actual -ne $file.Value) { throw "Frozen SHA256 mismatch: $($file.Name)" }
        Copy-Item -LiteralPath $source -Destination (Join-Path $dest $file.Name) -Force
    }
}
$runtime = Join-Path $here 'runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$container = (& docker create --entrypoint /bin/true $RuntimeImage).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot create reference container' }
try {
    & docker cp "${container}:/usr/local/lib/python3.11/site-packages/onnxruntime/capi/libonnxruntime.so.1.23.2" (Join-Path $runtime 'libonnxruntime.so.1.23.2')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot copy ONNX Runtime' }
    & docker cp "${container}:/usr/local/lib/python3.11/site-packages/onnxruntime/capi/libonnxruntime_providers_shared.so" (Join-Path $runtime 'libonnxruntime_providers_shared.so')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot copy ONNX Runtime provider library' }
} finally { & docker rm $container | Out-Null }
$receipt = [ordered]@{ image = $RuntimeImage; image_id = (& docker image inspect --format '{{.Id}}' $RuntimeImage).Trim(); files = [ordered]@{} }
Get-ChildItem -LiteralPath $runtime -Filter '*.so*' | ForEach-Object { $receipt.files[$_.Name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
foreach ($file in $manifest.runtime.PSObject.Properties) {
    if ($receipt.files[$file.Name] -ne $file.Value) { throw "Native runtime SHA256 mismatch: $($file.Name)" }
}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runtime 'receipt.json')
Write-Output ($receipt | ConvertTo-Json -Depth 5)
