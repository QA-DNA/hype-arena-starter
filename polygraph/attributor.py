"""Stage 3: decide which (subject, attribute) each value in a sentence is about.

This is the first model we TRAIN on practice.csv: its `form` column says, for every
sentence, which facts it states. We turn every (value read in the sentence) x (candidate
subject, attribute) pair into a feature vector, label it 1 when the gold form holds that
fact, and fit a gradient-boosted classifier. At run time each value goes to its
best-scoring (subject, attribute), if the score clears a threshold.

Features (all generalize to attributes the practice data never shows, through the
attribute's own name):
  kind/unit fit   P(value kind | attribute), unit seen with the attribute, unit word in the attribute name
  context cues    naive-Bayes log-odds of the words around the value for this attribute,
                  and overlap of those words with the attribute's name
  subject fit     distance from the subject's mention, nearest subject, inherited from the page
  priors          how often the attribute is stated at all

Booleans and names are not read by the reader; they are proposed here: a yes/no for every
attribute whose cue words appear (its polarity from negation), a name for every known name
or capitalised phrase.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from collections import Counter, defaultdict

import numpy as np

from .lexicon import Lexicon
from .linker import Linker, Mention
from .model import Fact, Row, ValueSpan, value_key
from .reader import NEGATION_RE, NEG_EXEMPT_RE, STOP, parse_values, singular

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")
NAME_RE = re.compile(r"(?<![A-Za-z])(?:[A-Z][\w&'’.-]*)(?:\s+(?:of\s+|de\s+|the\s+)?[A-Z][\w&'’.-]*)*")
KINDS = ["quantity", "money", "percent", "date", "version", "duration", "name", "boolean"]
WINDOW = 8
THRESHOLD = 0.15  # tuned by 5-fold CV on practice (precision 0.89, recall 0.81)


@lru_cache(maxsize=50_000)  # the same sentence is split for every candidate
def _words(text: str) -> tuple:
    return tuple(singular(w) for w in WORD_RE.findall(text) if w.lower() not in STOP and len(w) > 1)


def words(text: str) -> list[str]:
    return list(_words(text))


@lru_cache(maxsize=20_000)
def attr_tokens(attribute: str) -> frozenset:
    return frozenset(singular(t) for t in attribute.split("_") if t and t not in STOP)


def unit_of(v: dict) -> str:
    k = v.get("kind")
    if k == "quantity":
        return "q:" + str(v.get("unit", "")).lower()
    if k == "money":
        return f"m:{v.get('currency')}:{v.get('per')}"
    if k == "duration":
        return "d:" + ("mo" if v.get("unit") in ("month", "year") else "s")
    if k == "date":
        return f"t:{len(str(v.get('value')))}"
    return k


GLOBAL_K = 4  # lexicon-wide candidates per value, for sentences whose subject the page never names


class Attributor:
    def __init__(self, lexicon: Lexicon, threshold: float = THRESHOLD):
        self.lexicon = lexicon
        self.model = None
        self.threshold = threshold
        self.company = lexicon.canonical("Hooly")  # "we", "our": the company itself
        # attribute-name word -> (subject, attribute): finds attributes practice never showed
        self.token_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for s in lexicon.subjects:
            for a in lexicon.attributes(s):
                for t in attr_tokens(a):
                    self.token_index[t].append((s, a))
        self.unit_index: dict[str, set] = defaultdict(set)  # unit_of(value) -> (subject, attribute)
        self.attr_kind: dict[str, Counter] = defaultdict(Counter)  # attribute -> kind counts
        self.attr_unit: dict[str, Counter] = defaultdict(Counter)
        self.attr_words: dict[str, Counter] = defaultdict(Counter)  # cue words around the value
        self.all_words: Counter = Counter()
        self.attr_count: Counter = Counter()
        self.name_values: dict[str, Counter] = defaultdict(Counter)  # attribute -> names seen
        self.gazetteer: set[str] = set()
        self.bool_cues: dict[str, Counter] = defaultdict(Counter)  # boolean attribute -> words

    # ---- candidates ------------------------------------------------------------------
    def _readings(self, row: Row, values: list[ValueSpan], mentions: list[Mention]) -> list[tuple[dict, int, int, bool]]:
        """(value, start, end, is_alt) for everything the sentence may state."""
        out = []
        for v in values:
            if v.negated:
                continue
            out.append((v.value, v.start, v.end, False))
            for a in v.alts:
                out.append((a, v.start, v.end, True))
        # names: known names + mentions of other subjects + capitalised phrases
        seen = set()
        for m in mentions:
            if m.start >= 0:
                out.append(({"kind": "name", "value": m.subject}, m.start, m.end, False))
                seen.add(m.subject.lower())
        for m in NAME_RE.finditer(row.text):
            name = m.group(0).rstrip(".")
            if name.lower() in seen or len(name) < 3:
                continue
            if name in self.gazetteer or (" " in name and m.start() > 0):
                if not NEGATION_RE.search(NEG_EXEMPT_RE.sub(" ", row.text[: m.start()])):
                    out.append(({"kind": "name", "value": name}, m.start(), m.start() + len(name), name not in self.gazetteer))
                    seen.add(name.lower())
        # yes/no: one reading per polarity of the sentence
        neg = bool(NEGATION_RE.search(NEG_EXEMPT_RE.sub(" ", row.text)))
        out.append(({"kind": "boolean", "value": not neg}, 0, len(row.text), False))
        return out

    def _subjects(self, mentions: list[Mention]) -> list[Mention]:
        out, seen = [], set()
        for m in mentions:
            if m.subject not in seen:
                seen.add(m.subject)
                out.append(m)
        return out

    def _features(self, row: Row, reading, subj: Mention, attribute: str, mentions: list[Mention],
                  win_words: list[str]) -> list[float]:
        v, start, end, is_alt = reading
        kind = v["kind"]
        kc = self.attr_kind.get(attribute)
        total = sum(kc.values()) if kc else 0
        p_kind = (kc[kind] + 0.1) / (total + 0.8) if kc else 0.125
        uc = self.attr_unit.get(attribute)
        u = unit_of(v)
        unit_seen = (uc[u] / max(1, sum(uc.values()))) if uc else 0.0
        toks = attr_tokens(attribute)
        unit_word = singular(str(v.get("unit", ""))) if kind == "quantity" else ""
        unit_in_name = float(bool(unit_word) and unit_word in toks)
        cue = self._cue(attribute, win_words)
        name_overlap = len(toks & set(win_words)) / max(1, len(toks))
        text_overlap = len(toks & set(words(row.text))) / max(1, len(toks))
        # subject position: in the sentence, or elsewhere on the page
        if subj.start < 0:
            dist, inherited = 1.0, 1.0
        else:
            dist = min(abs(subj.start - start), abs(subj.end - start)) / max(1, len(row.text))
            inherited = 0.0
        page = [min(subj.row_gap, 20), min(subj.page_count, 20), float(subj.page_first), float(subj.earlier)]
        located = [m for m in mentions if m.start >= 0]
        nearest = 0.0
        if located and subj.start >= 0:
            best = min(located, key=lambda m: abs(m.start - start))
            nearest = float(best.subject == subj.subject)
        before = float(subj.start >= 0 and subj.start < start)
        # names: seen as this attribute's value before; the value is the subject itself
        nv = self.name_values.get(attribute)
        name_seen = float(kind == "name" and bool(nv) and v["value"] in nv)
        self_ref = float(kind == "name" and v["value"] == subj.subject)
        bc = self.bool_cues.get(attribute)
        bool_cue = 0.0
        if kind == "boolean" and bc:
            tw = set(words(row.text))
            bool_cue = sum(bc[w] for w in tw) / max(1, sum(bc.values()))
        return [p_kind, unit_seen, unit_in_name, cue, name_overlap, text_overlap, dist, inherited, nearest,
                before, math.log1p(self.attr_count[attribute]), float(kc is None), float(is_alt), name_seen,
                self_ref, bool_cue, float(kind == "boolean"), float(kind == "name"), float("op" in v),
                len(located), KINDS.index(kind), *page]

    def _cue(self, attribute: str, win_words: list[str]) -> float:
        """Naive-Bayes log-odds that these words surround a value of this attribute."""
        aw = self.attr_words.get(attribute)
        if not aw or not win_words:
            return 0.0
        na, vocab = self._totals.get(attribute) or self._total(attribute)
        nall = self._nall
        return sum(math.log((aw[w] + 0.5) / (na + 0.5 * vocab)) - math.log((self.all_words[w] + 0.5) / (nall + 0.5 * vocab))
                   for w in win_words) / len(win_words)

    def _total(self, attribute):
        t = (sum(self.attr_words[attribute].values()), len(self.all_words) + 1)
        self._totals[attribute] = t
        return t

    def _global(self, reading, win: list[str], on_page: set[str]) -> list[Mention]:
        """The few (subject, attribute) pairs anywhere in the lexicon that fit this value best."""
        v = reading[0]
        if v["kind"] in ("boolean", "name"):
            return []
        pool = set(self.unit_index.get(unit_of(v), ()))
        if v["kind"] == "quantity":
            pool.update(self.token_index.get(singular(str(v.get("unit", ""))), ()))
        for w in win:
            if w in self.token_index and len(self.token_index[w]) <= 12:
                pool.update(self.token_index[w])
        pool = sorted((s, a) for s, a in pool if s not in on_page)  # sorted: ties break the same in every run
        ranked = sorted(pool, key=lambda sa: -(self._cue(sa[1], win) + 0.5 * len(attr_tokens(sa[1]) & set(win))))
        return [(s, a) for s, a in ranked[:GLOBAL_K]]

    def _window(self, text: str, start: int, end: int, skip, whole: bool = False) -> list[str]:
        masked = list(text)
        for a, b in skip:
            for i in range(max(0, a), min(len(masked), b)):
                masked[i] = " "
        masked = "".join(masked)
        if whole:
            return [singular(w) for w in WORD_RE.findall(masked) if w.lower() not in STOP and len(w) > 1]
        left = WORD_RE.findall(masked[:start])[-WINDOW:]
        right = WORD_RE.findall(masked[end:])[:WINDOW]
        return [singular(w) for w in left + right if w.lower() not in STOP and len(w) > 1]

    def _candidates(self, row: Row, values: list[ValueSpan], mentions: list[Mention]):
        skip = [(m.start, m.end) for m in mentions if m.start >= 0]
        subjects = self._subjects(mentions)
        if self.company and all(m.subject != self.company for m in subjects):
            subjects.append(Mention(self.company, -1, -1, "", 50, 0, False, False))
        on_page = {m.subject for m in subjects}
        cands, feats = [], []
        squashed = re.sub(r"[^a-z0-9]", "", row.text.lower())
        for reading in self._readings(row, values, mentions):
            if reading[0]["kind"] == "boolean":  # a yes/no is the whole sentence: every word is context
                win = self._window(row.text, 0, 0, skip, whole=True)
            else:
                win = self._window(row.text, reading[1], reading[2], skip)
            pairs = [(s, a) for s in subjects for a in self.lexicon.attributes(s.subject)]
            pairs += [(Mention(s, -1, -1, "", 99, 0, False, False), a) for s, a in self._global(reading, win, on_page)]
            for s, a in pairs:
                if reading[0]["kind"] == "name" and reading[0]["value"] == s.subject:
                    continue
                cands.append((reading, s.subject, a))
                # the attribute's own words in the sentence: "SOC 2 certified" for soc2_certified
                phrase = a.replace("_", "")
                feats.append(self._features(row, reading, s, a, mentions, win) + [float(len(phrase) > 3 and phrase in squashed)])
        return cands, feats

    # ---- training --------------------------------------------------------------------
    def fit(self, rows: list[Row], forms: dict[str, list[dict]], mentions: dict[str, list[Mention]]) -> "Attributor":
        from sklearn.ensemble import HistGradientBoostingClassifier

        values = {}
        for r in rows:
            skip = [(m.start, m.end) for m in mentions[r.id] if m.start >= 0]
            values[r.id] = parse_values(r.text, skip)
        # statistics
        for r in rows:
            skip = [(m.start, m.end) for m in mentions[r.id] if m.start >= 0]
            for f in forms.get(r.id, []):
                a, v = f["attribute"], f["value"]
                self.attr_kind[a][v["kind"]] += 1
                self.attr_unit[a][unit_of(v)] += 1
                self.attr_count[a] += 1
                if v["kind"] == "name":
                    self.name_values[a][v["value"]] += 1
                    self.gazetteer.add(v["value"])
                if v["kind"] == "boolean":
                    self.bool_cues[a].update(set(words(r.text)))
                span = self._find_span(r, values[r.id], v)
                win = self._window(r.text, *span, skip) if span else words(r.text)
                self.attr_words[a].update(win)
                self.all_words.update(win)
                self.unit_index[unit_of(v)].add((f["subject"], a))
        self._totals, self._nall = {}, sum(self.all_words.values())
        # pairs
        X, y = [], []
        for r in rows:
            gold = {(f["subject"], f["attribute"], value_key(f["value"])) for f in forms.get(r.id, [])}
            cands, feats = self._candidates(r, values[r.id], mentions[r.id])
            for (reading, s, a), x in zip(cands, feats):
                X.append(x)
                y.append(int((s, a, value_key(reading[0])) in gold))
        self.model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
                                                    l2_regularization=1.0, random_state=0)
        self.model.fit(np.asarray(X, dtype=float), np.asarray(y))
        return self

    @staticmethod
    def _find_span(r: Row, values: list[ValueSpan], v: dict):
        k = value_key(v)
        for vs in values:
            if value_key(vs.value) == k or any(value_key(a) == k for a in vs.alts):
                return vs.start, vs.end
        if v["kind"] == "name":
            i = r.text.lower().find(str(v["value"]).lower())
            if i >= 0:
                return i, i + len(v["value"])
        return None

    # ---- predicting ------------------------------------------------------------------
    def assign(self, row: Row, values: list[ValueSpan], mentions: list[Mention]) -> list[Fact]:
        return self.assign_many([(row, values, mentions)])[0]

    def assign_many(self, items) -> list[list[Fact]]:
        all_c, all_x, owner = [], [], []
        for i, (row, values, mentions) in enumerate(items):
            c, x = self._candidates(row, values, mentions)
            all_c += c
            all_x += x
            owner += [i] * len(c)
        out: list[list[Fact]] = [[] for _ in items]
        if not all_x or self.model is None:
            return out
        p = self.model.predict_proba(np.asarray(all_x, dtype=float))[:, 1]
        return self._decide(all_c, p, owner, len(items), self.threshold)

    @staticmethod
    def _decide(cands, p, owner, n_items, threshold) -> list[list[Fact]]:
        """Each value span goes to its single best (subject, attribute), if that clears the
        threshold; a (subject, attribute) takes at most one value per sentence. Yes/no
        readings are judged per attribute. The score is the probability relative to the
        span's other candidates, as near-twin attributes split the raw probability."""
        out: list[list[Fact]] = [[] for _ in range(n_items)]
        spans: dict[tuple, list] = defaultdict(list)
        for (reading, s, a), prob, i in zip(cands, p, owner):
            # a yes/no reading spans the whole sentence: its attributes compete like a value's
            sk = (i, reading[1], reading[2]) if reading[0]["kind"] != "boolean" else (i, "bool")
            spans[sk].append((float(prob), reading, s, a))
        chosen: dict[tuple, tuple] = {}
        for sk, cs in spans.items():
            cs.sort(key=lambda c: -c[0])
            top = cs[0]
            share = top[0] / (sum(c[0] for c in cs[:4]) + 1e-9)
            score = top[0] ** 0.5 * share ** 0.5
            if score < threshold:
                continue
            k = (sk[0], top[2], top[3])
            if k not in chosen or score > chosen[k][0]:
                chosen[k] = (score, top[1], top[2], top[3])
        for (i, s, a), (score, reading, _, _) in chosen.items():
            out[i].append(Fact(s, a, reading[0], (reading[1], reading[2]), score))
        return out
