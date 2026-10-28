"""Stage 3: decide which attribute each value in a sentence is about.

Input: the row, the values the reader found, the subjects the linker found.
Output: Facts (subject, attribute, value).

Model (Phase 1): a scorer trained on the ~2,400 practice facts, using
- which value kinds and units each attribute takes (e.g. `programming_languages` -> quantity/language),
- cue words near the value (learned from practice + build-time cue lists in artifacts/cues.json),
- which subject is nearest to the value.

STATUS: stub. Returns no facts until the reader is implemented.
"""
from __future__ import annotations

from .lexicon import Lexicon
from .linker import Mention
from .model import Fact, Row, ValueSpan


class Attributor:
    def __init__(self, lexicon: Lexicon, training: list[tuple[Row, list[dict]]] | None = None):
        """`training`: (row, its gold facts) pairs from the practice data bundled in the image."""
        self.lexicon = lexicon
        self.training = training or []

    def assign(self, row: Row, values: list[ValueSpan], mentions: list[Mention]) -> list[Fact]:
        return []
