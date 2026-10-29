"""Independent value/phrase grammar for the factory's declared language subset.

Not a production extractor or the organizer's private referee. Gold comes from
the oracle's structured world, never from interpreting unsupported prose here.
"""

from __future__ import annotations

import re
from fractions import Fraction

from .oracle import (QUANTITY_UNITS, OracleError, canonical_name,
                     canonical_quantity_unit, partial_date, rational, version)


SMALL = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()
WORDS = {word: index for index, word in enumerate(SMALL)}
WORDS.update({word: 10 * index for index, word in enumerate(TENS) if index >= 2})
MONTHS = ("January February March April May June July August September October November December").split()

OPERATOR_PHRASES = {
    "eq": ("", "exactly ", "only ", "just "),
    "ne": ("different from ", "not equal to "),
    "lt": ("under ", "less than ", "below ", "lower than "),
    "le": ("at most ", "no more than ", "not more than ", "up to "),
    "gt": ("over ", "more than ", "above ", "greater than "),
    "ge": ("at least ", "no less than ", "not less than ", "minimum "),
}
DATE_OPERATOR_PHRASES = {
    "eq": ("", "exactly "), "ne": ("different from ", "not equal to "),
    "lt": ("before ", "prior to "), "le": ("by ", "no later than "),
    "gt": ("after ", "later than "), "ge": ("no earlier than ",),
}


def number_words(number: int) -> str:
    if not 0 <= number < 100:
        raise OracleError("number-word renderer is limited to 0..99")
    if number < 20:
        return SMALL[number]
    return TENS[number // 10] + ("-" + SMALL[number % 10] if number % 10 else "")


def decimal_text(number: Fraction) -> str:
    """Finite decimal only. No context rounding or approximate values allowed."""
    number = rational(number)
    denominator, twos, fives = number.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise OracleError("a repeating rational has no exact finite-decimal surface form")
    places = max(twos, fives)
    scaled = number.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled)).rjust(places + 1, "0")
    if places:
        return sign + (digits[:-places] + "." + digits[-places:]).rstrip("0").rstrip(".")
    return sign + digits


def render_number(number: str | Fraction | int, style: int, *, percent: bool = False) -> str:
    number = rational(number)
    if style % 6 == 1 and number.denominator == 1 and 0 <= number < 100:
        return number_words(int(number))
    # The contract rejects a lone decimal point with exactly three following
    # digits outside percentages. Equivalent longer representation is explicit.
    text = decimal_text(number)
    if not percent and re.fullmatch(r"-?\d+\.\d{3}", text):
        text += "0"
    if style % 6 == 2 and abs(number) >= 1000:
        integer, dot, fraction = text.partition(".")
        integer = f"{int(integer):,}"
        return integer + (dot + fraction if dot else "")
    if style % 6 == 3 and number >= 10000:
        scaled = decimal_text(number / 1000)
        if not percent and re.fullmatch(r"-?\d+\.\d{3}", scaled):
            scaled += "0"
        return scaled + " thousand"
    if style % 6 == 4 and number >= 1000000:
        scaled = decimal_text(number / 1000000)
        if not percent and re.fullmatch(r"-?\d+\.\d{3}", scaled):
            scaled += "0"
        return scaled + "M"
    if re.fullmatch(r"(?:19|20)\d{2}", text):
        return f"{int(text):,}"
    return text


