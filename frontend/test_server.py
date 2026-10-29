"""Smoke check: the frontend's run_system labels the sample and returns 1,000 unique claims.

    .venv/bin/python frontend/test_server.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import SAMPLE, run_system

res = run_system(SAMPLE.read_text(encoding="utf-8"))
assert len(res["labels"]) == 20, len(res["labels"])
for l in res["labels"]:
    assert l["label"] in ("true", "false", "unsure"), l
    assert (l["confidence"] == "") == (l["label"] == "unsure"), l
    if l["confidence"] != "":
        assert 0.5 <= float(l["confidence"]) <= 1.0, l
assert len(res["claims"]) == 1000
assert len({c["id"] for c in res["claims"]}) == 1000
sample_texts = {l["text"] for l in res["labels"]}
assert not any(c["text"] in sample_texts for c in res["claims"])
try:
    run_system("id,text,date,label\n")
    raise AssertionError("no unlabelled rows must be rejected")
except ValueError:
    pass
print("ok")
