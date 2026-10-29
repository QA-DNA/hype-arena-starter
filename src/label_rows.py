#!/usr/bin/env python3
"""
Hooly row labeler  -  tree-based true / false / unsure classifier.

Pipeline (per row):
  1. Subject finder     : longest lexicon name/alias in the text, else the last
                          subject named earlier on the same page (same date).
  2. Fact router        : TF-IDF + logistic model predicts "subject||attribute"
                          (trained on the practice forms).
  3. Value extractor    : regex pulls numbers, dates, versions, negations, names.
  4. Knowledge base     : timeline of values per (subject, attribute) built from
                          labelled TRUE rows (+ values seen in FALSE rows = lies).
  5. Evidence features  : does the text hold the value valid on its date? an old
                          value? a future value? a known lie? what do the other
                          (unlabelled) rows about the same fact say?
  6. Judge              : Gradient-boosted decision trees -> label + probability.
                          confidence = max(p_true, p_false) rescaled to 0.5..1.

Usage
  python label_rows.py --practice practice.csv --lexicon lexicon.json \
                       --input universe.csv --output labels.csv
  python label_rows.py --practice practice.csv --lexicon lexicon.json --eval
"""
import argparse, json, re, sys, math, os
from collections import defaultdict, Counter
from datetime import date

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, KFold
from scipy.sparse import hstack

MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
NEG = re.compile(r"\b(not|no|never|without|n't|isn't|doesn't|don't|lacks?|missing|none|off|disabled|unavailable)\b|n't", re.I)
SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12}


# ----------------------------------------------------------------- helpers
def pdate(s):
    try:
        y, m, d = map(int, str(s)[:10].split("-")); return date(y, m, d)
    except Exception:
        return None


def norm_num(x):
    x = float(x)
    return str(int(x)) if abs(x - round(x)) < 1e-9 else f"{x:.6g}"


def text_tokens(text):
    """All value tokens a sentence holds."""
    t = text.replace("\u00a0", " ")
    toks = set()
    # dates: 12 January 2026 / January 12, 2026 / January 2026 / 2026-01-12
    for d, mo, y in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b", t):
        if mo.lower() in MONTHS: toks.add(f"date:{y}-{MONTHS[mo.lower()]:02d}-{int(d):02d}")
    for mo, d, y in re.findall(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", t):
        if mo.lower() in MONTHS: toks.add(f"date:{y}-{MONTHS[mo.lower()]:02d}-{int(d):02d}")
    for mo, y in re.findall(r"\b([A-Za-z]{3,9})\s+(\d{4})\b", t):
        if mo.lower() in MONTHS: toks.add(f"date:{y}-{MONTHS[mo.lower()]:02d}")
    for y, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        toks.add(f"date:{y}-{m}-{d}")
    for y in re.findall(r"\b(19\d\d|20\d\d)\b", t):
        toks.add(f"date:{y}")
    # versions
    for v in re.findall(r"\b[vV]?(\d+(?:\.\d+)+)\b", t):
        toks.add(f"ver:{v}")
    # numbers (with thousands separators, decimals, scale words)
    for num, sc in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|trillion|bn|mn|k|m|b)?\b", t, re.I):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        if sc: v *= SCALE[sc.lower()]
        toks.add(f"num:{norm_num(v)}")
        if sc and sc.lower() in ("m", "b"):  # 'm' may be metres/minutes
            toks.add(f"num:{norm_num(float(num.replace(',', '')))}")
    toks.add("bool:false" if NEG.search(t) else "bool:true")
    return toks


def value_token(v):
    k = v.get("kind")
    if k in ("quantity", "money", "percent", "duration"):
        return f"num:{norm_num(v['value'])}"
    if k == "date":  return f"date:{v['value']}"
    if k == "version": return f"ver:{v['value']}"
    if k == "boolean": return f"bool:{str(bool(v['value'])).lower()}"
    if k == "name": return f"name:{str(v['value']).lower()}"
    return f"{k}:{v.get('value')}"


def token_in_text(tok, text, ttoks):
    if tok.startswith("name:"):
        return tok[5:] in text.lower()
    if tok.startswith("ver:") and tok not in ttoks:
        return f"num:{tok[4:]}" in ttoks
    return tok in ttoks


