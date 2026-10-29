# PowerShell equivalent of scripts/check.sh for testing on Windows
param (
    [string]$Image = "hype-arena-submission",
    [int]$Minutes = 30
)

$ErrorActionPreference = "Stop"

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "  HYPE ARENA - LOCAL DOCKER VERIFICATION" -ForegroundColor Cyan
Write-Host "========================================================="

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

# 1. Build Image
Write-Host "`n[1/4] Building Docker image '$Image'..." -ForegroundColor Yellow
docker build --platform linux/amd64 -t $Image $root

# 2. Inspect User
$user = (docker image inspect $Image --format '{{.Config.User}}').Trim()
Write-Host "Image USER: '$user'"
if ($user -notmatch "^10001") {
    Write-Host "ERROR: Refused! Image USER must be 10001, got '$user'." -ForegroundColor Red
    exit 1
}

# 3. Create simulated mounts
$tempDir = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "hype-arena-check-" + [System.Guid]::NewGuid().ToString().Substring(0,8))
$workUniverse = Join-Path $tempDir "universe"
$workOutput = Join-Path $tempDir "output"
New-Item -ItemType Directory -Path $workUniverse -Force | Out-Null
New-Item -ItemType Directory -Path $workOutput -Force | Out-Null

Write-Host "`n[2/4] Preparing input data (with hidden labels)..." -ForegroundColor Yellow
python "$root/scripts/input.py" "$root/data/practice.csv" "$workUniverse/universe.csv"
Copy-Item "$root/data/lexicon.json" "$workUniverse/lexicon.json"

# 4. Run Docker Container
$deadline = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + ($Minutes * 60)
$containerName = "hype-arena-run-" + [System.Guid]::NewGuid().ToString().Substring(0,8)

Write-Host "`n[3/4] Running container '$containerName' offline..." -ForegroundColor Yellow
docker run -d --name $containerName --platform linux/amd64 `
    --network none --read-only --user 10001:10001 `
    --cpus 2 --memory 6g --memory-swap 6g --pids-limit 256 `
    --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,size=128m,mode=1777 `
    -v "${workUniverse}:/universe:ro" -v "${workOutput}:/output" `
    -e ARENA_DEADLINE="$deadline" `
    $Image | Out-Null

docker wait $containerName | Out-Null
Write-Host "`nContainer Logs:" -ForegroundColor Cyan
docker logs --tail 20 $containerName

docker rm -f $containerName | Out-Null

# 5. Check Output Format & Accuracy
Write-Host "`n[4/4] Evaluating output.csv with referee checks..." -ForegroundColor Yellow
python "$root/scripts/check_output.py" "$workOutput" "$root/data/practice.csv" "$workUniverse/universe.csv"

# Clean up
Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue

Write-Host "`nVerification complete!" -ForegroundColor Green
