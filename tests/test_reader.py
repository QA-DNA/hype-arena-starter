"""Every example table in contracts/value-forms.md is a test: `Written` must read as `Read as`,
and every row under "Not read" must NOT read as the value shown.

These are expected failures until the reader lands (reader.IMPLEMENTED = True).
"""
import json
import re
from pathlib import Path

import pytest

from polygraph import reader
from polygraph.model import value_key

DOC = Path(__file__).resolve().parent.parent / "contracts" / "value-forms.md"


def examples():
    read, not_read, section = [], [], ""
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].startswith("`") or "{" not in cells[1]:
            continue
        written = cells[0].strip("`")
        value = json.loads(cells[1].strip("`"))
        if value["kind"] in ("name", "boolean"):
            continue  # read by the attributor (they depend on the lexicon / the attribute)
        (not_read if section == "Not read" else read).append(pytest.param(written, value, id=f"{section}:{written}"))
    return read, not_read


READ, NOT_READ = examples()
pending = pytest.mark.xfail(not reader.IMPLEMENTED, reason="reader not implemented yet", strict=False)


@pending
@pytest.mark.parametrize("written,value", READ)
def test_reads(written, value):
    got = [value_key(v.value) for v in reader.parse_values(written) if not v.negated]
    assert value_key(value) in got


@pytest.mark.parametrize("written,value", NOT_READ)
def test_does_not_read(written, value):
    got = [value_key(v.value) for v in reader.parse_values(written) if not v.negated]
    assert value_key(value) not in got


def test_examples_found():
    assert len(READ) > 60 and len(NOT_READ) > 25


def test_sentences():
    text = "Hooly Inc. grew. It costs €59 per month! Dr. Who? Yes"
    spans = reader.sentences(text)
    assert [text[a:b].strip() for a, b in spans] == ["Hooly Inc. grew.", "It costs €59 per month!", "Dr. Who?", "Yes"]
