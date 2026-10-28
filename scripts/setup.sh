#!/bin/sh
# One-time setup on Mac/Linux (or Git Bash). Run from the repo root: sh scripts/setup.sh
set -eu
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
if [ -f .venv/bin/python ]; then PY=.venv/bin/python; else PY=.venv/Scripts/python.exe; fi
$PY -m pip install --upgrade pip
$PY -m pip install -r requirements-dev.txt
$PY -m pytest
$PY scripts/eval.py --no-claims
echo "Done. Activate with: . .venv/bin/activate"
