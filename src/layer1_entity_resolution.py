"""
Layer 1 - Fuzzy Entity Resolution
=================================
Maps a raw subject string ("hooly ai", "Pixel Buds", "Gemini") to the canonical
subject name of lexicon.json, and checks the attribute belongs to that subject.

Math:
  * Jaro similarity      J = 1/3 (m/|s1| + m/|s2| + (m-t)/m)
  * Jaro-Winkler         JW = J + l * p * (1 - J)      (l = common prefix <= 4, p = 0.1)
  * Levenshtein distance d(s1, s2) with a band cut-off k (Ukkonen): O(k * n)
    instead of O(n * m) -> behaves like a Levenshtein automaton for small k.
Pipeline: exact alias hash (O(1)) -> token-subset / suffix match -> fuzzy JW + Lev.
Pure standard library: runs offline in the Docker image.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

_WS = re.compile(r"[\s\-_]+")
_PUNCT = re.compile(r"[^\w\s/.\-]")


def normalize(s: str) -> str:
    """Lower-case, strip accents, possessives and punctuation, collapse spaces."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("’", "'")
    s = re.sub(r"'s\b", "", s)
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


# ---------------------------------------------------------------- similarity
def jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    l1, l2 = len(s1), len(s2)
    if not l1 or not l2:
        return 0.0
    window = max(l1, l2) // 2 - 1
    m1, m2 = [False] * l1, [False] * l2
    matches = 0
    for i, c in enumerate(s1):
        lo, hi = max(0, i - window), min(i + window + 1, l2)
        for j in range(lo, hi):
            if not m2[j] and s2[j] == c:
                m1[i] = m2[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    t, k = 0, 0
    for i in range(l1):
        if m1[i]:
            while not m2[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    t /= 2
    return (matches / l1 + matches / l2 + (matches - t) / matches) / 3


def jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    j = jaro(s1, s2)
    prefix = 0
    for a, b in zip(s1[:4], s2[:4]):
        if a != b:
            break
        prefix += 1
    return j + prefix * p * (1 - j)


def levenshtein_bounded(a: str, b: str, k: int) -> int:
    """Edit distance, or k+1 as soon as it is known to exceed k (banded DP)."""
    if abs(len(a) - len(b)) > k:
        return k + 1
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        lo, hi = max(1, i - k), min(len(b), i + k)
        cur = [k + 1] * (len(b) + 1)
        cur[0] = i if i <= k else k + 1
        for j in range(lo, hi + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        if min(cur[lo - 1:hi + 1]) > k:
            return k + 1
        prev = cur
    return min(prev[len(b)], k + 1)


# ---------------------------------------------------------------- resolver
@dataclass
class Resolution:
    query: str
    canonical: str | None
    score: float                 # 1.0 exact, <1 fuzzy
    method: str                  # exact | token | fuzzy | none
    attribute_ok: bool | None = None
    alternatives: list = field(default_factory=list)


class EntityResolver:
    def __init__(self, lexicon: dict, jw_threshold: float = 0.90, max_edits: int = 2):
        self.jw_threshold = jw_threshold
        self.max_edits = max_edits
        self.attributes: dict[str, set[str]] = {}
        self.alias_to_name: dict[str, str] = {}
        for subj in lexicon.get("subjects", []):
            name = subj["name"]
            self.attributes[name] = set(subj.get("attributes", []))
            for alias in [name, *subj.get("aliases", [])]:
                self.alias_to_name.setdefault(normalize(alias), name)
        self.events = {normalize(e): e for e in lexicon.get("events", [])}
        # Longest aliases first -> "hooly ai pro" wins over "hooly" (lexicon rule).
        self._aliases_sorted = sorted(self.alias_to_name, key=len, reverse=True)

    @classmethod
    def from_file(cls, path: str, **kw) -> "EntityResolver":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), **kw)

    @lru_cache(maxsize=65536)
    def resolve(self, query: str, attribute: str | None = None) -> Resolution:
        q = normalize(query)
        # 1) exact alias hash
        if q in self.alias_to_name:
            return self._finish(query, self.alias_to_name[q], 1.0, "exact", attribute)
        # 2) token match: "the hooly gemini app" contains alias "hooly gemini";
        #    or query is a unique suffix ("gemini" -> "Hooly Gemini")
        padded = f" {q} "
        for alias in self._aliases_sorted:
            if f" {alias} " in padded:
                return self._finish(query, self.alias_to_name[alias], 0.97, "token", attribute)
        suffix = [a for a in self._aliases_sorted if a.endswith(" " + q)]
        if attribute:
            suffix = [a for a in suffix if attribute in self.attributes[self.alias_to_name[a]]] or suffix
        if len({self.alias_to_name[a] for a in suffix}) == 1:
            return self._finish(query, self.alias_to_name[suffix[0]], 0.95, "token", attribute)
        # 3) fuzzy: Jaro-Winkler ranking, Levenshtein as a hard gate
        scored = []
        for alias in self._aliases_sorted:
            jw = jaro_winkler(q, alias)
            if jw < self.jw_threshold - 0.1:
                continue
            d = levenshtein_bounded(q, alias, self.max_edits)
            if d <= self.max_edits or jw >= self.jw_threshold:
                bonus = 0.02 if attribute and attribute in self.attributes[self.alias_to_name[alias]] else 0
                scored.append((jw - 0.03 * d + bonus, alias))
        scored.sort(reverse=True)
        if scored and scored[0][0] >= self.jw_threshold - 0.05:
            best = self.alias_to_name[scored[0][1]]
            res = self._finish(query, best, round(min(scored[0][0], 0.94), 4), "fuzzy", attribute)
            res.alternatives = [self.alias_to_name[a] for _, a in scored[1:4]]
            return res
        return Resolution(query, None, 0.0, "none", None)

    def _finish(self, query, name, score, method, attribute):
        ok = None if attribute is None else attribute in self.attributes.get(name, set())
        return Resolution(query, name, score, method, ok)

    def resolve_event(self, query: str) -> str | None:
        q = normalize(query)
        if q in self.events:
            return self.events[q]
        best = max(self.events, key=lambda e: jaro_winkler(q, e), default=None)
        return self.events[best] if best and jaro_winkler(q, best) >= self.jw_threshold else None


if __name__ == "__main__":
    import sys
    lex = sys.argv[2] if len(sys.argv) > 2 else "data/lexicon.json"
    r = EntityResolver.from_file(lex)
    for q, a in [("Hooly AI", "ceo"), ("hooly ai pro", "price"), ("Gemini", "languages"),
                 ("Hooley Gemni", None), ("Pixel Buds", None), ("coffee machine", None)]:
        print(q, "->", r.resolve(q, a))
