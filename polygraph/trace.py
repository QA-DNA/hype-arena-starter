"""The trace JSON the frontend draws: what every stage did to every row.

The contract is documented in docs/BRIEF_frontend.md; change both together.
"""
from __future__ import annotations

from .model import Row


def to_trace(rows: list[Row], result, max_claims: int = 1000) -> dict:
    verdicts = {v.id: v for v in result.verdicts}
    keys = set()
    out_rows = []
    for r in rows:
        v = verdicts.get(r.id)
        facts = []
        for f in result.facts.get(r.id, []):
            keys.add((f.subject, f.attribute))
            status = next((d["status"] for d in (v.facts if v else [])
                           if d["subject"] == f.subject and d["attribute"] == f.attribute), "unknown")
            facts.append({"subject": f.subject, "attribute": f.attribute, "value": f.value,
                          "span": list(f.span) if f.span else None, "status": status})
        out_rows.append({
            "id": r.id, "text": r.text, "date": r.date, "page": r.page,
            "given_label": r.label or None,
            "verdict": v.label if v else r.label, "confidence": v.confidence if v else None,
            "why": v.why if v else "labelled in the input", "facts": facts,
        })
    timelines = {}
    for key in keys:
        steps = result.kb.timeline(*key)
        timelines[f"{key[0]}|{key[1]}"] = {
            "steps": [{"from": s.start, "to": s.end, "value": s.value, "confidence": s.confidence,
                       "support": s.support} for s in steps],
            "mentions": result.kb.mentions.get(key, []),
        }
    return {
        "stages": result.stages,
        "rows": out_rows,
        "timelines": timelines,
        "claims": [{"id": c.id, "type": c.type, "text": c.text, "form": c.form,
                    "confidence": round(c.confidence, 3), "sources": c.sources}
                   for c in result.claims[:max_claims]],
    }
