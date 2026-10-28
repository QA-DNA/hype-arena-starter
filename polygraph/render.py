"""Writing a value in words exactly as contracts/value-forms.md reads it.

The forge uses this to put values into claim texts. Every form here must read back to the
same value through reader.parse_values (tests/test_render.py checks the round trip).
"""
from __future__ import annotations

import re

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
SYMBOL_UNITS = {"B", "KB", "MB", "GB", "TB", "mm", "cm", "m", "km", "in", "g", "kg", "mAh",
                "Hz", "kHz", "MHz", "GHz", "mW", "W", "kW"}
CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}
DURATION_WORD = {"ms": "ms", "s": "second", "min": "minute", "h": "hour", "day": "day",
                 "week": "week", "month": "month", "year": "year"}
IRREGULAR = {"person": "people", "inch": "inches", "child": "children", "man": "men",
             "woman": "women", "foot": "feet", "index": "indices"}


def number(x: float | int) -> str | None:
    """Digits with commas between thousands. None when the number cannot be written so
    that it reads unambiguously (three decimals reads as nothing outside a percentage)."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    if isinstance(x, int):
        return f"{x:,}"
    s = repr(x)
    if "e" in s:
        return None
    whole, frac = s.split(".")
    if len(frac) == 3:
        return None
    return f"{int(whole):,}.{frac}"


def plural(noun: str, n: float) -> str:
    if n == 1:
        return noun
    low = noun.lower()
    if low in IRREGULAR:
        return IRREGULAR[low]
    if re.search(r"(s|x|z|ch|sh)$", low):
        return noun + "es"
    if re.search(r"[^aeiou]y$", low):
        return noun[:-1] + "ies"
    return noun + "s"


def date(v: str) -> str:
    parts = v.split("-")
    if len(parts) == 3:
        return f"{int(parts[2])} {MONTHS[int(parts[1]) - 1]} {parts[0]}"
    if len(parts) == 2:
        return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return parts[0]


def render(v: dict) -> str | None:
    """The value as text, or None when it has no safe written form. Booleans have none:
    a yes or no is stated by the sentence's polarity (claim-forms.md)."""
    kind = v.get("kind")
    if kind == "quantity":
        n = number(v["value"])
        if n is None:
            return None
        unit = v["unit"]
        if unit in SYMBOL_UNITS:
            return f"{n} {unit}"
        return f"{n} {plural(unit, v['value'])}"
    if kind == "money":
        n = number(v["value"])
        if n is None:
            return None
        cur = v["currency"]
        s = f"{CURRENCY_SYMBOL[cur]}{n}" if cur in CURRENCY_SYMBOL else f"{n} {cur}"
        return f"{s} per {v['per']}" if v.get("per") else s
    if kind == "percent":
        n = number(v["value"]) if len(repr(v["value"]).split(".")[-1]) != 3 else repr(v["value"])
        return f"{n}%"
    if kind == "date":
        return date(v["value"])
    if kind == "version":
        return f"version {v['value']}"
    if kind == "duration":
        n = number(v["value"])
        if n is None:
            return None
        word = DURATION_WORD.get(v["unit"], v["unit"])
        return f"{n} {word}" if word == "ms" else f"{n} {plural(word, v['value'])}"
    if kind == "name":
        return v["value"]
    return None


def attribute_words(attribute: str) -> str:
    """`soc2_certified` -> `soc2 certified`: the attribute in words, as the referee reads it."""
    return attribute.replace("_", " ")
