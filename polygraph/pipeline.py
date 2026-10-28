"""The whole system as one function, used by run.py (Docker), scripts/eval.py and server/app.py."""
from __future__ import annotations

import os
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
OOF_FOLDS = 5
RECONCILE = os.environ.get("POLY_RECONCILE", "1") == "1"  # let the knowledge base correct extraction


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
        gold_extraction: bool = False, cache: str | Path | None = None) -> Result:
    """Label every unlabelled row and write the claims.

    gold_extraction: use the practice forms as the extraction of unlabelled rows too
    (eval only): measures the truth engine alone, as if extraction were perfect.
    cache: (eval only) a pickle file holding the extraction stages' output, so experiments
    on the truth engine and judge skip the slow extraction.
    """
    stages: list[dict] = []

    def stage(name, t0, count):
        stages.append({"name": name, "ms": round((time.perf_counter() - t0) * 1000, 1), "count": count})

    t = time.perf_counter()
    linker = Linker(lexicon, derived=True)
    mentions = link_pages(linker, rows)
    stage("linker", t, sum(1 for ms in mentions.values() for m in ms if m.start >= 0))

    t = time.perf_counter()
    values = {r.id: reader.parse_values(r.text, [(m.start, m.end) for m in mentions[r.id] if m.start >= 0])
              for r in rows}
    stage("reader", t, sum(map(len, values.values())))

    if cache and Path(cache).exists():
        import pickle
        facts, extracted = pickle.loads(Path(cache).read_bytes())
        stages.append({"name": "attributor", "ms": 0.0, "count": sum(map(len, facts.values()))})
    else:
        t = time.perf_counter()
        facts, extracted = _extract(rows, lexicon, bundle, gold_extraction, linker, mentions, values)
        stage("attributor", t, sum(map(len, facts.values())))
        if cache:
            import pickle
            Path(cache).parent.mkdir(parents=True, exist_ok=True)
            Path(cache).write_bytes(pickle.dumps((facts, extracted)))

    # what the knowledge base may use to correct extraction (judge.reconcile)
    ctx = None
    if not gold_extraction and RECONCILE:
        ctx = {"readings": {rid: [(v.value, v.start, v.end) for v in vs if not v.negated] +
                                 [(a, v.start, v.end) for v in vs if not v.negated for a in v.alts]
                            for rid, vs in values.items()},
               "subjects": {rid: [m.subject for m in ms] for rid, ms in mentions.items()}}

    t = time.perf_counter()
    truth.TIMER["ms"] = 0.0
    verdicts, fitted = judge.label(rows, facts, lexicon, extracted, ctx)
    facts = getattr(fitted, "facts", facts)
    kb = fitted.kb
    total = (time.perf_counter() - t) * 1000
    stages.append({"name": "truth", "ms": round(truth.TIMER["ms"], 1), "count": len(kb.timelines)})
    stages.append({"name": "judge", "ms": round(total - truth.TIMER["ms"], 1), "count": len(verdicts)})

    t = time.perf_counter()
    out_claims = forge.generate(kb, {normalize_text(r.text) for r in rows}) if claims else []
    stages.append({"name": "forge", "ms": round((time.perf_counter() - t) * 1000, 1), "count": len(out_claims)})

    return Result(verdicts, out_claims, kb, facts, stages)


def _extract(rows, lexicon, bundle, gold_extraction, linker, mentions, values):
    """The attributor: every row's facts, plus the out-of-fold extraction of the labelled
    rows (see judge.label)."""
    # train the attributor on the practice rows the input labels (never on a hidden one)
    labelled = {r.id for r in rows if r.label}
    train = [r for r in bundle.rows if r.id in labelled and r.id in bundle.forms]
    facts: dict[str, list[Fact]] = {}  # the best facts we have: gold for labelled practice rows
    for r in rows:
        if r.id in bundle.forms and (r.label or gold_extraction):
            facts[r.id] = [Fact(f["subject"], f["attribute"], f["value"]) for f in bundle.forms[r.id]]
    todo = [r for r in rows if r.id not in facts]
    # what extraction makes of the labelled rows, from a model that never saw them: the judge
    # trains on these so it learns on facts as noisy as an unlabelled row's
    extracted: dict[str, list[Fact]] = {}
    if train:
        bundle_mentions = link_pages(linker, bundle.rows)
        attributor = attributor_mod.Attributor(lexicon).fit(train, bundle.forms, bundle_mentions)
        if todo:
            for r, fs in zip(todo, attributor.assign_many([(r, values[r.id], mentions[r.id]) for r in todo])):
                facts[r.id] = fs
        if not gold_extraction:
            page_of = {r.id: r.page for r in bundle.rows}
            labelled_rows = [r for r in rows if r.id in labelled and r.id in page_of]
            for k in range(OOF_FOLDS):
                tr = [r for r in train if page_of[r.id] % OOF_FOLDS != k]
                te = [r for r in labelled_rows if page_of[r.id] % OOF_FOLDS == k]
                if not tr or not te:
                    continue
                att_k = attributor_mod.Attributor(lexicon).fit(tr, bundle.forms, bundle_mentions)
                for r, fs in zip(te, att_k.assign_many([(r, values[r.id], mentions[r.id]) for r in te])):
                    extracted[r.id] = fs
    return facts, extracted


def link_pages(linker: Linker, rows: list[Row]) -> dict:
    out = {}
    for _, page in groupby(rows, key=lambda r: r.page):
        page = list(page)
        for r, ms in zip(page, linker.link_page([r.text for r in page])):
            out[r.id] = ms
    return out


def load_universe(folder: str | Path) -> tuple[list[Row], Lexicon]:
    folder = Path(folder)
    return read_rows(folder / "universe.csv"), Lexicon.load(folder / "lexicon.json")
