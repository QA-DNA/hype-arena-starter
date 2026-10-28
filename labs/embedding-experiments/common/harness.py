"""Shared evaluation harness for the VERIDYCT embedding experiments: import it, never copy it.
    import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
Only stdlib + numpy + scipy + scikit-learn (no torch). Self-test: python -I harness.py (about 5 s).
Folds, probes and retrieval use POSITIONS in the row list you pass (X rows follow that list); anchors/pairs report
`idx` (position in load()'s full list). Probes, kNN and retrieval L2-normalise X. Attribute tasks use the GOLD
subject and restrict predictions to its lexicon attributes. run_* return (metrics, per_row_output); NaN = empty bucket."""
import csv, json, math, os, random, time, warnings
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_union
from sklearn.svm import LinearSVC

HERE = Path(__file__).resolve().parent
RESULTS_DIR = '/tmp/veridyct-emb/results'
LABELS = ['true', 'false', 'unsure']  # column order of every 3-class probability matrix
TASKS = {'attr_probe', 'attr_knn', 'attr_zeroshot', 'attr_hybrid', 'attr_unseen', 'key_retrieval', 'truth_false',
         'truth_three', 'nli_anchor', 'nli_conflict', 'nli_attr', 'speed'}
TASK_PREFIXES = ('finetune_', 'fusion_', 'values_')
NAN = float('nan')

def set_threads(n=2):
    """Cap CPU threads. Call BEFORE importing torch, then torch.set_num_threads(n) yourself. Returns n."""
    for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'RAYON_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
        os.environ[k] = str(n)
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ.setdefault('HF_HOME', '/tmp/veridyct-bench/hf')
    try:  # env vars bind libraries loaded later; this also caps the OpenMP pool numpy/sklearn already loaded
        from threadpoolctl import threadpool_limits
        global _LIMITS
        _LIMITS = threadpool_limits(limits=n)
    except ImportError:
        pass
    return n

# ---------------------------------------------------------------- data
def pages(rows):
    """Assign r['page'] in place (exp.py rule): sort by N of id p-N; new page when the date changes or N != prev+1.
    Returns the page count (291 on practice.csv)."""
    page, prev = -1, None
    for r in sorted(rows, key=lambda r: r['n']):
        if prev is None or r['date'] != prev['date'] or r['n'] != prev['n'] + 1:
            page += 1
        r['page'], prev = page, r
    return page + 1

def load():
    """-> (rows, lex). rows: dicts {idx,id,n,text,date,label,facts,page} sorted by n. lex: {subjects: {name:
    {aliases, attributes}}, alias_to_name: {lowercased alias or name: name}, events}."""
    with open(HERE / 'practice.csv', newline='', encoding='utf-8') as f:
        raw = sorted(csv.DictReader(f), key=lambda r: int(r['id'].rsplit('-', 1)[1]))
    rows = [dict(idx=i, id=r['id'], n=int(r['id'].rsplit('-', 1)[1]), text=r['text'], date=r['date'],
                 label=r['label'], facts=json.loads(r['form']), page=-1) for i, r in enumerate(raw)]
    pages(rows)
    L = json.load(open(HERE / 'lexicon.json', encoding='utf-8'))
    lex = dict(subjects={s['name']: dict(aliases=s['aliases'], attributes=s['attributes']) for s in L['subjects']},
               alias_to_name={}, events=L['events'])
    for s in L['subjects']:  # names are written last so a name beats another subject's alias
        lex['alias_to_name'].update({a.lower(): s['name'] for a in s['aliases']})
    lex['alias_to_name'].update({s['name'].lower(): s['name'] for s in L['subjects']})
    return rows, lex

def single_fact_rows(rows): return [r for r in rows if len(r['facts']) == 1]
def key(fact): return (fact['subject'], fact['attribute'])
def attr_words(attribute): return attribute.replace('_', ' ')
def describe(subject, attribute): return f'{subject} {attr_words(attribute)}'
def _attrs(rows_sf): return np.array([r['facts'][0]['attribute'] for r in rows_sf], dtype=object)

