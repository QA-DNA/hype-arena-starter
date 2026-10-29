param(
    [string]$Image='veridyct:evidence-native',
    [string]$ExtractorImage='veridyct-native-extractor:selected-v2',
    [switch]$Boosted
)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskContext=Join-Path $taskRoot 'artifacts/native-solver-layer'
New-Item -ItemType Directory -Force -Path $taskContext | Out-Null
$taskDockerfile=@'
ARG EXTRACTOR_IMAGE=veridyct-native-extractor:selected-v2
FROM veridyct:evidence-rust AS solver
FROM ${EXTRACTOR_IMAGE}
WORKDIR /app
COPY --from=solver /app/veridyct /app/veridyct
COPY --from=solver /app/veridyct-api /app/veridyct-api
ENV VERIDYCT_NATIVE_EXTRACTOR=/opt/veridyct-extractor/veridyct-extractor VERIDYCT_ADDR=0.0.0.0:8787 HOME=/tmp XDG_CACHE_HOME=/tmp
ENTRYPOINT ["/app/veridyct"]
CMD ["run"]
USER 10001
'@
if($Boosted){
    Copy-Item -LiteralPath (Join-Path $taskRoot 'artifacts/verifier-lab/models/PRODUCTION-all-practice-gbt.json') -Destination (Join-Path $taskContext 'verifier.json')
    $taskDockerfile+="`nCOPY verifier.json /app/verifier.json`nENV VERIDYCT_VERIFIER_MODEL=/app/verifier.json`nUSER 10001`n"
}
$taskDockerfile | Set-Content -LiteralPath (Join-Path $taskContext 'Dockerfile') -Encoding ascii
& docker build --platform linux/amd64 --build-arg "EXTRACTOR_IMAGE=$ExtractorImage" -t $Image $taskContext
if($LASTEXITCODE -ne 0){throw 'Native solver image build failed'}
