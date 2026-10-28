"""Stage 1: the value parser, a clone of the referee's contracts/value-forms.md.

It does two jobs:
- reads the values in every input sentence (for labelling), and
- reads our own claim texts back (validate.py), so a claim the referee would not read
  never ships.

STATUS: stub. Phase 1 (Claude, branch `engine`) implements it. Until then parse_values
returns nothing and tests/test_reader.py marks the contract examples as expected failures.
"""
from __future__ import annotations

from .model import ValueSpan

IMPLEMENTED = False

NEGATIONS = {"not", "no", "never", "none", "nobody", "nothing", "neither", "nor", "without", "cannot"}


def parse_values(text: str) -> list[ValueSpan]:
    """Every value the text states, in reading order, each with its span.

    A value reads as value-forms.md says: whole, with its comparison words (as `op`) and its
    unit. Approximations, range ends and ambiguous numbers read as nothing. A value after a
    negation in its clause is returned with negated=True (the referee ignores it).
    """
    return []


def sentences(text: str) -> list[tuple[int, int]]:
    """Spans of the sentences of a text: a sentence ends at . ! or ? before a space, or at a
    blank line; abbreviations (e.g., Inc., Dr., an initial) end nothing."""
    import re
    abbrev = re.compile(r"(?:e\.g|i\.e|vs|approx|Inc|Ltd|Co|Corp|Dr|Mr|Mrs|Ms|Prof|St|No|[A-Z])\.$")
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?=\s)|\n\s*\n", text):
        if m.group(0) == "." and abbrev.search(text[start:m.end()]):
            continue
        spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans
