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
    start: int  # -1: not in this sentence, but elsewhere on its page
    end: int
    written: str
    row_gap: int = 0  # page context only: rows to the nearest row that names it
    page_count: int = 0  # how many sentences of the page name it
    page_first: bool = False  # the first subject the page names (its topic, usually)
    earlier: bool = False  # page context only: named in an earlier sentence


def derived_aliases(lexicon: Lexicon) -> dict[str, str]:
    """Short names people use that the lexicon doesn't list: the name without "Hooly "
    (Workspace, Photos Lite) and a unique last word (Lite, Enterprise). For reading input
    rows only; claims always use the lexicon's own spellings."""
    known = lexicon.all_names()
    out: dict[str, str] = {}
    last: dict[str, set] = {}
    for s in lexicon.subjects:
        if s.lower().startswith("hooly ") and len(s) > 9:
            out.setdefault(norm(s[6:]), s)
        w = s.split()[-1]
        if len(s.split()) >= 3 and w[:1].isupper() and not w[:1].isdigit():
            last.setdefault(norm(w), set()).add(s)
    for w, subs in last.items():
        if len(subs) == 1:
            out.setdefault(w, next(iter(subs)))
    return {k: v for k, v in out.items() if k not in known}


class Linker:
    def __init__(self, lexicon: Lexicon, derived: bool = False):
        self.lexicon = lexicon
        self.extra = derived_aliases(lexicon) if derived else {}
        spellings = sorted([*lexicon.all_names(), *self.extra], key=len, reverse=True)  # longest first
        parts = []
        for s in spellings:
            words = [re.escape(w) for w in s.split(" ")]
            parts.append(r"\s*".join(words))
        # a name never ends inside a number: "Hooly Android 17.0" is Hooly Android + version 17.0
        self.pattern = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(parts) + r")(?![A-Za-z0-9]|\.\d)",
                                  re.IGNORECASE)
        self._squashed = {re.sub(r"\s+", "", k): v for k, v in lexicon.all_names().items()}

    def find(self, text: str, cased: bool = False) -> list[Mention]:
        """cased=False matches like the referee (any case). cased=True is for reading input
        rows: a lower-case "photos" or "search" is a word, not Hooly Photos or Hooly Search."""
        out = []
        for m in self.pattern.finditer(text):
            written = m.group(0)
            if cased and written[0].islower():
                continue
            subject = (self.lexicon.canonical(written) or self._squashed.get(re.sub(r"\s+", "", norm(written)))
                       or self.extra.get(norm(written)))
            if subject:
                out.append(Mention(subject, m.start(), m.end(), written))
        return out

    def link_page(self, texts: list[str]) -> list[list[Mention]]:
        """Mentions for each sentence of one page: its own, then every other subject the page
        names, as context (start = end = -1). A sentence like "9 integrations live" or "He
        begins with 4 engineers" is about a subject named elsewhere on its page."""
        own = [self.find(t, cased=True) for t in texts]
        rows_of: dict[str, list[int]] = {}
        for i, ms in enumerate(own):
            for m in ms:
                rows_of.setdefault(m.subject, [])
                if not rows_of[m.subject] or rows_of[m.subject][-1] != i:
                    rows_of[m.subject].append(i)
        first = next((ms[0].subject for ms in own if ms), None)
        out = []
        for i, ms in enumerate(own):
            here = {m.subject for m in ms}
            for m in ms:
                m.page_count, m.page_first = len(rows_of[m.subject]), m.subject == first
            ctx = []
            for s, rws in rows_of.items():
                if s in here:
                    continue
                gap = min(abs(j - i) for j in rws)
                ctx.append(Mention(s, -1, -1, "", gap, len(rws), s == first, min(rws) < i))
            ctx.sort(key=lambda m: (m.row_gap, not m.earlier))
            out.append(ms + ctx)
        return out
