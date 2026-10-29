"""Train worker C's extractor from allowed material only.
Data used (all gold read here is from ALLOWED worlds): realistic-training-mmr-20000/training.jsonl and gold/rows.jsonl of
development-20000, realistic-synthetic-20000, diagnostic-6000, pilot-500, practice-1897, external-development.
Never calibration/sealed/external-calibration/external-sealed.
Usage: python -I train.py --data DATA --out C/artifacts [--exclude dev]   (--exclude dev = development hold-out model)"""
import argparse, json, os, pickle, sys, time, collections
os.environ.setdefault('OMP_NUM_THREADS', '2'); os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core as C

ALLOWED = {'dev': 'realistic-v1/development-20000', 'synth': 'realistic-synthetic-20000', 'diag': 'realistic-v1/diagnostic-6000',
           'pilot': 'realistic-v1/pilot-500', 'prac': 'realistic-v1/practice-1897', 'extdev': 'realistic-v1/external-development'}
TRAINING = 'realistic-training-mmr-20000/training.jsonl'


def c2(b, x):
    return len(b[:x].decode())


def tags(r):
    """Experiment keys of a gold row: its template family and its aside families."""
    return {r['template_family']} | {d['family'] for d in r['distractors']}


def load(data, exclude, drop=()):
    """-> list of rows: dict(text, prev_subject or None, spans [(s,e)], form). drop: template/aside families left out."""
    out, fam = [], {}
    if drop:  # mmr examples are hidden-target rows of dev/synth/diag: look their families up by id
        for k in ('dev', 'synth', 'diag'):
            for l in open(os.path.join(data, ALLOWED[k], 'gold/rows.jsonl'), encoding='utf-8'):
                r = json.loads(l); fam[r['id']] = tags(r)
    for k, p in ALLOWED.items():
        if k in exclude:
            continue
        prev = None
        for l in open(os.path.join(data, p, 'gold/rows.jsonl'), encoding='utf-8'):
            r = json.loads(l); b = r['text'].encode()
            if drop and tags(r) & set(drop):
                prev = r['form'][-1]['subject'] if r['form'] else None
                continue
            sp = [(c2(b, s['start']), c2(b, s['end'])) for s in r['assertion_spans']]
            out.append(dict(text=r['text'], prev_subject=prev, spans=sp, form=r['form'], src=k))
            prev = r['form'][-1]['subject'] if r['form'] else None
    for l in open(os.path.join(data, TRAINING), encoding='utf-8'):
        e = json.loads(l)
        if 'dev' in exclude and 'development-20000' in e['source_release']:
            continue
        if drop and fam.get(e['id'], set()) & set(drop):
            continue
        t = e['input']['text']; b = t.encode(); tg = e['target']
        sp = [(c2(b, s['start']), c2(b, s['end'])) for s in tg['assertion_spans']]
        pr = e['input']['previous_row']
        ps = None
        if pr:  # previous row's subject is not given: its last lexicon mention is the best label-free guess
            m = C.mentions(pr['text']); ps = m[-1] if m else None
        out.append(dict(text=t, prev_subject=ps, spans=sp, form=tg['form'], src='mmr'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True); ap.add_argument('--out', required=True); ap.add_argument('--exclude', default='')
    ap.add_argument('--drop', default='', help='experiment only: comma list of template/aside families to leave out')
    a = ap.parse_args()
    exclude = set(x for x in a.exclude.split(',') if x)
    t0 = time.time()
    rows = load(a.data, exclude, [x for x in a.drop.split(',') if x])
    print('rows', len(rows), collections.Counter(r['src'] for r in rows), round(time.time() - t0, 1), 's', flush=True)
    P = []  # (norm text, raw piece, label dict)
    seg_ok = 0; kind_of = collections.defaultdict(collections.Counter)
    for r in rows:
        iv, pieces = C.segment(r['text'])
        gold = {sp: j for j, sp in enumerate(r['spans'])}
        ok = [p in gold for p in pieces[:len(r['spans'])]] == [True] * len(r['spans']) and len(pieces) >= len(r['spans'])
        seg_ok += ok
        last = max(e for _, e in r['spans']) if r['spans'] else 0
        prev = r['prev_subject']
        for i, p in enumerate(pieces):
            t = r['text'][p[0]:p[1]]
            if p in gold:
                f = r['form'][gold[p]]; s = f['subject']
                ment = C.mentions(t)
                lab_s = 'PRON' if (s not in ment and C.PRON.search(t)) else s
                P.append(dict(t=t, n=C.norm(t), aside=0, pos=i, s=s, ls=lab_s, a=f['attribute'], v=f['value'], ment=bool(ment)))
                kind_of[f['attribute']][f['value']['kind']] += 1
                prev = s
            elif p[0] >= last:
                P.append(dict(t=t, n=C.norm(t), aside=1, pos=i, ment=bool(C.mentions(t))))
    print('pieces', len(P), 'rows with exact segmentation', seg_ok, '/', len(rows), round(time.time() - t0, 1), 's', flush=True)
    KIND = {at: c.most_common(1)[0][0] for at, c in kind_of.items()}

    texts = sorted({p['n'] for p in P})
    vw = TfidfVectorizer(analyzer='word', ngram_range=(1, 2), min_df=2, sublinear_tf=True, token_pattern=r"[a-z0-9€$£%']+")
    vc = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), min_df=3, sublinear_tf=True, max_features=200000)
    vw.fit(texts); vc.fit(texts)

    def feats(ps):
        return C.feats(dict(vw=vw, vc=vc), ps)

    def fit(ps, key, C_=0.5):
        seen, X_, y = set(), [], []
        for p in ps:  # dedupe identical (text, label) pairs: the generator repeats itself
            k2 = (p['n'], p['ment'], p['pos'] > 0, p[key])
            if k2 in seen: continue
            seen.add(k2); X_.append(p); y.append(p[key])
        m = LinearSVC(C=C_).fit(feats(X_), y)
        print(' fit', key, len(X_), 'classes', len(m.classes_), round(time.time() - t0, 1), 's', flush=True)
        return m

    ass = [p for p in P if not p['aside']]
    A = fit(ass, 'a'); S = fit(ass, 'ls')
    X = fit([p for p in P if p['pos'] > 0], 'aside')

    # op and unit tables: what the grammar reads versus what gold says, keyed by attribute and the words before the value
    op_t = collections.defaultdict(collections.Counter); op_p = collections.defaultdict(collections.Counter)
    unit_t = collections.defaultdict(collections.Counter); name_t = collections.Counter(); found = collections.Counter()
    seen = set()
    for p in ass:
        k = p['v']['kind']
        if k == 'boolean' or (p['t'], p['s'], p['a']) in seen: continue
        seen.add((p['t'], p['s'], p['a']))
        g = p['v']; cs = C.candidates(p['t'], p['s'], k)
        hit = None
        for c in cs:
            v = c['value']
            if all(C.num_eq(g[x], v.get(x)) for x in g if x not in ('op', 'unit')) and k != 'name' or (k == 'name' and v['value'] == g['value']):
                hit = c; break
        found[(k, hit is not None)] += 1
        if hit is None: continue
        pw = C.prefix_words(p['t'], hit['start'])
        op_t[(p['a'], pw)][g.get('op')] += 1; op_p[pw][g.get('op')] += 1
        if 'unit' in g: unit_t[(p['a'], hit['value'].get('unit'))][g['unit']] += 1
    print('grammar finds gold value (kind, found):', sorted(found.items()), flush=True)
    vocab = collections.Counter(w for p in ass for w in C.toks(p['t']))
    art = dict(vw=vw, vc=vc, A=A, S=S, X=X, KIND=KIND, vocab={w for w, n in vocab.items() if n >= 2},
               op_t={k: v.most_common(1)[0][0] for k, v in op_t.items()}, op_p={k: v.most_common(1)[0][0] for k, v in op_p.items()},
               unit_t={k: v.most_common(1)[0][0] for k, v in unit_t.items()}, exclude=sorted(exclude),
               data_used=[ALLOWED[k] for k in ALLOWED if k not in exclude] + [TRAINING + (' (minus development-sourced examples)' if 'dev' in exclude else '')])
    os.makedirs(a.out, exist_ok=True)
    pickle.dump(art, open(os.path.join(a.out, 'model.pkl'), 'wb'))
    json.dump(dict(data_used=art['data_used'], rows=len(rows), pieces=len(P), seconds=round(time.time() - t0, 1)), open(os.path.join(a.out, 'training-data.json'), 'w'), indent=1)
    print('done', round(time.time() - t0, 1), 's')


if __name__ == '__main__':
    main()
