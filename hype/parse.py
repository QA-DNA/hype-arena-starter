"""Text -> facts parser: rules for values/subjects, TF-IDF + logistic regression for the attribute.

    from hype import parse
    model = parse.train(rows_with_gold_facts, lexicon)            # rows: dicts with id,text,date,facts
    facts = parse.parse(text, date, context_rows, lexicon, model)  # context_rows: rows BEFORE this one, in order
    allf  = parse.parse_all(rows, lexicon, model)                 # {id: facts}; neighbours handled for you
"""
import json
import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.linear_model import LogisticRegression

from . import values

TOK = re.compile(r"[A-Za-z]+|\d[\d.,]*|[%€$£\"]")
STOPN = {"The", "A", "An", "We", "Our", "It", "Its", "He", "She", "His", "Her", "They", "This", "That", "In", "On", "At", "For", "And", "But",
         "So", "If", "When", "As", "By", "From", "To", "Of", "With", "Yes", "No", "Not", "There", "Here", "Now", "Today", "Every", "Each"}
W_EXPL_PREV, W_EXPL_OTHER, CTX_DECAY, W_AFTER = 1.0, 0.85, 0.6, 0.3
THETA, GAMMA = 0.25, 1.0
CTX_W, W_FACT = 0.9, 1.0  # weight of a context subject; weight of a subject carried over from the previous rows' own facts
CTX_ROWS = 10
NONE_SCALE = 1.0
CHAIN = True
ACC_THETA = 0.4  # emit a hypothesis when the acceptance model says P(correct) >= this
USE_ACCEPT = True
LAST_HYPS = {}  # id -> per-candidate hypotheses of the last parse_all call


class Lex:
    def __init__(self, lexicon):
        self._cache = {}
        self.attrs = {s["name"]: s["attributes"] for s in lexicon["subjects"]}
        for e in lexicon.get("events", []):
            self.attrs.setdefault(e, [])
        names = {}
        for s in lexicon["subjects"]:
            for n in [s["name"]] + s["aliases"]:
                names[n] = s["name"]
            parts = s["name"].split()
            if len(parts) == 2 and not s["name"].startswith("Hooly") and not any(ch.isdigit() for ch in s["name"]):
                names.setdefault(parts[0], s["name"])  # first-name alias for people
        self.names = names
        self.ci = {n for n in names if " " in n}
        alts = sorted(names, key=len, reverse=True)
        self.rx_cs = re.compile(r"(?<![\w])(?:" + "|".join(map(re.escape, [n for n in alts if n not in self.ci])) + r")(?![\w])")
        self.rx_ci = re.compile(r"(?<![\w])(?:" + "|".join(map(re.escape, [n for n in alts if n in self.ci])) + r")(?![\w])", re.I)
        self.low = {n.lower(): s for n, s in names.items() if n in self.ci}

    def mentions(self, text):
        r = self._cache.get(text)
        if r is None:
            r = self._cache[text] = self._mentions(text)
        return r

    def _mentions(self, text):
        found = []
        for m in self.rx_ci.finditer(text):
            found.append((m.start(), m.end(), self.low[m.group(0).lower()]))
        for m in self.rx_cs.finditer(text):
            found.append((m.start(), m.end(), self.names[m.group(0)]))
        found.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
        kept = []
        for f in found:
            if not any(f[0] < k[1] and k[0] < f[1] for k in kept):
                kept.append(f)
        kept.sort()
        return kept


def _canon(v):
    d = {k: x for k, x in v.items() if k != "op"}
    if isinstance(d["value"], float):
        d["value"] = round(d["value"], 9)
    return json.dumps(d, sort_keys=True)


def name_cands(text, mentions, common):
    out = []
    for m in re.finditer(r"[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*", text):
        toks = [(t.group(0), m.start() + t.start()) for t in re.finditer(r"\S+", m.group(0))]
        toks = [(re.sub(r"['’]s?$", "", t), p) for t, p in toks]
        toks = [(t, p) for t, p in toks if t]
        while toks and (toks[0][0] in STOPN or toks[0][0].lower() in common or toks[0][0].isupper() and len(toks[0][0]) > 1):
            toks = toks[1:]
        while toks and toks[-1][0].isupper() and len(toks[-1][0]) > 1:
            toks = toks[:-1]
        if not toks:
            continue
        s, e = toks[0][1], toks[-1][1] + len(toks[-1][0])
        if text[e:e + 1] == ":" and s < 3:
            continue
        if any(s < b and a < e and not (a <= s and e <= b) for a, b, _ in mentions):
            continue
        if any(a <= s and e <= b and (b - a) > (e - s) for a, b, _ in mentions):
            continue
        out.append({"v": {"kind": "name", "value": text[s:e]}, "s": s, "e": e})
    return out


