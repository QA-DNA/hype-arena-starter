"""Exact, deliberately bounded counterfactual temporal-world semantics.

This module was independently written from the public contracts, not ported from
the Rust solver.  Unsupported semantics raise OracleError; they NEVER become an
``unsure`` gold label.  Only an explicitly unknown public world interval does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Iterable


LABELS = ("true", "false", "unsure")
OPERATORS = ("eq", "ne", "lt", "le", "gt", "ge")
KINDS = ("quantity", "money", "percent", "date", "version", "duration", "name", "boolean")


class OracleError(ValueError):
    """Invalid/unsupported generator semantics, not an epistemic world gap."""


def rational(value: Any) -> Fraction:
    """Accept exact decimal/rational representations; reject binary floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise OracleError("numeric values must be exact, never bool or binary float")
    try:
        result = value if isinstance(value, Fraction) else Fraction(Decimal(str(value)))
    except (ValueError, ArithmeticError) as exc:
        raise OracleError(f"invalid exact number: {value!r}") from exc
    return result


# Factors are literal rationals. Calendar months belong to a separate dimension.
QUANTITY_UNITS = {
    "B": ("data", Fraction(1)), "KB": ("data", Fraction(1000)),
    "MB": ("data", Fraction(10**6)), "GB": ("data", Fraction(10**9)),
    "TB": ("data", Fraction(10**12)),
    "mm": ("length", Fraction(1, 1000)), "cm": ("length", Fraction(1, 100)),
    "m": ("length", Fraction(1)), "km": ("length", Fraction(1000)),
    "in": ("length", Fraction(127, 5000)),
    "g": ("mass", Fraction(1)), "kg": ("mass", Fraction(1000)),
    "mAh": ("charge", Fraction(1)),
    "Hz": ("frequency", Fraction(1)), "kHz": ("frequency", Fraction(1000)),
    "MHz": ("frequency", Fraction(10**6)), "GHz": ("frequency", Fraction(10**9)),
    "mW": ("power", Fraction(1, 1000)), "W": ("power", Fraction(1)),
    "kW": ("power", Fraction(1000)),
}
# Keep the canonical factor table (and the factory's sampling vocabulary) fixed.
# These are spellings explicitly listed by contracts/value-forms.md, not fuzzy
# suffix stripping or case folding of case-sensitive SI symbols.
QUANTITY_SYMBOL_ALIASES = {"kB": "KB", "kb": "KB", "mb": "MB", "gb": "GB", "tb": "TB"}
QUANTITY_WORD_ALIASES = {
    alias: unit
    for unit, words in {
        "B": ("byte", "bytes"), "KB": ("kilobyte", "kilobytes"),
        "MB": ("megabyte", "megabytes"), "GB": ("gigabyte", "gigabytes", "gig", "gigs"),
        "TB": ("terabyte", "terabytes"),
        "mm": ("millimetre", "millimetres", "millimeter", "millimeters"),
        "cm": ("centimetre", "centimetres", "centimeter", "centimeters"),
        "m": ("metre", "metres", "meter", "meters"),
        "km": ("kilometre", "kilometres", "kilometer", "kilometers"),
        "in": ("inch", "inches"),
        "g": ("gram", "grams", "gramme", "grammes"),
        "kg": ("kilogram", "kilograms", "kilo", "kilos"),
        "Hz": ("hertz",), "kHz": ("kilohertz",),
        "MHz": ("megahertz",), "GHz": ("gigahertz",),
        "mW": ("milliwatt", "milliwatts"), "W": ("watt", "watts"),
        "kW": ("kilowatt", "kilowatts"),
    }.items()
    for alias in words
}


def canonical_quantity_unit(unit: str) -> str:
    """Resolve only declared physical spellings; leave counted nouns untouched."""
    if unit in QUANTITY_UNITS:
        return unit
    return QUANTITY_SYMBOL_ALIASES.get(unit, QUANTITY_WORD_ALIASES.get(unit.casefold(), unit))


DURATION_UNITS = {
    "ms": ("elapsed", Fraction(1, 1000)), "s": ("elapsed", Fraction(1)),
    "min": ("elapsed", Fraction(60)), "h": ("elapsed", Fraction(3600)),
    "day": ("elapsed", Fraction(86400)), "week": ("elapsed", Fraction(604800)),
    "month": ("calendar", Fraction(1)), "year": ("calendar", Fraction(12)),
}


