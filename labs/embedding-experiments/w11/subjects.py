"""w11: page-context subject resolver for VERIDYCT practice sentences.
Rules + a TF-IDF attribute classifier. The resolver itself has no trained parameters: it scores each candidate subject s by
    score(s) = max_{a in attributes(s)} P(a | text) * prior(s)        prior = recency over rows of the same page
and picks the (s, a) pair with the best score. P(a | text) comes from an unrestricted attribute classifier (see measure.py).

    X = Ctx(rows, lex)                      # label-free structures: matcher hits per row, pages, subject x attribute matrix
    out = resolve(X, i, P_i, cfg, prior)    # -> dict(set, s, a, how); P_i: probabilities over X.CLASSES
Self-test: /tmp/veridyct-bench/.venv/bin/python -I subjects.py
"""
import re
import sys
from collections import Counter, defaultdict

import numpy as np

# ------------------------------------------------------------------ S0: lexicon matcher (longest first, case-insensitive)
def make_matcher(lex):
    """find(text) -> [(start, end, canonical subject)] for every name/alias hit, longest alternative first, no overlaps."""
    names = dict(lex['alias_to_name'])  # lower-cased name or alias -> canonical name (a name beats another subject's alias)
    keys = sorted(names, key=len, reverse=True)
    rx = re.compile(r"(?<![\w])(?:" + '|'.join(re.escape(k).replace(r'\ ', r'\s+') for k in keys) + r")(?![\w])(?!\.\d)", re.I)

    def find(text):
        t = text.replace('’', "'")
        return [(m.start(), m.end(), names[re.sub(r'\s+', ' ', m.group(0).lower())]) for m in rx.finditer(t)]
    return find


PERSON_ATTRS = {'joined', 'previous_employer', 'team_size', 'chairs', 'chairs_audit_committee', 'independent_director',
                'desks_managed', 'facilities_team', 'offices_run'}
HE = re.compile(r"\b(?:he|she|his|her|hers|him|himself|herself)\b", re.I)
IT = re.compile(r"\b(?:it|its|itself)\b|\bthe (?:platform|phone|handset|device|browser|service|product|app|assistant|tool|suite|watch|earbuds|model)\b", re.I)


class Ctx:
    """Everything that needs no labels: lexicon matrices, matcher hits per row, page layout, person/thing typing."""

    def __init__(self, rows, lex):
        self.rows, self.lex = rows, lex
        self.SUBJ = list(lex['subjects']); self.SI = {s: i for i, s in enumerate(self.SUBJ)}
        self.CLASSES = sorted({a for d in lex['subjects'].values() for a in d['attributes']})
        self.CI = {a: i for i, a in enumerate(self.CLASSES)}
        self.A = np.zeros((len(self.SUBJ), len(self.CLASSES)), bool)
        for s, d in lex['subjects'].items():
            for a in d['attributes']:
                self.A[self.SI[s], self.CI[a]] = True
        self.find = make_matcher(lex)
        self.ents = [self.find(r['text']) for r in rows]
        self.found = [list(dict.fromkeys(e[2] for e in ents)) for ents in self.ents]  # distinct, in text order
        self.page, self.pos = defaultdict(list), {}
        for r in rows:  # rows are sorted by id, so every page list ascends
            self.pos[r['idx']] = len(self.page[r['page']])
            self.page[r['page']].append(r['idx'])
        self.person = {s for s, d in lex['subjects'].items() if PERSON_ATTRS & set(d['attributes'])}
        self.gold = [frozenset(f['subject'] for f in r['facts']) for r in rows]

    def cues(self, i):
        t = self.rows[i]['text']
        return bool(HE.search(t)), bool(IT.search(t))

    def type_filter(self, i, cs):
        """S4: he/she/his/her -> person subjects only; it/its/the platform/the phone -> non-person; both or neither: no filter."""
        he, it = self.cues(i)
        if he == it:
            return cs
        return [s for s in cs if (s in self.person) == he] or cs


# ------------------------------------------------------------------ S1-S4: the resolver
def prior_map(X, i, cfg):
    """{subject: recency prior}. In-row mentions 1.0; an earlier mention d rows back lam**d; ctx='page' also lets later rows
    count (mu * lam**d). Unnamed row: only the context. Named row: the row's own mentions, plus context when cfg['competes']."""
    found, L, k, lam = X.found[i], X.page[X.rows[i]['page']], X.pos[i], cfg.get('lam', 0.8)
    pr = {}

    def upd(s, p):
        if p > pr.get(s, 0):
            pr[s] = p
    for rank, s in enumerate(found):
        upd(s, 1.0 - 1e-6 * rank)  # text order breaks exact ties
    ctx = cfg.get('ctx')
    if ctx and (not found or cfg.get('competes')):
        for d, j in enumerate(range(k - 1, -1, -1), 1):
            if ctx == 'nearest_row':  # w7 page_carry: every subject of the nearest earlier row that names one
                if X.found[L[j]]:
                    for s in X.found[L[j]]:
                        upd(s, lam)
                    break
                continue
            for s in X.found[L[j]]:
                upd(s, lam ** d)
        if ctx == 'page':
            for d, j in enumerate(range(k + 1, len(L)), 1):
                for s in X.found[L[j]]:
                    upd(s, cfg.get('mu', 1.0) * lam ** d)
    if cfg.get('amb') is not None:  # the company itself is always a weak candidate ("our CTO", "we")
        upd('Hooly', lam ** cfg['amb'])
    return pr