# ----------------------------------------------------------------- lexicon
class Lexicon:
    def __init__(self, path):
        lx = json.load(open(path, encoding="utf-8"))
        self.subjects = {s["name"]: s for s in lx["subjects"]}
        self.alias = []
        for s in lx["subjects"]:
            for n in [s["name"]] + s.get("aliases", []):
                self.alias.append((n.lower(), s["name"]))
        self.alias.sort(key=lambda x: -len(x[0]))
        self.events = lx.get("events", [])

    def find(self, text):
        t = text.lower(); found = []
        taken = [False] * len(t)
        for a, name in self.alias:
            for m in re.finditer(r"(?<![\w])" + re.escape(a) + r"(?![\w])", t):
                if not any(taken[m.start():m.end()]):
                    for i in range(m.start(), m.end()): taken[i] = True
                    found.append((m.start(), name))
        return [n for _, n in sorted(found)]


def add_context(df, lex):
    """Subject tokens: explicit mentions + the page's running subject."""
    subj_cols, ctx = [], {}
    for text, d in zip(df.text, df.date):
        f = lex.find(str(text))
        prev = ctx.get(d)
        if f: ctx[d] = f[0]
        subj_cols.append((f, prev))
    df = df.copy()
    df["subj_found"] = [s for s, _ in subj_cols]
    df["subj_ctx"] = [p for _, p in subj_cols]
    df["router_text"] = [
        str(t) + " " + " ".join("SUBJ_" + re.sub(r"\W", "_", x) for x in s) +
        (" CTX_" + re.sub(r"\W", "_", p) if p else "")
        for t, (s, p) in zip(df.text, subj_cols)]
    return df


# ----------------------------------------------------------------- router
class Router:
    def fit(self, texts, targets):
        self.w = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        self.c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=3, sublinear_tf=True)
        X = hstack([self.w.fit_transform(texts), self.c.fit_transform(texts)]).tocsr()
        self.m = LinearSVC(C=1.0)
        self.m.fit(X, targets)
        return self

    def predict(self, texts):
        X = hstack([self.w.transform(texts), self.c.transform(texts)]).tocsr()
        S = self.m.decision_function(X) * 4.0
        S = np.exp(S - S.max(axis=1, keepdims=True)); P = S / S.sum(axis=1, keepdims=True)
        idx = np.argsort(-P, axis=1)[:, :2]
        return [(self.m.classes_[i[0]], P[r, i[0]], self.m.classes_[i[1]], P[r, i[1]]) for r, i in enumerate(idx)]


# ----------------------------------------------------------------- knowledge base
class KB:
    def __init__(self):
        self.true = defaultdict(list)   # (s,a) -> [(date, token)]
        self.lies = defaultdict(set)    # (s,a) -> tokens seen only in false rows
        self.kind = {}
        self.subj_tokens = defaultdict(set)
        self.attrs = defaultdict(set)

    def add(self, forms, label, d):
        d = pdate(d)
        for f in forms:
            key = (f["subject"], f["attribute"]); tok = value_token(f["value"])
            self.kind[key] = f["value"]["kind"]; self.attrs[f["subject"]].add(f["attribute"])
            if label == "true":
                self.true[key].append((d, tok)); self.subj_tokens[f["subject"]].add(tok)
            elif label == "false" and len(forms) == 1:
                self.lies[key].add(tok)

    def finish(self):
        for k in self.true: self.true[k].sort(key=lambda x: x[0] or date.min)
        for k in self.lies: self.lies[k] -= {t for _, t in self.true[k]}
        return self

    def at(self, key, d):
        """(current token, set of past tokens, set of future tokens, days since)"""
        tl = self.true.get(key, [])
        if not tl: return None, set(), set(), 9999
        past = [(x, t) for x, t in tl if x and d and x <= d]
        fut = {t for x, t in tl if x and d and x > d}
        if past:
            cur = past[-1][1]; days = (d - past[-1][0]).days
            return cur, {t for _, t in past[:-1]} - {cur}, fut - {cur}, days
        first = tl[0]
        return first[1], set(), fut - {first[1]}, -((first[0] - d).days if d and first[0] else 9999)


KINDS = ["quantity", "money", "percent", "duration", "date", "version", "boolean", "name"]


