"""The knowledge base: each fact's timeline as a staircase of Steps.

The truth engine fills it from all rows; until then `KB.from_gold` builds it from the
practice rows' `form` column (the facts the organizers extracted), so the forge and the
frontend can be built against real data from minute one.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from . import AS_OF
from .lexicon import Lexicon
from .model import Row, Step, more_precise, same_value


class KB:
    def __init__(self, lexicon: Lexicon):
        self.lexicon = lexicon
        self.timelines: dict[tuple[str, str], list[Step]] = {}
        # every mention behind a timeline, for the frontend's evidence board:
        # (subject, attribute) -> [{date, value, row_id, verdict}]
        self.mentions: dict[tuple[str, str], list[dict]] = defaultdict(list)

    # ---- reading -------------------------------------------------------------------
    def timeline(self, subject: str, attribute: str) -> list[Step]:
        return self.timelines.get((subject, attribute), [])

    def value_on(self, subject: str, attribute: str, day: str) -> Optional[Step]:
        """The step that holds on `day` (YYYY-MM-DD), or None."""
        for s in self.timeline(subject, attribute):
            if s.start <= day and (s.end is None or day < s.end):
                return s
        return None

    def current(self, subject: str, attribute: str) -> Optional[Step]:
        """The value on the as-of date, 29 Oct 2026."""
        return self.value_on(subject, attribute, AS_OF)

    def facts(self) -> Iterable[tuple[str, str]]:
        return self.timelines.keys()

    @property
    def events(self) -> dict[str, str]:
        """Event name -> its date (YYYY-MM-DD or coarser), from the event's `date` fact."""
        out = {}
        for e in self.lexicon.events:
            step = self.current(e, "date") or (self.timeline(e, "date") or [None])[-1]
            if step is not None:
                out[e] = step.value["value"]
        return out

    def links(self) -> dict[tuple[str, str], list[Step]]:
        """(subject, link attribute) -> steps whose value names another lexicon entity,
        e.g. (Hooly, cto) -> [Step(value={"kind": "name", "value": "Bertram Gilfoil"})]."""
        out = {}
        for (subj, attr), steps in self.timelines.items():
            if steps and all(s.value.get("kind") == "name" and self.lexicon.canonical(s.value["value"])
                             for s in steps):
                out[(subj, attr)] = steps
        return out

    # ---- building ------------------------------------------------------------------
    @staticmethod
    def staircase(points: list[tuple[str, dict]], weights: Optional[list[float]] = None) -> list[Step]:
        """Collapse dated (date, value) points that are all believed true into Steps:
        consecutive equal values merge; a step ends where the next one starts."""
        if not points:
            return []
        order = sorted(range(len(points)), key=lambda i: points[i][0])
        steps: list[Step] = []
        for i in order:
            d, v = points[i]
            w = weights[i] if weights else 1.0
            if steps and same_value(steps[-1].value, v):
                s = steps[-1]
                s.value = more_precise(s.value, v)
                s.support += 1
                s.confidence = max(s.confidence, w)
                s.last_seen = d
                continue
            if steps and steps[-1].start == d:
                # two values on one day: keep the better supported one
                if w > steps[-1].confidence:
                    steps[-1] = Step(d, None, v, w, 1, d)
                continue
            if steps:
                steps[-1].end = d
            steps.append(Step(d, None, v, w, 1, d))
        return steps

    @classmethod
    def from_gold(cls, lexicon: Lexicon, rows: list[Row], forms: dict[str, list[dict]]) -> "KB":
        """A KB from the labelled rows' gold forms. Only rows labelled `true` place points;
        a row whose label is hidden (empty) is left out, so evaluation never leaks."""
        kb = cls(lexicon)
        points: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
        for r in rows:
            for f in forms.get(r.id, []):
                key = (f["subject"], f["attribute"])
                if r.label:
                    kb.mentions[key].append({"date": r.date, "value": f["value"], "row_id": r.id,
                                             "verdict": r.label})
                if r.label == "true" and f["value"].get("op", "eq") == "eq":
                    points[key].append((r.date, f["value"]))
        for key, pts in points.items():
            kb.timelines[key] = cls.staircase(pts)
        return kb