def _norm(v):  # numbers -> float so 4 == 4.0; bool stays bool so True != 1 (json.dumps below tells them apart)
    if isinstance(v, dict): return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list): return [_norm(x) for x in v]
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v

def value_equal(v1, v2):
    """Exact equality of two fact `value` dicts; the only normalisation is numeric type (4 == 4.0)."""
    return json.dumps(_norm(v1), sort_keys=True) == json.dumps(_norm(v2), sort_keys=True)

def candidates(lex, subject):
    """The subject's lexicon attribute list (an alias is resolved; unknown subject -> [])."""
    s = lex['subjects'].get(subject) or lex['subjects'].get(lex['alias_to_name'].get(subject.lower()))
    return list(s['attributes']) if s else []

def _l2(X):
    X = np.asarray(X, dtype=np.float64)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)

# ---------------------------------------------------------------- folds
def page_folds(rows, n_splits=5):
    """[(train_idx, test_idx)] positions in `rows`: sklearn GroupKFold on `page`, deterministic. Build the folds from
    the SAME list you embed (all rows, or single_fact_rows(rows)); the two lists give different splits."""
    return list(GroupKFold(n_splits).split(np.zeros(len(rows)), groups=[r['page'] for r in rows]))

def attribute_folds(rows, n_splits=5):
    """Leave-attribute-out GroupKFold on the FIRST fact's attribute: test attributes are unseen at training time
    (train_counts all 0). Meant for SINGLE-FACT rows: pass single_fact_rows(rows)."""
    return list(GroupKFold(n_splits).split(np.zeros(len(rows)), groups=[r['facts'][0]['attribute'] for r in rows]))

def train_counts(rows_sf, folds):
    """Per row: number of training rows (in its fold) with the same attribute as the row's own."""
    y, out = _attrs(rows_sf), np.zeros(len(rows_sf), int)
    for tr, te in folds:
        c = Counter(y[tr])
        out[te] = [c[a] for a in y[te]]
    return out

# ---------------------------------------------------------------- anchors and pairs (idx = row['idx'])
def anchors(rows):
    """{idx: [ {idx, key, days, same_value} ]} for EVERY row (maybe empty): TRUE rows on OTHER pages sharing >=1 key;
    days = other.date - row.date (signed); same_value = gold values equal. Sorted by |days|, days, idx."""
    ordinal = {r['idx']: date.fromisoformat(r['date']).toordinal() for r in rows}
    kv, by_key = {}, defaultdict(list)
    for r in rows:
        d = kv[r['idx']] = defaultdict(list)
        for f in r['facts']:
            d[key(f)].append(f['value'])
        for kk in d:
            by_key[kk].append(r)
    out = {}
    for r in rows:
        A = [dict(idx=o['idx'], key=kk, days=ordinal[o['idx']] - ordinal[r['idx']],
                  same_value=any(value_equal(a, b) for a in vals for b in kv[o['idx']][kk]))
             for kk, vals in kv[r['idx']].items() for o in by_key[kk] if o['label'] == 'true' and o['page'] != r['page']]
        out[r['idx']] = sorted(A, key=lambda a: (abs(a['days']), a['days'], a['idx']))
    return out

def nearest_anchors(rows, k=2):
    """{idx: anchors}: PER KEY the k nearest at-or-before (days <= 0, same day counts as before) and k nearest after,
    merged across keys, deduplicated by idx, sorted by |days|."""
    out = {}
    for i, A in anchors(rows).items():
        sel = {}
        for kk in sorted({a['key'] for a in A}):
            Ak = [a for a in A if a['key'] == kk]
            for a in [a for a in Ak if a['days'] <= 0][:k] + [a for a in Ak if a['days'] > 0][:k]:
                sel.setdefault(a['idx'], a)
        out[i] = sorted(sel.values(), key=lambda a: (abs(a['days']), a['days'], a['idx']))
    return out

