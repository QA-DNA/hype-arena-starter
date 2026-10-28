"""Our clone of the referee's claim checks (contracts/claim-forms.md + entry.schema.json).

A claim ships only when validate() returns no problems.

STATUS: structural checks (schema, lexicon names, length, no copy of an input row, no
refused words). The text checks that need the reader (the sentence states exactly the
form's value, one value of its kind, no negation...) land once reader.IMPLEMENTED is True.
Owner: backend teammate (branch `forge`), see docs/BRIEF_backend.md.
"""
from __future__ import annotations

import re

from . import reader
from .lexicon import Lexicon
from .model import Claim

TYPES = {"fact", "compare", "change", "at_event", "relation"}
ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MONTHS_SEASONS_DAYS = ["January", "February", "March", "April", "May", "June", "July", "August",
                       "September", "October", "November", "December", "spring", "summer",
                       "autumn", "winter", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                       "Saturday", "Sunday"]
TIME_WORDS = ["ago", "yesterday", "tomorrow", "once", "formerly", "previously", "originally",
              "initially", "recently", "lately", "soon", "eventually", "then", "before", "after",
              "since", "until", "till", "earlier", "later", "used to", "last week", "last month",
              "last quarter", "last year", "next week", "next month", "next quarter", "next year",
              "in the past", "in the future", "at the time", "at that time"]
NEGATION = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n't\b", re.I)


def has_time_word(text: str) -> list[str]:
    found = []
    for w in TIME_WORDS:
        if re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", text, re.I):
            found.append(w)
    for w in MONTHS_SEASONS_DAYS:
        flags = 0 if w == "May" else re.I  # `may` is the month only when written May
        if re.search(r"(?<![A-Za-z])" + w + r"(?![A-Za-z])", text, flags):
            found.append(w)
    return found


def _names_ok(lex: Lexicon, subject: str, attribute: str | None, why: list[str], what: str):
    canon = lex.canonical(subject)
    if canon is None:
        why.append(f"{what}: unknown subject {subject!r}")
    elif attribute is not None and not lex.has(canon, attribute):
        why.append(f"{what}: {canon!r} has no attribute {attribute!r}")


def validate(claim: Claim, lex: Lexicon, input_texts: set[str] | None = None) -> list[str]:
    why: list[str] = []
    if not ID.match(claim.id):
        why.append("id")
    if claim.type not in TYPES:
        why.append("type")
    text = claim.text.strip()
    if not text or len(text) > 300:
        why.append("text length")
    if input_texts is not None and normalize_text(text) in input_texts:
        why.append("a copy of an input row")
    if not 0.5 <= claim.confidence <= 1:
        why.append("confidence")
    f = claim.form
    if claim.type in ("fact", "change", "at_event"):
        _names_ok(lex, f.get("subject", ""), f.get("attribute", ""), why, "subject")
    if claim.type == "at_event":
        if lex.canonical(f.get("event", "")) not in lex.events:
            why.append("event not in the lexicon's events")
    if claim.type == "compare":
        for side in ("left", "right"):
            _names_ok(lex, f.get(side, {}).get("subject", ""), f.get(side, {}).get("attribute", ""), why, side)
        if f.get("op") not in ("gt", "lt", "eq"):
            why.append("op")
    if claim.type == "relation":
        _names_ok(lex, f.get("subject", ""), f.get("link", ""), why, "link")
        _names_ok(lex, f.get("target", ""), f.get("attribute", ""), why, "target")
    for k in ("value", "from", "to"):
        if isinstance(f.get(k), dict) and "op" in f[k]:
            why.append(f"{k} has an op")
        # the referee resolves a name value through the lexicon's spellings only
        if isinstance(f.get(k), dict) and f[k].get("kind") == "name" and lex.canonical(f[k]["value"]) is None:
            why.append(f"{k}: name {f[k]['value']!r} is not in the lexicon")
    if claim.type != "change":
        rest = _outside_names(text, lex)
        v = f.get("value")
        if isinstance(v, dict) and v.get("kind") == "date":  # the value may be a date itself
            from .render import render
            rest = rest.replace(render(v) or "\0", " ")
        if claim.type == "compare":  # the op phrase's own words are allowed
            rest = re.sub(r"\b(?:later than|earlier than|after|before|on the same day as|the same day as)\b",
                          " ", rest, count=1, flags=re.I)
        if claim.type == "at_event":  # so is the event phrase
            rest = re.sub(r"\b(?:at the time of|on the day of)\b", " ", rest, count=1, flags=re.I)
        tw = has_time_word(rest)
        if tw:
            why.append(f"time words {tw}")
    if NEGATION.search(text) and not _is_boolean(claim):
        why.append("negation")
    if reader.IMPLEMENTED:
        pass  # TODO(forge): read the text back with reader.parse_values and check the values
    return why


def _is_boolean(claim: Claim) -> bool:
    f = claim.form
    return any(isinstance(f.get(k), dict) and f[k].get("kind") == "boolean" for k in ("value", "from", "to"))


def _outside_names(text: str, lex: Lexicon) -> str:
    """The text with every lexicon name blanked out: words inside names don't count."""
    from .linker import Linker
    linker = getattr(lex, "_linker", None) or Linker(lex)
    lex._linker = linker
    out = list(text)
    for m in linker.find(text):
        out[m.start:m.end] = " " * (m.end - m.start)
    return "".join(out)


def normalize_text(text: str) -> str:
    """How check_output.py compares a claim with the input rows."""
    return " ".join(text.lower().split()).rstrip(".!? ")