def feat_string(text, cand, mentions):
    s, e = cand["s"], cand["e"]
    v = cand["v"]
    toks = []
    for m in TOK.finditer(text):
        t = m.group(0)
        if m.start() < e and s < m.end():
            if not toks or toks[-1] != "<V>":
                toks.append("<V>")
            continue
        if any(m.start() < b and a < m.end() for a, b, _ in mentions):
            if not toks or toks[-1] != "<S>":
                toks.append("<S>")
            continue
        toks.append("<N>" if t[0].isdigit() else t.lower())
    i = toks.index("<V>") if "<V>" in toks else 0
    f = [f"KIND_{v['kind']}"]
    for k in ("unit", "per", "op", "currency"):
        if k in v:
            f.append(f"{k.upper()}_{v[k]}")
    if v["kind"] == "name":
        f.append("NAME_" + v["value"].lower().replace(" ", "_"))
        f += ["NAMETOK_" + t.lower() for t in v["value"].split()]
    if v["kind"] == "version":
        f.append("VER_" + "x".join(str(len(p)) for p in v["value"].split(".")))
    if v["kind"] == "boolean":
        f.append("NEG" if not v["value"] else "POS")
    for j, t in enumerate(reversed(toks[max(0, i - 6):i])):
        f.append(f"L_{t}")
        if j < 3:
            f.append(f"L{j+1}_{t}")
        if j == 0 and i >= 2:
            f.append(f"L2_{toks[i-2]}_{toks[i-1]}")
    for j, t in enumerate(toks[i + 1:i + 8]):
        f.append(f"R_{t}")
        if j < 3:
            f.append(f"R{j+1}_{t}")
        if j == 0 and i + 2 < len(toks):
            f.append(f"R2_{toks[i+1]}_{toks[i+2]}")
    for t in toks:
        f.append(f"S_{t}")
    if i == 0:
        f.append("FIRST")
    if i == len(toks) - 1:
        f.append("LAST")
    for a, b, subj in mentions[:3]:
        f.append("SUBJ_" + subj.replace(" ", "_"))
    return " ".join(f)


class Model:
    pass


def _row_cands(text, lex, mentions, model):
    masks = [(a, b) for a, b, _ in mentions]
    cs = values.extract(text, masks=masks, known_units=model.units)
    cs += name_cands(text, mentions, model.common)
    cs.append({"v": {"kind": "boolean", "value": not values.has_negation(text)}, "s": 0, "e": len(text)})
    return cs


def train(rows, lexicon, accept=True):
    lex = Lex(lexicon)
    m = Model()
    m.units = {f["value"]["unit"] for r in rows for f in r["facts"] if f["value"]["kind"] == "quantity"}
    m.attr_kinds = defaultdict(set)
    m.attr_units = defaultdict(Counter)
    for r in rows:
        for f in r["facts"]:
            m.attr_kinds[f["attribute"]].add(f["value"]["kind"])
            if "unit" in f["value"]:
                m.attr_units[f["attribute"]][f["value"]["unit"]] += 1
    low = Counter()
    for r in rows:
        for w in re.findall(r"(?<![A-Za-z'’])[a-z]{2,}(?![A-Za-z])", r["text"]):
            low[w] += 1
    m.common = {w for w, c in low.items() if c >= 1}
    X, y = [], []
    for r in rows:
        ments = lex.mentions(r["text"])
        gold = defaultdict(list)
        for f in r["facts"]:
            gold[_canon(f["value"])].append(f["attribute"])
        gb = [f["attribute"] for f in r["facts"] if f["value"]["kind"] == "boolean"]
        for c in _row_cands(r["text"], lex, ments, m):
            if c["v"]["kind"] == "boolean":
                lab = gb[0] if gb else "NONE"
            else:
                a = gold.get(_canon(c["v"]))
                lab = a[0] if a else "NONE"
            X.append(feat_string(r["text"], c, ments))
            y.append(lab)
    m.cv = CountVectorizer(analyzer=str.split, binary=True, min_df=1)
    m.tf = TfidfTransformer(sublinear_tf=True)
    Z = m.tf.fit_transform(m.cv.fit_transform(X))
    m.clf = LogisticRegression(C=30, max_iter=500)
    m.clf.fit(Z, y)
    m.classes = {c: i for i, c in enumerate(m.clf.classes_)}
    m.accept = train_accept(rows, lexicon) if accept and USE_ACCEPT else None
    return m