def same_key_pairs(rows, max_per_key=50, seed=0):
    """[(i, j, same_value)], i < j (idx): single-fact rows labelled true/false, DIFFERENT pages, same key; at most
    max_per_key pairs per key (seeded random sample). Get labels from rows[i]['label']."""
    rng, groups, out = random.Random(seed), defaultdict(list), []
    for r in rows:
        if len(r['facts']) == 1 and r['label'] in ('true', 'false'):
            groups[key(r['facts'][0])].append(r)
    for kk in sorted(groups):
        g = groups[kk]
        P = [(a, b) for n_, a in enumerate(g) for b in g[n_ + 1:] if a['page'] != b['page']]
        if len(P) > max_per_key:
            P = sorted(rng.sample(P, max_per_key), key=lambda p: (p[0]['idx'], p[1]['idx']))
        out += [(a['idx'], b['idx'], value_equal(a['facts'][0]['value'], b['facts'][0]['value'])) for a, b in P]
    return out

# ---------------------------------------------------------------- metrics
def _ece(conf, hit, bins=10):
    conf, hit = np.asarray(conf, float), np.asarray(hit, float)
    b = np.minimum((conf * bins).astype(int), bins - 1)
    return float(sum(abs(hit[b == k].mean() - conf[b == k].mean()) * (b == k).sum() for k in range(bins) if (b == k).any()) / len(conf)) if len(conf) else NAN

def ece(y01, p, bins=10):
    """Expected calibration error of P(y=1) = p (equal-width bins)."""
    return _ece(p, y01, bins)

def attr_metrics(y_true, y_pred, train_counts):
    """Accuracy and n overall and by the number of training examples of the true attribute in the fold:
    ge5 (>=5), 1to4, unseen (0). NaN accuracy for an empty bucket."""
    ok, tc = np.array([a == b for a, b in zip(y_true, y_pred)], float), np.asarray(train_counts)
    B = {'all': np.ones(len(tc), bool), 'ge5': tc >= 5, '1to4': (tc >= 1) & (tc <= 4), 'unseen': tc == 0}
    return {**{f'acc_{k}': float(ok[m].mean()) if m.any() else NAN for k, m in B.items()},
            **{f'n_{k}': int(m.sum()) for k, m in B.items()}}

def binary_metrics(y01, scores):
    """auc, ap, f1_max at threshold thr (+ precision/recall there); brier, acc_at_05, ece need scores in [0,1] else
    NaN; n, pos. auc/ap/f1 are NaN when one class is absent."""
    y, s = np.asarray(y01, int), np.asarray(scores, float)
    out = dict(auc=NAN, ap=NAN, f1_max=NAN, thr=NAN, precision=NAN, recall=NAN, brier=NAN, acc_at_05=NAN, ece=NAN,
               n=len(y), pos=int(y.sum()))
    if 0 < y.sum() < len(y):
        p, r, t = precision_recall_curve(y, s)
        f = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
        b = int(f.argmax())
        out.update(auc=float(roc_auc_score(y, s)), ap=float(average_precision_score(y, s)), f1_max=float(f[b]),
                   thr=float(t[b]), precision=float(p[b]), recall=float(r[b]))
    if len(s) and s.min() >= 0 and s.max() <= 1:
        out.update(brier=float(np.mean((s - y) ** 2)), acc_at_05=float(np.mean((s >= 0.5) == y)), ece=ece(y, s))
    return out