def featurize(df, routes, kb, votes):
    rows = []
    for (text, d), (sa, p1, sa2, p2), found, ctx in zip(zip(df.text, df.date), routes, df.subj_found, df.subj_ctx):
        text = str(text); dd = pdate(d); tt = text_tokens(text)
        s, a = sa.split("||"); key = (s, a)
        cur, past, fut, days = kb.at(key, dd)
        kind = kb.kind.get(key, "")
        n_vals = sum(1 for t in tt if t.startswith(("num:", "ver:")))
        n_dates = sum(1 for t in tt if t.startswith("date:"))
        known = kb.subj_tokens.get(s, set())
        unexplained = sum(1 for t in tt if t.startswith(("num:", "ver:")) and t not in known)
        v_agree, v_total = votes.get((key, cur), (0, 0)) if cur else (0, votes.get((key, None), (0, 0))[1])
        tl = kb.true.get(key, [])
        prv = [t for x, t in tl if x and dd and x <= dd]
        nxt = [t for x, t in tl if x and dd and x > dd]
        prev_tok = prv[-1] if prv else None; next_tok = nxt[0] if nxt else None
        pm = int(bool(prev_tok) and token_in_text(prev_tok, text, tt))
        nm = int(bool(next_tok) and token_in_text(next_tok, text, tt))
        kind_tok = {"date": "date:", "version": "ver:", "boolean": "bool:", "name": "name:"}.get(kind, "num:")
        has_kind = int(any(t.startswith(kind_tok) for t in tt)) if kind != "name" else 1
        any_hist = int(any(token_in_text(t, text, tt) for _, t in tl))
        # numeric distance to the value valid on the date (+ over/under claims)
        ref = prev_tok or next_tok
        rel, op_bad = -1.0, 0
        if ref and ref.startswith("num:"):
            rv = float(ref[4:]); nums = [float(t[4:]) for t in tt if t.startswith("num:")]
            if nums:
                best = min(nums, key=lambda v: abs(v - rv)); rel = min(abs(best - rv) / max(abs(rv), 1e-9), 10)
                if re.search(r"\b(over|more than|above|at least|exceeds?)\b", text, re.I) and best <= rv * 0 + max(nums) and rv <= max(nums): op_bad = 1
                if re.search(r"\b(under|less than|below|fewer than|at most)\b", text, re.I) and rv >= min(nums): op_bad = 1
        r = {
            "num_rel_diff": rel, "op_bad": op_bad,
            "prev_match": pm, "next_match": nm, "has_kind": has_kind, "any_hist": any_hist,
            "mismatch": int(bool(tl) and has_kind and not any_hist),
            "bool_conflict": int(kind == "boolean" and bool(prev_tok or next_tok) and not (pm or nm)),
            "p_route": p1, "p_route_gap": p1 - p2,
            "subj_explicit": int(s in found), "subj_ctx": int(s == ctx), "n_subj": len(found),
            "kb_has": int(cur is not None), "kb_n": len(kb.true.get(key, [])),
            "cur_match": int(bool(cur) and token_in_text(cur, text, tt)),
            "past_match": int(any(token_in_text(t, text, tt) for t in past)),
            "fut_match": int(any(token_in_text(t, text, tt) for t in fut)),
            "lie_match": int(any(token_in_text(t, text, tt) for t in kb.lies.get(key, ()))),
            "days_since": days if abs(days) < 9999 else 9999,
            "n_vals": n_vals, "n_dates": n_dates, "unexplained": unexplained,
            "neg": int(bool(NEG.search(text))),
            "hedge": int(bool(re.search(r"\b(about|around|roughly|nearly|almost|over|under|more than|less than|up to|at least|some|expected|plans?|will|soon|rumou?r|reportedly)\b", text, re.I))),
            "v_agree": v_agree, "v_total": v_total, "v_ratio": v_agree / v_total if v_total else -1,
            "len": len(text),
        }
        # subject-wide evidence: check every attribute of every candidate subject
        cands = set(found) | ({ctx} if ctx else set()) | {s}
        now_ok = stale = lie = 0
        for cs in cands:
            for ca in kb.attrs.get(cs, ()):
                c2, p2s, f2, _ = kb.at((cs, ca), dd)
                if c2 and not c2.startswith(("bool:", "name:")) and token_in_text(c2, text, tt): now_ok += 1
                if any(not t.startswith("bool:") and token_in_text(t, text, tt) for t in p2s | f2): stale += 1
                if any(not t.startswith("bool:") and token_in_text(t, text, tt) for t in kb.lies.get((cs, ca), ())): lie += 1
        r.update({"subj_now_ok": now_ok, "subj_stale": stale, "subj_lie": lie,
                  "vals_minus_ok": n_vals - now_ok})
        for k in KINDS: r["kind_" + k] = int(kind == k)
        rows.append(r)
    return pd.DataFrame(rows)