def resolve(X, i, P, cfg, prior, Pm=None, valid=None):
    """Joint (subject, attribute) pick for row i. cfg keys: ctx (None | 'carry' | 'page' | 'nearest_row'), competes, lam, mu, amb, rho (extra in-row
    subjects kept when their score >= rho * best), pron (S4 typing), fallback (S3). prior: training-fold counters.
    -> dict(set=frozenset|None, s, a, how, score)."""
    pr = prior_map(X, i, cfg)
    cs = list(pr)
    if cs and cfg.get('pron'):
        cs = X.type_filter(i, cs)
    if cs:
        W = X.A[[X.SI[s] for s in cs]] * P[None, :]
        comp = W.max(1)
        sc = comp * np.array([pr[s] for s in cs])
        b = int(sc.argmax())
        s, a = cs[b], X.CLASSES[int(W[b].argmax())]
        S = {s}
        if X.found[i] and cfg.get('rho') is not None and comp[b] > 0:  # a second subject named in the row with a fitting attribute
            S |= {c for c, v in zip(cs, comp) if c in X.found[i] and v >= cfg['rho'] * comp[b]}
        return dict(set=frozenset(S), s=s, a=a, how='named' if X.found[i] else 'context', score=float(sc[b]))
    if not cfg.get('fallback'):
        return dict(set=None, s=None, a=None, how='none', score=0.0)
    if cfg.get('fallback') == 'collective' and Pm is not None:  # X4: the subject that best explains every row of the page
        s, a = collective(X, i, P, Pm, valid)
        return dict(set=frozenset({s}), s=s, a=a, how='collective', score=0.0)
    cnt = Counter(s for j in X.page[X.rows[i]['page']] for s in X.found[j])  # S3: the page's most frequent subject, all rows
    if cnt:
        top = max(cnt.values())
        tied = [s for s in cnt if cnt[s] == top]
        W = X.A[[X.SI[s] for s in tied]] * P[None, :]
        b = int(W.max(1).argmax())
        s, a, how = tied[b], X.CLASSES[int(W[b].argmax())], 'page_dominant'
    else:  # nothing on the page: the training subject most often paired with the (unrestricted) predicted attribute
        c = int(P.argmax())
        cn = prior['attr_subj'].get(c)
        s, a, how = (cn.most_common(1)[0][0] if cn else prior['top_subject']), X.CLASSES[c], 'attr_prior'
        if s in X.SI and not X.A[X.SI[s], c]:
            a = X.CLASSES[int((X.A[X.SI[s]] * P).argmax())]
    return dict(set=frozenset({s}), s=s, a=a, how=how, score=0.0)


def collective(X, i, P, Pm, valid, eps=0.02, bonus=2.0):
    """Page-level subject posterior from all rows of the page (the whole page is available at run time; P is out of fold, and a
    page never straddles folds): col(s) = sum_rows log(eps + max_{a in attrs(s)} P_row(a)) + bonus * [s named somewhere on the page]."""
    L = X.page[X.rows[i]['page']]
    rs = [j for j in L if valid[j]] or [i]
    men = np.zeros(len(X.SUBJ))
    for j in L:
        for t in X.found[j]:
            men[X.SI[t]] = 1.0
    col = np.log(eps + np.stack([(X.A * Pm[j][None, :]).max(1) for j in rs])).sum(0) + bonus * men
    b = int(col.argmax())
    return X.SUBJ[b], X.CLASSES[int((X.A[b] * P).argmax())]


def _selftest():
    import json
    sys.path.insert(0, '/tmp/veridyct-emb/common')
    import harness as H
    rows, lex = H.load()
    X = Ctx(rows, lex)
    f = X.find
    assert [e[2] for e in f("Hooly Cloud's reliability team answers to Holdan.")] == ['Hooly Cloud', 'Holdan']
    assert [e[2] for e in f('Hooly Gemini 2.1 ships today')] == ['Hooly Gemini']
    assert [e[2] for e in f('Gemini kept 97.9% uptime')] == ['Hooly Gemini']
    assert f('The platform already serves over 100 customers') == []
    assert X.person == {'Bertram Gilfoil', 'Dinesh Chugtay', 'Erlich Bachmann', 'Holdan', 'Hoovar', 'Patreese', 'Peter Gregori', 'Ron LaFlame'}
    # toy page: row 3 names nothing, the classifier says 'customers' -> Hooly Cloud (recent) beats Holdan (no such attribute)
    i3 = next(r['idx'] for r in rows if r['id'] == 'p-7')
    P = np.zeros(len(X.CLASSES)); P[X.CI['customers']] = 0.9
    out = resolve(X, i3, P, dict(ctx='carry'), dict(attr_subj={}, top_subject='Hooly'))
    assert out['s'] == 'Hooly Cloud' and out['a'] == 'customers', out
    # pronoun typing: 'He begins with a small crew of 4 engineers' (p-4) must pick a person
    i4 = next(r['idx'] for r in rows if r['id'] == 'p-4')
    P = np.zeros(len(X.CLASSES)); P[X.CI['team_size']] = 0.8; P[X.CI['regions']] = 0.85
    out = resolve(X, i4, P, dict(ctx='carry', pron=True), dict(attr_subj={}, top_subject='Hooly'))
    assert out['s'] == 'Holdan', out
    print('subjects.py self-test OK')


if __name__ == '__main__':
    _selftest()