def three_class_metrics(y_true, proba):
    """y_true 'true'/'false'/'unsure'; proba (n,3) in LABELS order. ece: 10 bins on max prob, rows not predicted unsure.
    arena = (right - wrong)/n: answer argmax{p_true,p_false} if its max >= t else abstain (0); unsure-truth rows score 0.
    t in 0.50..0.95 step 0.05 -> arena_at_05, arena_best (+arena_best_t), arena_always_true = (n_true - n_false)/n."""
    P, yi = np.asarray(proba, float), np.array([LABELS.index(y) for y in y_true])
    n, pred = len(yi), P.argmax(1)
    tp_f, keep = int(((pred == 1) & (yi == 1)).sum()), pred != 2
    conf, guess, scored = P[:, :2].max(1), P[:, :2].argmax(1), yi != 2
    arena = {t: float((((conf >= t) & scored) * np.where(guess == yi, 1, -1)).sum() / n)
             for t in [round(0.5 + 0.05 * i, 2) for i in range(10)]}
    bt = max(arena, key=arena.get)
    return dict(acc=float((pred == yi).mean()), n=n,
                macro_f1=float(f1_score(yi, pred, labels=[0, 1, 2], average='macro', zero_division=0)),
                false_recall=tp_f / max(int((yi == 1).sum()), 1), false_precision=tp_f / max(int((pred == 1).sum()), 1),
                unsure_recall=int(((pred == 2) & (yi == 2)).sum()) / max(int((yi == 2).sum()), 1),
                ece=_ece(P.max(1)[keep], (pred == yi)[keep]), brier=float(((P - np.eye(3)[yi]) ** 2).sum(1).mean()),
                arena_at_05=arena[0.5], arena_best=arena[bt], arena_best_t=bt,
                arena_always_true=float(((yi == 0).sum() - (yi == 1).sum()) / n))

# ---------------------------------------------------------------- attribute prediction
def _restricted_argmax(S, classes, rows_sf, lex):
    """Per row, argmax of S over the gold subject's lexicon attributes (unrestricted if none is among `classes`)."""
    classes, cache, M = np.asarray(classes, dtype=object), {}, np.zeros(S.shape, bool)
    for i, r in enumerate(rows_sf):
        s = r['facts'][0]['subject']
        if s not in cache:
            cache[s] = np.isin(classes, candidates(lex, s))
        M[i] = cache[s]
    M[~M.any(1)] = True
    return classes[np.where(M, S, -np.inf).argmax(1)]

def _prep(X, rows_sf, folds):
    assert sorted(np.concatenate([te for _, te in folds]).tolist()) == list(range(len(rows_sf))), 'folds must tile rows once'
    return _l2(X), _attrs(rows_sf), np.empty(len(rows_sf), dtype=object)

def run_probe_attr(X, rows_sf, lex, folds, C=10.0):
    """Out-of-fold LogisticRegression(C, max_iter=3000) over attribute strings, gold-subject restriction. X (n_sf, d);
    folds = page_folds(rows_sf) or attribute_folds(rows_sf). Returns (attr_metrics, pred list[str]). A probe cannot
    predict an attribute absent from its training fold, so acc_unseen is 0 by construction."""
    X, y, pred = _prep(X, rows_sf, folds)
    for tr, te in folds:
        m = LogisticRegression(C=C, max_iter=3000).fit(X[tr], y[tr])
        pred[te] = _restricted_argmax(m.decision_function(X[te]), m.classes_, [rows_sf[i] for i in te], lex)
    return attr_metrics(y, pred, train_counts(rows_sf, folds)), list(pred)

def run_knn_attr(X, rows_sf, lex, folds, k=5):
    """Cosine kNN (k, weight 1/cosine-distance). The restriction narrows the NEIGHBOUR POOL: only training rows with
    an attribute of the gold subject vote (empty pool -> unrestricted). Returns (attr_metrics, pred)."""
    X, y, pred = _prep(X, rows_sf, folds)
    for tr, te in folds:
        cls, yt = np.unique(y[tr], return_inverse=True)
        ok = np.stack([np.isin(cls, candidates(lex, rows_sf[i]['facts'][0]['subject'])) for i in te])[:, yt]
        ok[~ok.any(1)] = True
        S = np.where(ok, X[te] @ X[tr].T, -np.inf)
        nb = np.argsort(-S, axis=1, kind='stable')[:, :k]
        sim, V = np.take_along_axis(S, nb, 1), np.zeros((len(te), len(cls)))
        np.add.at(V, (np.arange(len(te))[:, None], yt[nb]), np.where(np.isfinite(sim), 1 / np.maximum(1 - sim, 1e-6), 0.0))
        pred[te] = cls[V.argmax(1)]
    return attr_metrics(y, pred, train_counts(rows_sf, folds)), list(pred)

