"""The whole system as one function, used by run.py (Docker), scripts/eval.py and server/app.py."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path

from . import attributor as attributor_mod
from . import forge, judge, reader, truth
from .kb import KB
from .lexicon import Lexicon
from .linker import Linker
from .model import Claim, Fact, Row, Verdict
from .tables import read_practice_forms, read_rows
from .validate import normalize_text

BUNDLED_PRACTICE = Path(__file__).resolve().parent.parent / "data" / "practice.csv"


@dataclass
class Result:
    verdicts: list[Verdict]
    claims: list[Claim]
    kb: KB
    facts: dict[str, list[Fact]]
    stages: list[dict] = field(default_factory=list)  # [{name, ms, count}] for the diagram


@dataclass
class Bundle:
    """What the image carries besides code: the practice rows with their gold forms."""
    forms: dict[str, list[dict]]
    rows: list[Row]

    @classmethod
    def load(cls, practice: str | Path = BUNDLED_PRACTICE) -> "Bundle":
        return cls(read_practice_forms(practice), read_rows(practice))


def run(rows: list[Row], lexicon: Lexicon, bundle: Bundle, *, claims: bool = True,
        gold_extraction: bool = False) -> Result:
    """Label every unlabelled row and write the claims.

    gold_extraction: use the practice forms as the extraction of unlabelled rows too
    (eval only): measures the truth engine alone, as if extraction were perfect.
    """
    stages: list[dict] = []

    def stage(name, t0, count):
        stages.append({"name": name, "ms": round((time.perf_counter() - t0) * 1000, 1), "count": count})

    t = time.perf_counter()
    values = {r.id: reader.parse_values(r.text) for r in rows}
    stage("reader", t, sum(map(len, values.values())))

    t = time.perf_counter()
    linker = Linker(lexicon)
    mentions = {}
    for _, page in groupby(rows, key=lambda r: r.page):
        page = list(page)
        for r, ms in zip(page, linker.link_page([r.text for r in page])):
            mentions[r.id] = ms
    stage("linker", t, sum(map(len, mentions.values())))

    t = time.perf_counter()
    attributor = attributor_mod.Attributor(lexicon, [(r, bundle.forms[r.id]) for r in bundle.rows if r.id in bundle.forms])
    facts: dict[str, list[Fact]] = {}
    for r in rows:
        if gold_extraction and r.id in bundle.forms:
            facts[r.id] = [Fact(f["subject"], f["attribute"], f["value"]) for f in bundle.forms[r.id]]
        else:
            facts[r.id] = attributor.assign(r, values[r.id], mentions[r.id])
    stage("attributor", t, sum(map(len, facts.values())))

    t = time.perf_counter()
    labelled_forms = {r.id: bundle.forms[r.id] for r in rows if r.label and r.id in bundle.forms}
    kb = truth.build_kb(lexicon, rows, facts, labelled_forms)
    stage("truth", t, len(kb.timelines))

    t = time.perf_counter()
    verdicts = judge.label(rows, facts, kb)
    stage("judge", t, len(verdicts))

    t = time.perf_counter()
    out_claims = forge.generate(kb, {normalize_text(r.text) for r in rows}) if claims else []
    stage("forge", t, len(out_claims))

    return Result(verdicts, out_claims, kb, facts, stages)


def load_universe(folder: str | Path) -> tuple[list[Row], Lexicon]:
    folder = Path(folder)
    return read_rows(folder / "universe.csv"), Lexicon.load(folder / "lexicon.json")
