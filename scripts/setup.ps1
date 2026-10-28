# One-time setup on Windows. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Creates .venv, installs everything, runs the tests and a quick evaluation.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --upgrade pip
& .venv\Scripts\python.exe -m pip install -r requirements-dev.txt

Write-Host "`nRunning tests ..."
& .venv\Scripts\python.exe -m pytest

Write-Host "`nRunning a quick evaluation ..."
& .venv\Scripts\python.exe scripts\eval.py --no-claims

Write-Host "`nDone. Activate the environment in each new terminal with:  .venv\Scripts\Activate.ps1"
