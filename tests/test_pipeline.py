"""The whole system end to end on the practice data, with every 5th label hidden."""
import re
from dataclasses import replace

from polygraph import pipeline
from polygraph.linker import Linker
from polygraph.render import render
from polygraph.validate import validate


def test_linker_longest_name(lexicon):
    found = [m.subject for m in Linker(lexicon).find("Hooly AI Pro costs more than hooly  workspace and Hooly.")]
    assert found == ["Hooly AI Pro", "Hooly Workspace", "Hooly"]


def test_render():
    assert render({"kind": "money", "value": 59, "currency": "EUR", "per": "month"}) == "€59 per month"
    assert render({"kind": "quantity", "value": 2048, "unit": "customer"}) == "2,048 customers"
    assert render({"kind": "quantity", "value": 12, "unit": "person"}) == "12 people"
    assert render({"kind": "date", "value": "2026-07-01"}) == "1 July 2026"
    assert render({"kind": "duration", "value": 1.5, "unit": "s"}) == "1.5 seconds"
    assert render({"kind": "quantity", "value": 1.125, "unit": "GB"}) is None  # 3 decimals read as nothing


def test_end_to_end(lexicon, bundle):
    rows = [replace(r, label="" if i % 5 == 0 else r.label) for i, r in enumerate(bundle.rows)]
    res = pipeline.run(rows, lexicon, bundle)
    hidden = {r.id for r in rows if not r.label}
    assert {v.id for v in res.verdicts} == hidden
    for v in res.verdicts:
        assert v.label in ("true", "false", "unsure")
        assert (v.confidence is None) == (v.label == "unsure")
        assert v.confidence is None or 0.5 <= v.confidence <= 1
    assert len(res.claims) == 1000
    assert len({c.id for c in res.claims}) == 1000
    for c in res.claims:
        assert re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", c.id)
        assert not validate(c, lexicon), (c.text, validate(c, lexicon))
