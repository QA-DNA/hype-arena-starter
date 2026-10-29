"""Combine two public-text parser passes using public known-label availability."""
import argparse
import json
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-context", type=Path, required=True)
    parser.add_argument("--with-context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plain = json.loads(args.without_context.read_text(encoding="utf-8"))
    contextual = json.loads(args.with_context.read_text(encoding="utf-8"))
    if len(plain) != len(contextual):
        raise ValueError("Parser passes have different lengths")
    result = []
    anchors = 0
    for a, b in zip(plain, contextual):
        if (a["id"], a["date"], a["text"], a["label"]) != (b["id"], b["date"], b["text"], b["label"]):
            raise ValueError("Parser pass identity/order mismatch")
        known = bool(a["label"])
        anchors += known
        result.append(a if known else b)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"rows":len(result),"context_off_public_anchors":anchors,"context_on_targets":len(result)-anchors,"gold_access":False}))