def build_votes(df_all, routes_all, kb):
    """Among ALL rows (incl. unlabelled) routed to the same fact, how many hold the KB value."""
    votes = Counter(); totals = Counter()
    for text, d, (sa, p, _, _) in zip(df_all.text, df_all.date, routes_all):
        if p < 0.3: continue
        key = tuple(sa.split("||")); totals[key] += 1
        cur, _, _, _ = kb.at(key, pdate(d)); text = str(text)
        if cur and token_in_text(cur, text, text_tokens(text)): votes[(key, cur)] += 1
    out = {}
    for (key, cur), n in votes.items(): out[(key, cur)] = (n, totals[key])
    for key, n in totals.items(): out[(key, None)] = (0, n)
    return out


def primary(forms):
    f = json.loads(forms)[0]; return f"{f['subject']}||{f['attribute']}"


def build_kb(df):
    kb = KB()
    for forms, lab, d in zip(df.form, df.label, df.date):
        kb.add(json.loads(forms), lab, d)
    return kb.finish()


def train_features(practice, n_folds=5, seed=0):
    """Out-of-fold features so the judge learns from honest evidence."""
    feats = [None] * len(practice); routes_oof = [None] * len(practice)
    kf = KFold(n_folds, shuffle=True, random_state=seed)
    for tr, te in kf.split(practice):
        P, T = practice.iloc[tr], practice.iloc[te]
        router = Router().fit(P.router_text.tolist(), [primary(f) for f in P.form])
        kb = build_kb(P)
        r_all = router.predict(practice.router_text.tolist())
        votes = build_votes(practice, r_all, kb)
        r_te = [r_all[i] for i in te]
        F = featurize(T, r_te, kb, votes)
        for j, i in enumerate(te): feats[i] = F.iloc[j]; routes_oof[i] = r_te[j]
    return pd.DataFrame(feats).reset_index(drop=True), routes_oof


def make_judge():
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=300,
                                          l2_regularization=1.0, random_state=0)


def to_output(ids, judge, F, tau=0.65):
    P = judge.predict_proba(F)
    cls = list(judge.classes_)
    out = []

    idx_t = cls.index("true") if "true" in cls else -1
    idx_f = cls.index("false") if "false" in cls else -1
    idx_u = cls.index("unsure") if "unsure" in cls else -1

    for (i, p), (_, row) in zip(zip(ids, P), F.iterrows()):
        pt = p[idx_t] if idx_t >= 0 else 0.0
        pf = p[idx_f] if idx_f >= 0 else 0.0
        pu = p[idx_u] if idx_u >= 0 else 0.0
        c = max(pt, pf) / max(pt + pf, 1e-9)

        # Output 'unsure' when:
        # 1. Direct argmax is unsure, OR
        # 2. pu > 0.20 (compensates for 2% prior in training data), OR
        # 3. Model confidence is ambiguous (c < tau), OR
        # 4. Text is speculative / rumour without matching KB state
        is_unsure = (
            (idx_u >= 0 and np.argmax(p) == idx_u) or
            (pu > 0.20) or
            (c < tau) or
            (bool(row.get("hedge", 0)) and not bool(row.get("cur_match", 0)))
        )

        if is_unsure:
            out.append((i, "unsure", ""))
        elif pt >= pf:
            out.append((i, "true", f"{min(1.0, max(0.5, c)):.3f}"))
        else:
            out.append((i, "false", f"{min(1.0, max(0.5, c)):.3f}"))

    return pd.DataFrame(out, columns=["id", "label", "confidence"])