def _proba(model, feats):
    return model.clf.predict_proba(model.tf.transform(model.cv.transform(feats)))


def _context(rows_before, rows_after, lex, date):
    """[(subject, weight)] from neighbours of the same date, nearest first."""
    out, seen = [], set()
    rank = 0
    for r in reversed(rows_before[-CTX_ROWS:]):
        if r.get("date") != date:
            break
        for _, _, s in lex.mentions(r["text"]):
            if s not in seen:
                seen.add(s)
                out.append((s, CTX_DECAY ** rank))
                rank += 1
    for k, r in enumerate(rows_after[:3]):
        if r.get("date") != date:
            break
        for _, _, s in lex.mentions(r["text"]):
            if s not in seen:
                seen.add(s)
                out.append((s, W_AFTER * CTX_DECAY ** k))
    return out


def _chain(ctx, hist, date):
    """Add the subjects of the previous rows' own (predicted) facts: a pronoun row usually continues the previous row's subject."""
    best = dict(ctx)
    seen, rank = set(), 0
    for d, subs in reversed(hist[-CTX_ROWS:]):
        if d != date:
            break
        for s in subs:
            if s not in seen:
                seen.add(s)
                best[s] = max(best.get(s, 0.0), W_FACT * CTX_DECAY ** rank)
                rank += 1
    return list(best.items())


def _accepted(hy, text, model):
    cand = [h for h in hy if h["top"]]
    if not cand:
        return []
    pr = model.accept.predict_proba(np.array([hyp_features(h, len(text)) for h in cand]))[:, 1]
    best = {}
    for h, p in zip(cand, pr):
        h["pa"] = float(p)
        if p >= ACC_THETA:
            k = (h["top"][0], h["top"][1])
            if k not in best or best[k][0] < p:
                f = {"subject": h["top"][0], "attribute": h["top"][1], "value": h["value"], "_p": float(p), "_s": h["top"][2]}
                if h["alt"]:
                    f["_alt"] = [h["alt"][0], h["alt"][1], h["alt"][2]]
                best[k] = (p, f)
    for h in hy:
        h["emitted"] = bool(h.get("pa", 0) >= ACC_THETA and h["top"])
    return [f for _, f in best.values()]


def _decide(cands, probs, mentions, ctx, lex, model, theta=None):
    """Returns (facts, hyps). Each emitted fact also carries _p (attribute posterior), _s (score) and _alt (runner-up hypothesis);
    hyps has one entry per candidate value, emitted or not, so a judge can use soft hypotheses."""
    theta = THETA if theta is None else theta
    facts, best, hyps = [], {}, []
    for c, p in zip(cands, probs):
        v = c["v"]
        opts = {}
        prev = None
        for a, b, s in mentions:
            if b <= c["s"]:
                prev = s
        for a, b, s in mentions:
            w = W_EXPL_PREV if (s == prev or (prev is None and len(mentions) == 1)) else W_EXPL_OTHER
            opts[s] = max(opts.get(s, 0), w)
        for s, w in ctx:
            opts.setdefault(s, w * CTX_W)
        scored = []
        pn = NONE_SCALE * p[model.classes["NONE"]] if "NONE" in model.classes else 0.0
        for s, w in opts.items():
            al = []
            for a in lex.attrs.get(s, ()):
                i = model.classes.get(a)
                if i is None or v["kind"] not in model.attr_kinds[a]:
                    continue
                q = p[i]
                if v["kind"] == "quantity" and model.attr_units[a] and v["unit"] not in model.attr_units[a]:
                    q *= 0.15
                al.append((q, a))
            if not al:
                continue
            den = pn + sum(q for q, _ in al) + 1e-9
            for q, a in al:
                scored.append((q / den * w ** GAMMA, s, a, q / den))
        scored.sort(reverse=True)
        top = scored[0] if scored else None
        alt = next((x for x in scored[1:] if (x[1], x[2]) != (top[1], top[2])), None) if top else None
        emitted = bool(top and top[0] >= theta)
        hyps.append({"value": v, "emitted": emitted, "kind": v["kind"], "pn": float(pn), "nopt": len(opts), "nm": len(mentions),
                     "src": int(bool(top) and top[1] in {m[2] for m in mentions}), "nc": len(cands),
                     "top": [top[1], top[2], float(top[0]), float(top[3])] if top else None,
                     "alt": [alt[1], alt[2], float(alt[0]), float(alt[3])] if alt else None})
        if emitted:
            key = (top[1], top[2])
            if key not in best or best[key][0] < top[0]:
                f = {"subject": top[1], "attribute": top[2], "value": v, "_p": float(top[3]), "_s": float(top[0])}
                if alt:
                    f["_alt"] = [alt[1], alt[2], float(alt[0])]
                best[key] = (top[0], f)
    return [f for _, f in best.values()], hyps