def zeroshot_attr(sim_matrix_fn, rows_sf, lex, desc_fn=describe):
    """No training. sim_matrix_fn(descriptions: list[str]) -> cosine sims (len(rows_sf), len(descriptions)) for desc_fn
    (subject, attribute) of every lexicon pair (514, lexicon order); restricted argmax over the gold subject's pairs.
    train_counts are ALL ZERO by definition, so acc_unseen == acc_all. Returns (attr_metrics, pred)."""
    pairs = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]
    S = np.asarray(sim_matrix_fn([desc_fn(s, a) for s, a in pairs]), float)
    assert S.shape == (len(rows_sf), len(pairs)), f'sim matrix {S.shape}, expected {(len(rows_sf), len(pairs))}'
    ps, pa, pred = np.array([s for s, _ in pairs]), np.array([a for _, a in pairs], dtype=object), []
    for i, r in enumerate(rows_sf):
        m = ps == r['facts'][0]['subject']
        pred.append(pa[int((np.where(m, S[i], -np.inf) if m.any() else S[i]).argmax())])
    return attr_metrics(_attrs(rows_sf), pred, np.zeros(len(pred), int)), pred

# ---------------------------------------------------------------- truth probes
def _oof_lr(X, y, folds, classes, C):
    P = np.zeros((len(y), len(classes)))
    for tr, te in folds:
        m = LogisticRegression(class_weight='balanced', C=C, max_iter=3000).fit(X[tr], y[tr])
        P[np.ix_(te, [classes.index(c) for c in m.classes_])] = m.predict_proba(X[te])
    return P

def run_probe_false(X, rows, folds, C=1.0):
    """Out-of-fold LR(class_weight='balanced') false-vs-rest (true+unsure). X (len(rows), d); folds = page_folds(rows).
    Returns (binary_metrics, scores). Balanced weights shift probabilities, so brier/ece are of the raw outputs."""
    y = np.array([r['label'] == 'false' for r in rows], int)
    s = _oof_lr(_l2(X), y, folds, [0, 1], C)[:, 1]
    return binary_metrics(y, s), s

def run_probe_three(X, rows, folds, C=1.0):
    """Out-of-fold multinomial LR(class_weight='balanced'). Raw softmax: NO calibration (no isotonic) on purpose.
    Returns (three_class_metrics, proba (n,3) in LABELS order)."""
    y = [r['label'] for r in rows]
    P = _oof_lr(_l2(X), np.array(y), folds, LABELS, C)
    return three_class_metrics(y, P), P

# ---------------------------------------------------------------- key retrieval
def key_retrieval(X, rows, k=10):
    """Queries = rows sharing a key with a row on another page; candidates = all rows on other pages, ranked by cosine;
    relevant = those sharing a key. recall_at_k = |relevant in top k| / |relevant| (caps below 1 when more than k are
    relevant), hit_at_k = any relevant in top k, mrr over the full ranking; tfidf_* = char(3,5) reference. X (len(rows), d)."""
    P, by_key = np.array([r['page'] for r in rows]), defaultdict(set)
    for i, r in enumerate(rows):
        for f in r['facts']:
            by_key[key(f)].add(i)
    rel = np.zeros((len(rows),) * 2, bool)
    for ids in by_key.values():
        rel[np.ix_(sorted(ids), sorted(ids))] = True
    rel &= P[:, None] != P[None, :]
    q = np.flatnonzero(rel.any(1))

    def score(S, pre=''):
        S, rec, hit, rr = np.where(P[:, None] == P[None, :], -np.inf, S), [], [], []
        for i in q:
            r_ = rel[i][np.argsort(-S[i], kind='stable')]
            rec.append(r_[:k].sum() / r_.sum()); hit.append(r_[:k].any()); rr.append(1 / (1 + r_.argmax()))
        return {pre + 'recall_at_k': float(np.mean(rec)), pre + 'hit_at_k': float(np.mean(hit)), pre + 'mrr': float(np.mean(rr))}

    Xn = _l2(X)
    T = TfidfVectorizer(analyzer='char', ngram_range=(3, 5)).fit_transform([r['text'] for r in rows])
    return dict(**score(Xn @ Xn.T), **score((T @ T.T).toarray(), 'tfidf_'), n_queries=len(q), k=k)