def parse_number(text: str, *, money: bool = False, percent: bool = False) -> Fraction:
    text = text.strip()
    lower = text.casefold()
    if lower in WORDS:
        return Fraction(WORDS[lower])
    bits = re.split(r"[- ]", lower)
    if len(bits) == 2 and bits[0] in TENS[2:] and bits[1] in SMALL[1:10]:
        return Fraction(WORDS[bits[0]] + WORDS[bits[1]])
    scale = Fraction(1)
    match = re.fullmatch(r"(.+?)(?:\s*(thousand|million|billion|bn|k|M))", text)
    if match:
        text, suffix = match.groups()
        scale = {"thousand": 1000, "k": 1000, "million": 10**6, "M": 10**6,
                 "billion": 10**9, "bn": 10**9}[suffix]
    if money and re.fullmatch(r"-?\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    if not re.fullmatch(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
        raise OracleError(f"unsupported/ambiguous number: {text!r}")
    if not percent and re.fullmatch(r"-?\d+\.\d{3}", text):
        raise OracleError("three-digit decimal ambiguity outside percentages")
    return rational(text.replace(",", "")) * scale


def render_value(value: dict, style: int) -> str:
    kind, raw = value["kind"], value["value"]
    if kind == "boolean":
        return "yes" if raw else "no"
    if kind == "name":
        return raw
    if kind == "date":
        bits = partial_date(raw)
        if len(bits) == 1 or style % 3 == 0:
            return raw
        month = MONTHS[bits[1] - 1]
        if len(bits) == 2:
            return f"{month} {bits[0]}"
        return (f"{bits[2]} {month} {bits[0]}" if style % 3 == 1
                else f"{month} {bits[2]}, {bits[0]}")
    if kind == "version":
        version(raw)
        return ("v" if style % 2 == 0 else "version ") + raw
    number = render_number(raw, style, percent=(kind == "percent"))
    if kind == "percent":
        return number + ("%" if style % 2 else " percent")
    if kind == "money":
        if style % 7 == 0:
            number = decimal_text(rational(raw))
            if "." in number and len(number.split(".")[1]) <= 2:
                number = number.replace(".", ",")
        prefix = {"EUR": "€", "USD": "US$", "GBP": "£"}.get(value["currency"])
        base = (prefix + number if prefix and style % 2 == 0
                else number + " " + value["currency"])
        period = value.get("per")
        if not period:
            return base
        suffix = (f" per {period}", f"/{period}", f" a {period}")[style % 3]
        return base + suffix
    if kind in ("quantity", "duration"):
        unit = value["unit"]
        # A counted noun is pluralized only with the explicitly listed suffix.
        if kind == "quantity" and canonical_quantity_unit(unit) not in QUANTITY_UNITS:
            unit += "s" if rational(raw) != 1 else ""
        elif kind == "duration" and unit in ("day", "week", "month", "year"):
            unit += "s" if rational(raw) != 1 else ""
        return f"{number} {unit}"
    raise OracleError("renderer does not know this kind")


def parse_value(text: str, kind: str, aliases: dict[str, str]) -> dict:
    """Parse an isolated value, not an entire sentence or hidden gold form."""
    text = text.strip()
    if any(char in text for char in ("\u200b", "\u2060", "\u00ad")):
        raise OracleError("invisible character in value")
    result: dict = {"kind": kind}
    if kind == "boolean":
        if text.casefold() not in ("yes", "no", "not"):
            raise OracleError("bounded boolean literals are yes/no/not")
        result["value"] = text.casefold() == "yes"
    elif kind == "name":
        result["value"] = canonical_name(text, aliases)
    elif kind == "version":
        match = re.fullmatch(r"(?:v|version |ver\. )(\d+(?:\.\d+){0,3})", text)
        if not match:
            raise OracleError("unsupported version surface")
        version(match.group(1))
        result["value"] = match.group(1)
    elif kind == "date":
        if re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", text):
            partial_date(text)
            result["value"] = text
        else:
            patterns = [
                (r"(\d{1,2}) (\w+) (\d{4})", (2, 1, 0)),
                (r"(\w+) (\d{1,2}), (\d{4})", (2, 0, 1)),
                (r"(\w+) (\d{4})", (1, 0, None)),
            ]
            for pattern, order in patterns:
                match = re.fullmatch(pattern, text)
                if match:
                    groups = match.groups()
                    try:
                        month = MONTHS.index(groups[order[1]]) + 1
                    except ValueError as exc:
                        raise OracleError("unrecognized month") from exc
                    result["value"] = f"{int(groups[order[0]]):04}-{month:02}"
                    if order[2] is not None:
                        result["value"] += f"-{int(groups[order[2]]):02}"
                    partial_date(result["value"])
                    break
            else:
                raise OracleError("unsupported/ambiguous date surface")
    elif kind == "money":
        period = re.search(r"(?: per | a |/)(day|week|month|year)$", text)
        if period:
            result["per"] = period.group(1)
            text = text[:period.start()]
        match = re.fullmatch(r"(€|US\$|\$|£)(.+)|(.+) ([A-Z]{3})|([A-Z]{3}) (.+)", text)
        if not match:
            raise OracleError("unsupported money surface")
        if match.group(1):
            result["currency"] = {"€": "EUR", "US$": "USD", "$": "USD", "£": "GBP"}[match.group(1)]
            number = match.group(2)
        elif match.group(3):
            result["currency"], number = match.group(4), match.group(3)
        else:
            result["currency"], number = match.group(5), match.group(6)
        result["value"] = decimal_text(parse_number(number, money=True))
    elif kind == "percent":
        match = re.fullmatch(r"(.+?)(?:\s*%| percent| per cent)", text)
        if not match:
            raise OracleError("unsupported percent surface")
        result["value"] = decimal_text(parse_number(match.group(1), percent=True))
    elif kind in ("quantity", "duration"):
        match = re.fullmatch(r"(.+) ([A-Za-z][A-Za-z0-9_]*)", text)
        if not match:
            raise OracleError("unsupported quantity/duration surface")
        number, unit = match.groups()
        if kind == "quantity" and re.fullmatch(r"(?:19|20)\d{2}", number):
            raise OracleError("a plain four-digit year is not an unambiguous count")
        if kind == "quantity":
            unit = canonical_quantity_unit(unit)
        if unit in ("days", "weeks", "months", "years") or unit.endswith("s") and unit not in (
            "ms", "s", "Hz", "kHz", "MHz", "GHz"
        ):
            unit = unit[:-1]
        result.update(value=decimal_text(parse_number(number)), unit=unit)
    else:
        raise OracleError("unknown isolated value kind")
    return result


def parse_comparison(text: str) -> tuple[str, str]:
    # Longest first prevents 'no more than' from becoming a negated 'more than'.
    phrases = sorted(((phrase, op) for mapping in (OPERATOR_PHRASES, DATE_OPERATOR_PHRASES)
                      for op, items in mapping.items() for phrase in items if phrase),
                     key=lambda pair: -len(pair[0]))
    for phrase, op in phrases:
        if text.startswith(phrase):
            return op, text[len(phrase):]
    return "eq", text