KINDS = ["quantity", "money", "duration", "name", "percent", "boolean", "date", "version"]


def hyp_features(h, text_len):
    t, a = h["top"], h["alt"]
    f = [t[2], t[3], a[2] if a else 0.0, a[3] if a else 0.0, t[2] - (a[2] if a else 0.0), h["pn"], h["nopt"], h["src"], h["nm"], h["nc"], text_len]
    return f + [int(h["kind"] == k) for k in KINDS]


def _is_correct(h, gold):
    """top hypothesis equals a gold fact (subject, attribute, value)."""
    t = h["top"]
    for g in gold:
        if g["subject"] == t[0] and g["attribute"] == t[1] and _canon(g["value"]) == _canon(h["value"]):
            return True
    return False


def train_accept(rows, lexicon, inner=4):
    """Acceptance model: P(top hypothesis is a correct fact), fitted on hypotheses of rows parsed by models that never saw them
    (inner date-grouped folds), so it learns the parser's real error profile."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    dates = sorted({r["date"] for r in rows})
    fold = {d: i % inner for i, d in enumerate(dates)}
    X, y = [], []
    for k in range(inner):
        tr = [r for r in rows if fold[r["date"]] != k]
        te = {r["id"] for r in rows if fold[r["date"]] == k}
        m = train(tr, lexicon, accept=False)
        parse_all(rows, lexicon, m, only=te)
        for r in rows:
            if r["id"] in te:
                for h in LAST_HYPS.get(r["id"], []):
                    if h["top"]:
                        X.append(hyp_features(h, len(r["text"]))); y.append(_is_correct(h, r["facts"]))
    clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=120, min_samples_leaf=20, l2_regularization=1.0, random_state=0)
    return clf.fit(np.array(X), np.array(y))


def parse(row_text, row_date, context_rows, lexicon, model, after_rows=(), lex=None):
    lex = lex or Lex(lexicon)
    ments = lex.mentions(row_text)
    cands = _row_cands(row_text, lex, ments, model)
    probs = _proba(model, [feat_string(row_text, c, ments) for c in cands])
    ctx = _context(list(context_rows), list(after_rows), lex, row_date)
    return _decide(cands, probs, ments, ctx, lex, model)[0]


def parse_all(rows, lexicon, model, only=None):
    """rows in file order (all of them: neighbours give context). Returns {id: facts} (for ids in `only` if given)."""
    lex = Lex(lexicon)
    prep = []
    allfeat = []
    for r in rows:
        ments = lex.mentions(r["text"])
        if only is not None and r["id"] not in only:
            prep.append((ments, [], len(allfeat)))
            continue
        cands = _row_cands(r["text"], lex, ments, model)
        prep.append((ments, cands, len(allfeat)))
        allfeat += [feat_string(r["text"], c, ments) for c in cands]
    P = _proba(model, allfeat) if allfeat else np.zeros((0, 1))
    out, hist = {}, []
    LAST_HYPS.clear()
    for i, r in enumerate(rows):
        ments, cands, o = prep[i]
        if only is not None and r["id"] not in only:
            hist.append((r["date"], []))
            continue
        ctx = _context(rows[max(0, i - CTX_ROWS):i], rows[i + 1:i + 4], lex, r["date"])
        if CHAIN:
            ctx = _chain(ctx, hist, r["date"])
        facts, hy = _decide(cands, P[o:o + len(cands)], ments, ctx, lex, model)
        if model.accept is not None:
            facts = _accepted(hy, r["text"], model)
        out[r["id"]] = facts
        LAST_HYPS[r["id"]] = hy
        hist.append((r["date"], [f["subject"] for f in facts]))
    return out