# ---------------------------------------------------------------- TF-IDF sanity baseline
def _tfidf(train_texts, test_texts):
    u = make_union(TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5)), TfidfVectorizer(ngram_range=(1, 2)))
    return u.fit_transform(train_texts), u.transform(test_texts)

def tfidf_baseline(rows, lex=None):
    """Sanity reference -> {'attr': attr_metrics, 'false': binary_metrics}. attr: char_wb(2,5)+word(1,2) TF-IDF + LinearSVC
    (C=3), single-fact rows, page_folds, gold-subject restriction (~0.87 acc_all, ~0.96 acc_ge5, 0 unseen). false: same
    TF-IDF + LR(balanced, C=3), false-vs-rest on all rows (AUC ~0.63)."""
    lex = lex or load()[1]
    sf = single_fact_rows(rows)
    y, pred, folds = _attrs(sf), np.empty(len(sf), dtype=object), page_folds(sf)
    for tr, te in folds:
        Xtr, Xte = _tfidf([sf[i]['text'] for i in tr], [sf[i]['text'] for i in te])
        m = LinearSVC(C=3).fit(Xtr, y[tr])
        pred[te] = _restricted_argmax(m.decision_function(Xte), m.classes_, [sf[i] for i in te], lex)
    yf, s = np.array([r['label'] == 'false' for r in rows], int), np.zeros(len(rows))
    for tr, te in page_folds(rows):
        Xtr, Xte = _tfidf([rows[i]['text'] for i in tr], [rows[i]['text'] for i in te])
        s[te] = LogisticRegression(class_weight='balanced', C=3, max_iter=3000).fit(Xtr, yf[tr]).predict_proba(Xte)[:, 1]
    return dict(attr=attr_metrics(y, pred, train_counts(sf, folds)), false=binary_metrics(yf, s))

# ---------------------------------------------------------------- results and speed
def results_path(worker): return f'{RESULTS_DIR}/{worker}.jsonl'

def _jsonable(o):
    if isinstance(o, dict): return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)): return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray): return _jsonable(o.tolist())
    if isinstance(o, np.generic): o = o.item()
    return None if isinstance(o, float) and not math.isfinite(o) else o

class ResultWriter:
    """One JSON line per .add(): {ts, worker, model, task, variant, n, notes, metrics, **extra}; NaN/inf -> null, numpy ->
    python; a non-standard task name only warns (a result is never dropped); one O_APPEND write per line."""

    def __init__(self, path):
        self.path = str(path)
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)

    def add(self, worker, model, task, variant, metrics, n=None, notes='', **extra):
        if task not in TASKS and not task.startswith(TASK_PREFIXES):
            warnings.warn(f'non-standard task name {task!r}; use one of {sorted(TASKS)} or {TASK_PREFIXES}*')
        rec = dict(ts=datetime.now(timezone.utc).isoformat(timespec='seconds'), worker=worker, model=model, task=task,
                   variant=variant, n=n, notes=notes, metrics=metrics)
        assert not set(extra) & set(rec), f'extra keys clash with core fields: {set(extra) & set(rec)}'
        rec.update(extra)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(_jsonable(rec), ensure_ascii=False, default=str) + '\n').encode())
        finally:
            os.close(fd)
        return rec