def predict_labels(practice_rows, unlabelled_rows, lexicon_path):
    """
    Function interface for entrypoint.py.
    Predicts label ('true', 'false', 'unsure') and confidence (0.5..1.0)
    for unlabelled rows using the tree-based classifier.
    Returns: dict mapping row_id -> (label, confidence)
    """
    if not unlabelled_rows:
        return {}

    os.environ["LOKY_MAX_CPU_COUNT"] = "2"
    lex = Lexicon(lexicon_path)
    
    # Format practice dataframe
    p_data = []
    for r in practice_rows:
        f = r.get("form")
        form_str = json.dumps(f) if isinstance(f, (list, dict)) else str(f or "[]")
        p_data.append({
            "id": str(r.get("id", "")).strip(),
            "text": str(r.get("text", "")),
            "date": str(r.get("date", "")).strip(),
            "label": str(r.get("label", "")).strip().lower(),
            "form": form_str
        })
    practice_df = pd.DataFrame(p_data)
    practice = add_context(practice_df, lex)

    # Format unlabelled dataframe
    u_data = []
    for r in unlabelled_rows:
        u_data.append({
            "id": str(r.get("id", "")).strip(),
            "text": str(r.get("text", "")),
            "date": str(r.get("date", "")).strip(),
            "label": str(r.get("label", "")).strip().lower()
        })
    unlabelled_df = pd.DataFrame(u_data)
    uni = add_context(unlabelled_df, lex)

    print(f"      [label_rows] Training model on {len(practice):,} practice rows (out-of-fold)...")
    Ftr, _ = train_features(practice)
    judge = make_judge().fit(Ftr, practice.label)
    router = Router().fit(practice.router_text.tolist(), [primary(f) for f in practice.form])
    kb = build_kb(practice)

    print(f"      [label_rows] Predicting on {len(uni):,} unlabelled rows...")
    r_all = router.predict(uni.router_text.tolist())
    votes = build_votes(uni, r_all, kb)

    F_test = featurize(uni, r_all, kb, votes)
    res = to_output(uni.id, judge, F_test)

    preds = {}
    for _, row in res.iterrows():
        preds[row["id"]] = (row["label"], row["confidence"])
    print(f"      [label_rows] Finished labeling {len(preds):,} rows.")
    return preds


def label_unlabelled_dataframe(practice_df, unlabelled_df, lex):
    """
    Function interface for DataFrame inputs.
    """
    if unlabelled_df.empty:
        return {}

    os.environ["LOKY_MAX_CPU_COUNT"] = "2"
    practice = add_context(practice_df, lex)
    uni = add_context(unlabelled_df, lex)

    Ftr, _ = train_features(practice)
    judge = make_judge().fit(Ftr, practice.label)
    router = Router().fit(practice.router_text.tolist(), [primary(f) for f in practice.form])
    kb = build_kb(practice)

    r_all = router.predict(uni.router_text.tolist())
    votes = build_votes(uni, r_all, kb)

    F_test = featurize(uni, r_all, kb, votes)
    res = to_output(uni.id, judge, F_test)

    return {row["id"]: (row["label"], row["confidence"]) for _, row in res.iterrows()}


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--practice", required=True); ap.add_argument("--lexicon", required=True)
    ap.add_argument("--input"); ap.add_argument("--output", default="labels.csv")
    ap.add_argument("--eval", action="store_true", help="hold out every 5th practice row and score")
    a = ap.parse_args()
    lex = Lexicon(a.lexicon)
    practice = add_context(pd.read_csv(a.practice, dtype=str, keep_default_na=False), lex)

    if a.eval:
        hide = np.arange(len(practice)) % 5 == 4
        train, test = practice[~hide].reset_index(drop=True), practice[hide].reset_index(drop=True)
        Ftr, _ = train_features(train)
        judge = make_judge().fit(Ftr, train.label)
        router = Router().fit(train.router_text.tolist(), [primary(f) for f in train.form])
        kb = build_kb(train)
        r_all = router.predict(practice.router_text.tolist())
        votes = build_votes(practice, r_all, kb)
        r_te = router.predict(test.router_text.tolist())
        res = to_output(test.id, judge, featurize(test, r_te, kb, votes))
        acc = (res.label.values == test.label.values).mean()
        route_acc = np.mean([r[0] == primary(f) for r, f in zip(r_te, test.form)])
        print(f"router accuracy {route_acc:.3f}   label accuracy {acc:.3f}  (n={len(test)})")
        print(pd.crosstab(test.label.values, res.label.values, rownames=["gold"], colnames=["pred"]))
        return

    if not a.input: sys.exit("--input required (or use --eval)")
    uni = pd.read_csv(a.input, dtype=str, keep_default_na=False)
    uni = add_context(uni, lex)
    Ftr, _ = train_features(practice)
    judge = make_judge().fit(Ftr, practice.label)
    router = Router().fit(practice.router_text.tolist(), [primary(f) for f in practice.form])
    kb = build_kb(practice)
    r_all = router.predict(uni.router_text.tolist())
    votes = build_votes(uni, r_all, kb)
    mask = (uni.label.str.strip() == "").values
    todo = uni[mask].reset_index(drop=True)
    r_todo = [r for r, m in zip(r_all, mask) if m]
    res = to_output(todo.id, judge, featurize(todo, r_todo, kb, votes))
    tmp = a.output + ".tmp"
    res.to_csv(tmp, index=False); import os; os.replace(tmp, a.output)
    print(f"labelled {len(res)} rows -> {a.output}"); print(res.label.value_counts().to_string())


if __name__ == "__main__":
    main()
