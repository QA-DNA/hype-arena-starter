"""The data types every stage passes along. Keep these stable: teammates code against them."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

# A value is a plain dict exactly as contracts/claimed_value.schema.json writes it, e.g.
# {"kind": "money", "value": 59, "currency": "EUR", "per": "month"}
Value = dict


@dataclass
class Row:
    id: str
    text: str
    date: str  # YYYY-MM-DD, the date of the page the sentence comes from
    label: str = ""  # "true" | "false" | "unsure" | "" (unlabelled: we must label it)
    page: int = -1  # index of the page (a run of consecutive rows with the same date)


@dataclass
class ValueSpan:
    """A value the reader found in a text, and where."""
    value: Value
    start: int
    end: int
    negated: bool = False
    alts: list = field(default_factory=list)  # other readings (e.g. another counted noun)


@dataclass
class Fact:
    """One (subject, attribute, value) a row states."""
    subject: str  # canonical lexicon name
    attribute: str
    value: Value
    span: Optional[tuple[int, int]] = None
    score: float = 1.0  # how sure the extraction is


@dataclass
class Step:
    """One stair of a fact's timeline: the value held from start up to (not incl.) end."""
    start: str
    end: Optional[str]  # None: still holds
    value: Value
    confidence: float = 1.0
    support: int = 1  # how many mentions back it
    last_seen: Optional[str] = None  # date of its last mention: between last_seen and the
    # next step's start, we don't know exactly when the value changed


@dataclass
class Verdict:
    id: str
    label: str  # "true" | "false" | "unsure"
    confidence: Optional[float]  # 0.5..1, None for unsure
    why: str = ""
    facts: list = field(default_factory=list)  # [{subject, attribute, value, status}]


@dataclass
class Claim:
    id: str
    type: str  # fact | compare | change | at_event | relation
    text: str
    form: dict
    confidence: float
    sources: list = field(default_factory=list)  # [{subject, attribute}] the facts it connects


# Units of one dimension compare after conversion (value-forms.md "Units convert").
# Months and years convert to each other, never to days.
DURATION_BASE = {"ms": ("s", 0.001), "s": ("s", 1), "min": ("s", 60), "h": ("s", 3600),
                 "day": ("s", 86400), "week": ("s", 604800), "month": ("mo", 1), "year": ("mo", 12)}
QUANTITY_BASE = {"B": ("B", 1), "KB": ("B", 1e3), "MB": ("B", 1e6), "GB": ("B", 1e9), "TB": ("B", 1e12),
                 "mm": ("m", 0.001), "cm": ("m", 0.01), "m": ("m", 1), "km": ("m", 1000), "in": ("m", 0.0254),
                 "inch": ("m", 0.0254),
                 "g": ("g", 1), "kg": ("g", 1000), "mAh": ("mAh", 1),
                 "Hz": ("Hz", 1), "kHz": ("Hz", 1e3), "MHz": ("Hz", 1e6), "GHz": ("Hz", 1e9),
                 "mW": ("W", 0.001), "W": ("W", 1), "kW": ("W", 1000)}


def _num(x):
    x = round(float(x), 9)
    return int(x) if x.is_integer() else x


def value_key(v: Value) -> str:
    """A hashable key for a value: equal keys = values the referee holds equal
    (14 days == 2 weeks, 1 GB == 1,000 MB)."""
    v = dict(v)
    if v.get("op") == "eq":
        v.pop("op")
    kind = v.get("kind")
    if kind == "duration" and v.get("unit") in DURATION_BASE:
        base, f = DURATION_BASE[v["unit"]]
        v["unit"], v["value"] = base, _num(v["value"] * f)
    elif kind == "quantity" and isinstance(v.get("unit"), str):
        if v["unit"] in QUANTITY_BASE:
            base, f = QUANTITY_BASE[v["unit"]]
            v["unit"], v["value"] = base, _num(v["value"] * f)
        else:
            v["unit"] = v["unit"].lower()
    if isinstance(v.get("value"), (int, float)) and not isinstance(v.get("value"), bool):
        v["value"] = _num(v["value"])
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def same_value(a: Value, b: Value) -> bool:
    """Equal values, or two dates where one is the other written less precisely
    (2026-01 and 2026-01-12): both are true of the same fact."""
    if value_key(a) == value_key(b):
        return True
    if a.get("kind") == b.get("kind") == "date" and a.get("op", "eq") == b.get("op", "eq"):
        x, y = str(a["value"]), str(b["value"])
        return x.startswith(y) or y.startswith(x)
    return False


def more_precise(a: Value, b: Value) -> Value:
    return a if len(str(a.get("value"))) >= len(str(b.get("value"))) else b


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