def encode_speed(encode_fn, texts, bs=32):
    """encode_fn(list[str]) per batch of bs, longest texts first; one warm-up batch, then one timed full pass.
    est_sec_20k_x86 = 20000 / sentences_per_s * 2.0 (midpoint of the 1.5x-3x x86-vs-Mac slowdown factor)."""
    ts = sorted(texts, key=len, reverse=True)
    batches = [ts[i:i + bs] for i in range(0, len(ts), bs)]
    encode_fn(batches[0])
    t0 = time.perf_counter()
    for b in batches:
        encode_fn(b)
    wall = time.perf_counter() - t0
    return dict(sentences_per_s=len(ts) / wall, est_sec_20k_x86=20000 / (len(ts) / wall) * 2.0, n=len(ts), bs=bs, wall_s=wall)

# ---------------------------------------------------------------- self-test
if __name__ == '__main__':
    t0 = time.time()
    set_threads(2)
    rows, lex = load()
    sf = single_fact_rows(rows)
    sizes = lambda F: [(len(a), len(b)) for a, b in F]
    pc = sorted(Counter(r['page'] for r in rows).values())
    print(f'rows={len(rows)} pages={pages(rows)} single_fact={len(sf)} labels={dict(Counter(r["label"] for r in rows))} '
          f'page size min/median/max={pc[0]}/{pc[len(pc) // 2]}/{pc[-1]} subjects={len(lex["subjects"])} '
          f'pairs={sum(len(s["attributes"]) for s in lex["subjects"].values())} events={len(lex["events"])}')
    for name, F in (('page_folds(all)', page_folds(rows)), ('page_folds(sf)', page_folds(sf)), ('attribute_folds(sf)', attribute_folds(sf))):
        print(f'{name:20s} (train,test) sizes: {sizes(F)}')
    A, pr = anchors(rows), same_key_pairs(rows)
    print(f'anchors: rows with >=1 anchor={sum(1 for v in A.values() if v)}/{len(rows)}, median anchors/covered row='
          f'{int(np.median([len(v) for v in A.values() if v]))}, same_value share={np.mean([a["same_value"] for v in A.values() for a in v]):.3f}, '
          f'nearest_anchors(k=2) max len={max(map(len, nearest_anchors(rows, 2).values()))}')
    print(f'same_key_pairs: {len(pr)} pairs, same_value={sum(p[2] for p in pr)}, different={sum(not p[2] for p in pr)}')
    assert len(rows) == 1897 and pages(rows) == 291 and len(sf) == 1467 and all(not set(a) & set(b) for a, b in page_folds(rows))
    assert value_equal({'v': 4}, {'v': 4.0}) and not value_equal({'v': True}, {'v': 1}) and not value_equal({'v': 4}, {'v': 5})
    assert same_key_pairs(rows) == pr and describe('Holdan', 'team_size') == 'Holdan team size'
    assert abs(three_class_metrics(['true', 'false', 'unsure'], np.eye(3))['arena_best'] - 2 / 3) < 1e-9  # +1 +1 +0 over 3 rows
    t1 = time.time()
    B = tfidf_baseline(rows, lex)
    a, f = B['attr'], B['false']
    print(f'tfidf attr (single-fact, page folds, restricted): acc_all={a["acc_all"]:.3f} acc_ge5={a["acc_ge5"]:.3f} '
          f'acc_1to4={a["acc_1to4"]:.3f} acc_unseen={a["acc_unseen"]:.3f} n={a["n_all"]}/{a["n_ge5"]}/{a["n_1to4"]}/{a["n_unseen"]}')
    print(f'tfidf false-vs-rest (all rows): auc={f["auc"]:.3f} ap={f["ap"]:.3f} f1_max={f["f1_max"]:.3f} n={f["n"]} pos={f["pos"]}')
    ok = abs(a['acc_all'] - .872) < .02 and abs(a['acc_ge5'] - .966) < .02 and a['acc_unseen'] == 0 and abs(f['auc'] - .63) < .02
    print(f'sanity vs expected (0.872 / 0.966 / 0 / 0.63, tolerance 0.02): {"OK" if ok else "MISMATCH"}')
    print(f'self-test done: tfidf_baseline {time.time() - t1:.1f}s, total {time.time() - t0:.1f}s')