def partial_date(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        raise OracleError(f"invalid ISO partial date: {value!r}")
    bits = tuple(map(int, value.split("-")))
    try:
        date(bits[0], bits[1] if len(bits) > 1 else 1, bits[2] if len(bits) > 2 else 1)
    except ValueError as exc:
        raise OracleError(f"invalid date: {value!r}") from exc
    return bits


def version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", value):
        raise OracleError(f"unsupported version (numeric components only): {value!r}")
    return tuple(map(int, value.split(".")))


def name_key(value: str) -> str:
    return "".join(value.casefold().split())


def alias_map(lexicon: dict) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for subject in lexicon["subjects"]:
        for name in [subject["name"], *subject.get("aliases", [])]:
            key = name_key(name)
            if key in aliases and aliases[key] != subject["name"]:
                raise OracleError(f"ambiguous lexicon alias: {name}")
            aliases[key] = subject["name"]
    return aliases


def canonical_name(value: str, aliases: dict[str, str]) -> str:
    try:
        return aliases[name_key(value)]
    except KeyError as exc:
        raise OracleError(f"unpublished name: {value!r}") from exc


def channel(value: dict) -> str:
    kind = value["kind"]
    if kind == "money":
        currency, period = value.get("currency"), value.get("per", "once")
        if not re.fullmatch(r"[A-Z]{3}", str(currency)) or period not in (
            "once", "day", "week", "month", "year"
        ):
            raise OracleError("invalid money currency/period")
        return f"money:{currency}:{period}"
    if kind in ("quantity", "duration"):
        unit = value.get("unit", "")
        if kind == "quantity":
            unit = canonical_quantity_unit(unit)
        table = QUANTITY_UNITS if kind == "quantity" else DURATION_UNITS
        if unit in table:
            dimension = table[unit][0]
        elif kind == "quantity" and re.fullmatch(r"[a-z][a-z0-9_]*", unit):
            dimension = f"count:{unit}"
        else:
            raise OracleError(f"unsupported unit: {kind}/{unit}")
        return f"{kind}:{dimension}"
    if kind not in KINDS:
        raise OracleError(f"unsupported value kind: {kind}")
    return kind


def normalized(value: dict, aliases: dict[str, str]) -> Any:
    kind = value["kind"]
    channel(value)  # Validate even nonnumeric fields before comparison.
    raw = value["value"]
    if kind in ("money", "quantity", "duration", "percent"):
        result = rational(raw)
        if kind in ("money", "duration") and result < 0:
            raise OracleError(f"negative {kind}")
        if kind in ("quantity", "duration"):
            table = QUANTITY_UNITS if kind == "quantity" else DURATION_UNITS
            unit = canonical_quantity_unit(value["unit"]) if kind == "quantity" else value["unit"]
            result *= table.get(unit, (None, Fraction(1)))[1]
        return result
    if kind == "date":
        return partial_date(raw)
    if kind == "version":
        return version(raw)
    if kind == "name":
        return canonical_name(raw, aliases)
    if kind == "boolean":
        if type(raw) is not bool:
            raise OracleError("boolean value must be a JSON boolean")
        return raw
    raise OracleError(f"unsupported value: {value}")


def compare(actual: dict, asserted: dict, op: str, aliases: dict[str, str]) -> str:
    if op not in OPERATORS:
        raise OracleError(f"unsupported operator: {op}")
    if channel(actual) != channel(asserted):
        raise OracleError("comparison across dimensions/currencies/periods is undefined")
    if actual["kind"] in ("name", "boolean") and op not in ("eq", "ne"):
        raise OracleError("names and booleans have equality/inequality only")
    left, right = normalized(actual, aliases), normalized(asserted, aliases)
    if actual["kind"] == "date" and len(left) != len(right) and op not in ("eq", "ne"):
        raise OracleError("mixed-precision date ordering is outside this factory's domain")
    predicates = {
        "eq": lambda: left == right, "ne": lambda: left != right,
        "lt": lambda: left < right, "le": lambda: left <= right,
        "gt": lambda: left > right, "ge": lambda: left >= right,
    }
    return "true" if predicates[op]() else "false"


def conjunction(labels: Iterable[str]) -> str:
    labels = tuple(labels)
    if not labels or any(label not in LABELS for label in labels):
        raise OracleError("conjunction needs at least one valid component")
    if "false" in labels:
        return "false"
    return "unsure" if "unsure" in labels else "true"


@dataclass(frozen=True)
class Segment:
    start: date
    end: date
    value: dict | None
    reason: str = ""

    @classmethod
    def load(cls, raw: dict) -> "Segment":
        result = cls(date.fromisoformat(raw["start"]), date.fromisoformat(raw["end"]),
                     raw.get("value"), raw.get("reason", ""))
        if result.start > result.end or (result.value is None and result.reason != "explicit_gap"):
            raise OracleError("invalid or undocumented world interval")
        return result

    def dump(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(),
                "value": self.value, "reason": self.reason}


class World:
    def __init__(self, timelines: list[dict], lexicon: dict):
        self.lexicon = lexicon
        self.aliases = alias_map(lexicon)
        self.timelines: dict[tuple[str, str, str], list[Segment]] = {}
        legal = {item["name"]: set(item["attributes"]) for item in lexicon["subjects"]}
        for timeline in timelines:
            subject = canonical_name(timeline["subject"], self.aliases)
            attribute, slot = timeline["attribute"], timeline["channel"]
            if attribute not in legal[subject]:
                raise OracleError(f"unpublished subject/attribute: {subject}/{attribute}")
            key = (subject, attribute, slot)
            if key in self.timelines:
                raise OracleError(f"duplicate timeline: {key}")
            segments = [Segment.load(raw) for raw in timeline["segments"]]
            if not segments:
                raise OracleError("empty timeline")
            for index, segment in enumerate(segments):
                if index and (segment.start - segments[index - 1].end).days != 1:
                    raise OracleError("intervals must cover the scope without overlaps or implicit gaps")
                if segment.value is not None:
                    if channel(segment.value) != slot:
                        raise OracleError("interval value has the wrong channel")
                    normalized(segment.value, self.aliases)
            self.timelines[key] = segments

    def lookup(self, subject: str, attribute: str, at: str, value: dict) -> Segment:
        key = (canonical_name(subject, self.aliases), attribute, channel(value))
        if key not in self.timelines:
            raise OracleError(f"undeclared world channel; not an automatic unsure: {key}")
        day = date.fromisoformat(at)
        for segment in self.timelines[key]:
            if segment.start <= day <= segment.end:
                return segment
        raise OracleError("date outside the explicitly published evaluation scope")

    def evaluate(self, assertion: dict, at: str) -> tuple[str, str]:
        # Validate the asserted value even when the world interval is unknown.
        normalized(assertion["value"], self.aliases)
        op = assertion.get("op", "eq")
        if op not in OPERATORS:
            raise OracleError("invalid assertion operator")
        if assertion["value"]["kind"] in ("name", "boolean") and op not in ("eq", "ne"):
            raise OracleError("undefined ordered name/boolean assertion")
        segment = self.lookup(assertion["subject"], assertion["attribute"], at, assertion["value"])
        if segment.value is None:
            return "unsure", "explicit_gap"
        return compare(segment.value, assertion["value"], op, self.aliases), "known_interval"

    def evaluate_all(self, assertions: list[dict], at: str) -> tuple[str, list[dict]]:
        parts = [self.evaluate(assertion, at) for assertion in assertions]
        return conjunction(label for label, _ in parts), [
            {"label": label, "reason": reason} for label, reason in parts
        ]


def resolve_public_context(text: str, context: dict, lexicon: dict) -> str:
    """Resolve only the public declaration at actual recorded character bounds.

    There is deliberately no row-id -> gold subject table or private fallback.
    Span indices are Unicode code-point offsets, half-open, within this same row.
    """
    start, end = context["declaration_span"]
    if not (0 <= start < end <= len(text)):
        raise OracleError("invalid public context bounds")
    declaration = text[start:end]
    match = re.fullmatch(r"Record subject: (.+)\.\s*", declaration)
    if not match:
        raise OracleError("context does not contain a unique public subject declaration")
    return canonical_name(match.group(1), alias_map(lexicon))
