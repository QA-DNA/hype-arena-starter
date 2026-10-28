"""Reading the input table and writing the output table (contracts/README.md)."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from .model import Claim, Row, Verdict, dumps

COLUMNS = ["id", "type", "text", "form", "label", "confidence"]


def read_rows(path: str | Path) -> list[Row]:
    """Rows of universe.csv (or practice.csv), with pages numbered: a page is a run of
    consecutive rows sharing a date."""
    rows: list[Row] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        page, last = -1, None
        for r in csv.DictReader(f):
            if r["date"] != last:
                page, last = page + 1, r["date"]
            rows.append(Row(r["id"], r["text"], r["date"], (r.get("label") or "").strip().lower(), page))
    return rows


def read_practice_forms(path: str | Path) -> dict[str, list[dict]]:
    """id -> the facts the practice row states (its `form` column)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["id"]: json.loads(r["form"]) for r in csv.DictReader(f) if r.get("form")}


def _conf(c: float | None) -> str:
    return "" if c is None else f"{min(1.0, max(0.5, c)):.3f}"


def write_output(path: str | Path, verdicts: list[Verdict], claims: list[Claim]) -> None:
    """Write the table under a temporary name, then rename it, so a half-written table
    never counts (contracts/README.md)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".partial")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for v in verdicts:
            w.writerow([v.id, "", "", "", v.label, "" if v.label == "unsure" else _conf(v.confidence)])
        for c in claims:
            w.writerow([c.id, c.type, c.text, dumps(c.form), "true", _conf(c.confidence)])
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
