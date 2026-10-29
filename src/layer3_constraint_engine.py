"""
Layer 3 - Symbolic Constraint Engine
====================================
A sentence is a conjunction of atoms  phi = A_1 AND ... AND A_n,
each atom  A_i := attr(subject, T) <op> value.

First-order evaluation over the temporal KB (three-valued, Kleene logic):
    atom  -> TRUE | FALSE | UNKNOWN
    AND   -> FALSE if any FALSE; TRUE if all TRUE; else UNKNOWN
(the contest rule: "false when the sentence states at least one false value").

Arithmetic: values are first brought to a canonical unit
(duration -> seconds, money -> (currency, per-period), percent -> float,
version -> tuple), then the claim's op (eq, lt, le, gt, ge) is checked as an
inequality with a relative tolerance eps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DURATION_S = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "day": 86400,
              "week": 604800, "month": 2629800, "year": 31557600}
PER_FACTOR = {"month": 12, "year": 1, "week": 52, "day": 365}   # -> per year
EPS = 1e-6

TRUE, FALSE, UNKNOWN = "true", "false", "unknown"


def _singular(u: str) -> str:
    u = (u or "").lower()
    return u[:-1] if u.endswith("s") and len(u) > 3 else u


def canonical(v: dict) -> tuple:
    """Kind-aware normal form used both for equality and as a hash key."""
    k = v.get("kind")
    x = v.get("value")
    if k == "duration":
        return ("duration", round(float(x) * DURATION_S.get(v.get("unit"), 1), 6))
    if k == "money":
        per = v.get("per")
        amount = float(x) * PER_FACTOR.get(per, 1) if per in PER_FACTOR else float(x)
        return ("money", v.get("currency"), "periodic" if per else "once", round(amount, 6))
    if k == "quantity":
        return ("quantity", _singular(v.get("unit")), round(float(x), 6))
    if k == "percent":
        return ("percent", round(float(x), 6))
    if k == "version":
        return ("version", tuple(int(p) if p.isdigit() else p for p in re.split(r"[.\-]", str(x))))
    if k == "boolean":
        return ("boolean", bool(x))
    if k == "name":
        return ("name", re.sub(r"\s+", " ", str(x).strip().lower()))
    if k == "date":
        return ("date", str(x)[:10])
    return (k, str(x))


def comparable(a: tuple, b: tuple) -> bool:
    """Same kind and same dimension (unit / currency / period type)."""
    return a[0] == b[0] and a[:-1] == b[:-1]


def compare(claimed: dict, actual: dict) -> str:
    """Is `claimed` (with its op) satisfied by `actual`?"""
    c, a = canonical(claimed), canonical(actual)
    if not comparable(c, a):
        return UNKNOWN
    op = claimed.get("op", "eq")
    cv, av = c[-1], a[-1]
    if c[0] == "date" and op == "eq":
        # "2026-01" (month precision) is consistent with "2026-01-12"
        short, long_ = sorted((cv, av), key=len)
        return TRUE if long_.startswith(short) else FALSE
    if c[0] == "name":
        # "Nimbus" vs "Nimbus Cloud": whole-word prefix of each other = same entity
        x, y = sorted((cv, av), key=len)
        return TRUE if x == y or y.startswith(x + " ") else FALSE
    if op == "eq" or c[0] == "boolean":
        if isinstance(cv, float):
            return TRUE if abs(cv - av) <= EPS * max(1, abs(av)) else FALSE
        return TRUE if cv == av else FALSE
    ok = {"lt": av < cv, "le": av <= cv, "gt": av > cv, "ge": av >= cv}.get(op)
    return UNKNOWN if ok is None else (TRUE if ok else FALSE)


@dataclass
class AtomResult:
    subject: str
    attribute: str
    claimed: dict
    verdict: str                  # true | false | unknown
    reason: str
    actual: dict | None = None
    support: int = 0
    allen: str = ""
    resolution_score: float = 1.0


@dataclass
class ClaimResult:
    verdict: str
    atoms: list = field(default_factory=list)


class ConstraintEngine:
    def __init__(self, kb, resolver):
        self.kb, self.resolver = kb, resolver

    def check_atom(self, atom: dict, day) -> AtomResult:
        subj_raw, attr, val = atom["subject"], atom["attribute"], atom["value"]
        res = self.resolver.resolve(subj_raw, attr)
        if res.canonical is None:
            return AtomResult(subj_raw, attr, val, UNKNOWN, "unknown_subject", resolution_score=0)
        subj = res.canonical
        if res.attribute_ok is False:
            return AtomResult(subj, attr, val, UNKNOWN, "attribute_not_in_lexicon",
                              resolution_score=res.score)
        st = self.kb.state_at(subj, attr, day)
        # explicit negative evidence on the same day
        for nv in st.negatives:
            if compare(val, nv) == TRUE and val.get("op", "eq") == "eq":
                return AtomResult(subj, attr, val, FALSE, "known_false_value", nv, 1,
                                  st.relation, res.score)
        if st.value is None:
            why = "no_data" if st.relation == "no_data" else "before_first_observation"
            return AtomResult(subj, attr, val, UNKNOWN, why, None, 0, st.relation, res.score)
        v = compare(val, st.value)
        reason = {TRUE: "matches_state", FALSE: "contradicts_state",
                  UNKNOWN: "incomparable_units"}[v]
        return AtomResult(subj, attr, val, v, reason, st.value, st.support, st.relation, res.score)

    def check(self, atoms: list[dict], day) -> ClaimResult:
        results = [self.check_atom(a, day) for a in atoms]
        verdicts = {r.verdict for r in results}
        if FALSE in verdicts:
            out = FALSE
        elif verdicts == {TRUE}:
            out = TRUE
        else:
            out = UNKNOWN
        return ClaimResult(out, results)
