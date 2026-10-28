"""The API the frontend calls. Runs the same engine as the Docker image.

    uvicorn server.app:app --reload --port 8000       (from the repo root, venv active)

Endpoints (contract in docs/BRIEF_frontend.md):
  GET  /api/health        -> {"ok": true}
  GET  /api/architecture  -> the pipeline stages, for the diagram
  POST /api/run           -> body {"rows": [{id, text, date}], "include_claims": false}
                             runs the system on the practice universe + these rows and
                             returns the trace JSON for just these rows
  GET  /api/sample        -> the rows of sample/sample.csv (from 09:00 on 29 Oct), if present
  GET  /api/claims        -> the 1,000 claims the system writes on the practice universe
If web/dist exists (the built frontend), it is served at /.
"""
from __future__ import annotations

import csv
import sys
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polygraph import pipeline  # noqa: E402
from polygraph.lexicon import Lexicon  # noqa: E402
from polygraph.model import Row  # noqa: E402
from polygraph.trace import to_trace  # noqa: E402

app = FastAPI(title="Polygraph")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STAGES = [
    {"id": "reader", "name": "Reader", "what": "Reads every value as the referee does: money, counts, dates, versions, yes/no"},
    {"id": "linker", "name": "Linker", "what": "Finds which Hooly subjects a sentence names (lexicon + page context)"},
    {"id": "attributor", "name": "Attributor", "what": "Decides which attribute each value is about"},
    {"id": "truth", "name": "Truth engine", "what": "Rebuilds each fact's timeline from 20,000 rows, weighting trusted pages"},
    {"id": "judge", "name": "Judge", "what": "True / false / unsure per row with a calibrated confidence"},
    {"id": "forge", "name": "Claim forge", "what": "Writes 1,000 new true claims and checks each with our referee clone"},
]


class InRow(BaseModel):
    id: str
    text: str
    date: str


class RunRequest(BaseModel):
    rows: list[InRow]
    include_claims: bool = False


@lru_cache(maxsize=1)
def universe():
    lexicon = Lexicon.load(ROOT / "data" / "lexicon.json")
    bundle = pipeline.Bundle.load()
    return lexicon, bundle


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/architecture")
def architecture():
    return {"stages": STAGES, "edges": [[a["id"], b["id"]] for a, b in zip(STAGES, STAGES[1:])]}


@app.post("/api/run")
def run(req: RunRequest):
    lexicon, bundle = universe()
    base = list(bundle.rows)
    page = (base[-1].page + 1) if base else 0
    new = []
    for i, r in enumerate(req.rows):
        if i and r.date != req.rows[i - 1].date:
            page += 1
        new.append(Row(r.id, r.text, r.date, "", page))
    res = pipeline.run(base + new, lexicon, bundle, claims=req.include_claims)
    trace = to_trace(new, res)
    return trace


@app.get("/api/sample")
def sample():
    path = ROOT / "sample" / "sample.csv"
    if not path.exists():
        return {"rows": [], "note": "sample/sample.csv appears at 09:00 on 29 Oct"}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {"rows": [{"id": r["id"], "text": r["text"], "date": r["date"]} for r in csv.DictReader(f)]}


@lru_cache(maxsize=1)
def _claims():
    lexicon, bundle = universe()
    res = pipeline.run(list(bundle.rows), lexicon, bundle)
    return to_trace([], res)["claims"]


@app.get("/api/claims")
def claims():
    return {"claims": _claims()}


if (ROOT / "web" / "dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "web" / "dist", html=True), name="web")
