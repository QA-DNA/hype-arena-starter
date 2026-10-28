"""Stage 2: find which lexicon subjects a sentence names.

Names match as whole words, in any case, with or without the spaces between their words,
and a name inside a longer name names the longer one only (claim-forms.md, General rules).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .lexicon import Lexicon, norm


@dataclass
class Mention:
    subject: str  # canonical name
    start: int
    end: int
    written: str


class Linker:
    def __init__(self, lexicon: Lexicon):
        self.lexicon = lexicon
        spellings = sorted(lexicon.all_names(), key=len, reverse=True)  # longest first
        parts = []
        for s in spellings:
            words = [re.escape(w) for w in s.split(" ")]
            parts.append(r"\s*".join(words))
        self.pattern = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9])",
                                  re.IGNORECASE)
        self._squashed = {re.sub(r"\s+", "", k): v for k, v in lexicon.all_names().items()}

    def find(self, text: str) -> list[Mention]:
        out = []
        for m in self.pattern.finditer(text):
            written = m.group(0)
            subject = self.lexicon.canonical(written) or self._squashed.get(re.sub(r"\s+", "", norm(written)))
            if subject:
                out.append(Mention(subject, m.start(), m.end(), written))
        return out

    def link_page(self, texts: list[str]) -> list[list[Mention]]:
        """Mentions for each sentence of one page. A sentence that names nobody ("Its paid
        accounts...", "He begins...") inherits the page's last named subject, marked by a
        mention with start = end = -1."""
        out, last = [], None
        for t in texts:
            ms = self.find(t)
            if ms:
                last = ms[-1].subject
            elif last:
                ms = [Mention(last, -1, -1, "")]
            out.append(ms)
        return out
