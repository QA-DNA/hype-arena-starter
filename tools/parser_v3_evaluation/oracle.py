"""A small independent typed oracle, never an English parser.

All facts are invented by the factory. Only the public lexicon constrains names
and attributes. Decimal strings are converted directly to exact fractions.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
import re

KINDS = frozenset({"quantity", "money", "percent", "date", "version",
                   "duration", "name", "boolean"})
OPS = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})
INVERSE = {"eq": "ne", "ne": "eq", "lt": "ge", "le": "gt", "gt": "le", "ge": "lt"}
PHYSICAL = {
    "B": ("data", 1), "KB": ("data", 1000), "MB": ("data", 10**6),
    "GB": ("data", 10**9), "TB": ("data", 10**12),
    "mm": ("length", Fraction(1, 1000)), "cm": ("length", Fraction(1, 100)),
    "m": ("length", 1), "km": ("length", 1000), "in": ("length", Fraction(127, 5000)),
    "g": ("mass", 1), "kg": ("mass", 1000), "mAh": ("charge", 1),
    "Hz": ("frequency", 1), "kHz": ("frequency", 1000),
    "MHz": ("frequency", 10**6), "GHz": ("frequency", 10**9),
    "mW": ("power", Fraction(1, 1000)), "W": ("power", 1), "kW": ("power", 1000),
}
DURATION = {
    "ms": ("fixed", Fraction(1, 1000)), "s": ("fixed", 1),
    "min": ("fixed", 60), "h": ("fixed", 3600), "day": ("fixed", 86400),
    "week": ("fixed", 604800), "month": ("calendar", 1), "year": ("calendar", 12),
}
UNIT_ALIASES = {
    "byte": "B", "bytes": "B", "kilobyte": "KB", "kilobytes": "KB", "kB": "KB", "kb": "KB",
    "megabyte": "MB", "megabytes": "MB", "mb": "MB", "gigabyte": "GB", "gigabytes": "GB", "gb": "GB",
    "terabyte": "TB", "terabytes": "TB", "tb": "TB", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "inch": "in", "inches": "in", "kilogram": "kg", "kilograms": "kg", "gram": "g", "grams": "g",
    "watt": "W", "watts": "W", "kilowatt": "kW", "kilowatts": "kW",
    "millisecond": "ms", "milliseconds": "ms", "second": "s", "seconds": "s", "sec": "s",
    "minute": "min", "minutes": "min", "hour": "h", "hours": "h", "hr": "h",
    "days": "day", "d": "day", "weeks": "week", "wk": "week", "months": "month", "mo": "month", "mth": "month",
    "years": "year", "yr": "year", "people": "person", "companies": "company",
}


def rational(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("boolean/null is not a numeric value")
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite():
            raise ValueError("non-finite numeric value")
        return Fraction(decimal)
    except (InvalidOperation, TypeError) as error:
        raise ValueError("invalid numeric value") from error


def unit_key(unit):
    if not isinstance(unit, str) or not unit:
        raise ValueError("unit must be a nonempty string")
    unit = UNIT_ALIASES.get(unit, unit)
    if unit in PHYSICAL or unit in DURATION:
        return unit
    return unit[:-1] if unit.endswith("s") else unit


def typed(value):
    """Return (kind, channel, exact value); comparisons retain channel identity."""
    if not isinstance(value, dict): raise ValueError("typed value must be an object")
    kind = value.get("kind")
    raw = value.get("value")
    if kind not in KINDS:
        raise ValueError("unknown value kind")
    if kind in {"quantity", "duration"}:
        unit = unit_key(value.get("unit"))
        table = PHYSICAL if kind == "quantity" else DURATION
        dimension, factor = table.get(unit, ("count:" + unit, 1))
        if kind == "duration" and unit not in DURATION:
            raise ValueError("unknown duration unit")
        return kind, dimension, rational(raw) * factor
    if kind == "money":
        currency = value.get("currency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("money needs an ISO currency")
        period = value.get("per")
        if period is not None:
            period = unit_key(period)
            if period not in {"day", "week", "month", "year"}:
                raise ValueError("invalid billing period")
        return kind, (currency, period), rational(raw)
    if kind == "percent":
        return kind, None, rational(raw)
    if kind == "boolean":
        if type(raw) is not bool:
            raise ValueError("boolean must be a JSON boolean")
        return kind, None, raw
    if kind == "version":
        if not isinstance(raw, str) or not re.fullmatch(r"\d+(?:\.\d+)*", raw):
            raise ValueError("invalid version")
        return kind, len(raw.split(".")), tuple(int(x) for x in raw.split("."))
    if kind == "date":
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", raw):
            raise ValueError("invalid date")
        from datetime import date
        parts = tuple(int(x) for x in raw.split("-"))
        date(*((*parts, 1, 1)[:3]))
        return kind, len(parts), parts
    if not isinstance(raw, str) or not raw:
        raise ValueError("name must be a nonempty string")
    return kind, None, " ".join(raw.casefold().split())


def value_key(value):
    kind, channel, exact = typed(value)
    # Version component count is an equality property; lexicographic numeric
    # tuples remain ordered across component counts.
    return kind, channel, exact


def compare(left, right, op="eq"):
    if op not in OPS:
        raise ValueError("invalid comparison operator")
    lk, lc, lv = typed(left)
    rk, rc, rv = typed(right)
    if lk != rk:
        return None
    if lk in {"version", "date"}:
        if op in {"eq", "ne"}:
            result = lc == rc and lv == rv
            return result if op == "eq" else not result
        if lk == "date" and lc != rc:
            return None
    elif lc != rc:
        return None
    if lk in {"name", "boolean"} and op not in {"eq", "ne"}:
        return None
    if op == "eq": return lv == rv
    if op == "ne": return lv != rv
    if op == "lt": return lv < rv
    if op == "le": return lv <= rv
    if op == "gt": return lv > rv
    return lv >= rv


def channel(value):
    kind, dimension, _ = typed(value)
    # All version arities occupy the same factual channel.
    return (kind, None if kind in {"version", "date"} else dimension)


def lookup(world, ref, threshold=None):
    matches = [fact for fact in world if fact["subject"] == ref["subject"]
               and fact["attribute"] == ref["attribute"]]
    if threshold is not None:
        matches = [fact for fact in matches if channel(fact["channel"]) == channel(threshold)]
    if len(matches) != 1 or matches[0]["value"] is None:
        return None
    return matches[0]["value"]


def evaluate(ast, world):
    if ast is None:
        return None
    kind = ast.get("type")
    if kind == "atom":
        fact = ast["fact"]
        query = fact["value"]
        actual = lookup(world, fact, query)
        return None if actual is None else compare(actual, query, query.get("op", "eq"))
    if kind == "compare":
        left = lookup(world, ast["left"])
        right = lookup(world, ast["right"])
        return None if left is None or right is None else compare(left, right, ast["op"])
    if kind == "not":
        truth = evaluate(ast["child"], world)
        return None if truth is None else not truth
    if kind in {"all", "any"}:
        truths = [evaluate(child, world) for child in ast["children"]]
        if not truths:
            raise ValueError("empty connective")
        dominant = False if kind == "all" else True
        if any(truth is dominant for truth in truths):
            return dominant
        return None if any(truth is None for truth in truths) else not dominant
    raise ValueError("unknown AST node")


def label(truth):
    return "unsure" if truth is None else "true" if truth else "false"


def canonical_fact(fact, negate=False):
    if not isinstance(fact, dict): raise ValueError("fact must be an object")
    if not isinstance(fact.get("subject"), str) or not isinstance(fact.get("attribute"), str):
        raise ValueError("fact subject/attribute must be strings")
    value = fact["value"]
    op = value.get("op", "eq")
    if op not in OPS:
        raise ValueError("invalid fact operator")
    if negate:
        op = INVERSE[op]
    kind, dimension, exact = typed(value)
    if kind == "boolean" and op in {"eq", "ne"}:
        exact = exact if op == "eq" else not exact
        op = "eq"
    return (fact["subject"], fact["attribute"], op, kind, dimension, exact)


def canonical_ast(ast, negate=False):
    """Negation normal form, preserving scope, exact values and typed channels.

    Flattening and sorting accept associative/commutative variants. De Morgan
    and inverted inequalities accept logically identical representations.
    """
    if ast is None:
        return None
    kind = ast.get("type")
    if kind == "not":
        return canonical_ast(ast["child"], not negate)
    if kind == "atom":
        return ("atom", canonical_fact(ast["fact"], negate))
    if kind == "compare":
        op = INVERSE[ast["op"]] if negate else ast["op"]
        left = tuple((key, ast["left"][key]) for key in ("subject", "attribute", "date") if key in ast["left"])
        right = tuple((key, ast["right"][key]) for key in ("subject", "attribute", "date") if key in ast["right"])
        return ("compare", left, op, right)
    if kind in {"all", "any", "and", "or"}:
        kind = {"and": "all", "or": "any"}.get(kind, kind)
        if negate:
            kind = "any" if kind == "all" else "all"
        children = []
        for child in ast["children"]:
            normalized = canonical_ast(child, negate)
            children.extend(normalized[1] if normalized[0] == kind else [normalized])
        if not children:
            raise ValueError("empty connective")
        return children[0] if len(children) == 1 else (kind, tuple(sorted(set(children), key=repr)))
    raise ValueError("unknown AST node")


def assertions(ast, negate=False):
    """Flat NNF leaf set; never equates a disjunction to a conjunction."""
    if ast is None:
        return []
    if ast["type"] == "not":
        return assertions(ast["child"], not negate)
    if ast["type"] == "atom":
        fact = deepcopy(ast["fact"])
        if negate:
            fact["value"]["op"] = INVERSE[fact["value"].get("op", "eq")]
        return [fact]
    if ast["type"] == "compare":
        return []
    return [fact for child in ast["children"] for fact in assertions(child, negate)]


def ast_facts(ast):
    if ast is None:
        return []
    if ast["type"] == "atom":
        return [ast["fact"]]
    if ast["type"] == "compare":
        return []
    if ast["type"] == "not":
        return ast_facts(ast["child"])
    return [fact for child in ast["children"] for fact in ast_facts(child)]


def validate_ast(ast, lexicon):
    allowed = {subject["name"]: set(subject["attributes"]) for subject in lexicon["subjects"]}
    def validate_ref(ref):
        if not isinstance(ref, dict): raise ValueError("fact reference must be an object")
        if ref.get("attribute") not in allowed.get(ref.get("subject"), set()):
            raise ValueError("reference outside public lexicon")
    def walk(node, depth=0):
        if not isinstance(node, dict): raise ValueError("AST node must be an object")
        if depth > 128: raise ValueError("AST depth limit")
        kind = node.get("type")
        if kind == "atom":
            validate_ref(node["fact"])
            if not isinstance(node["fact"].get("value"), dict): raise ValueError("value must be an object")
            typed(node["fact"]["value"])
            if node["fact"]["value"].get("op", "eq") not in OPS:
                raise ValueError("invalid op")
        elif kind == "compare":
            validate_ref(node["left"])
            validate_ref(node["right"])
            if node["op"] not in OPS: raise ValueError("invalid op")
        elif kind == "not":
            walk(node["child"], depth + 1)
        elif kind in {"all", "any"}:
            if len(node["children"]) < 2: raise ValueError("connective needs two children")
            for child in node["children"]: walk(child, depth + 1)
        else:
            raise ValueError("invalid AST node")
    if ast is not None:
        walk(ast)


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
