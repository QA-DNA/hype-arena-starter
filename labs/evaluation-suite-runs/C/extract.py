"""Worker C extractor: reads ONLY DATA/<world>/public/universe.csv plus C/artifacts, writes forms/C/<world>.jsonl.
Usage: python -I extract.py --world dev --data DATA [--artifacts C/artifacts] [--out /tmp/veridyct-evalsuite/forms/C]"""
import argparse, csv, json, math, os, pickle, sys, time
os.environ.setdefault('OMP_NUM_THREADS', '2'); os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core as C

WORLDS = {'dev': 'realistic-v1/development-20000', 'cal': 'realistic-v1/calibration-20000', 'sealed': 'realistic-v1/sealed-20000',
          'diag': 'realistic-v1/diagnostic-6000', 'pilot': 'realistic-v1/pilot-500', 'prac': 'realistic-v1/practice-1897',
          'extdev': 'realistic-v1/external-development', 'extcal': 'realistic-v1/external-calibration',
          'extsealed': 'realistic-v1/external-sealed', 'synth': 'realistic-synthetic-20000', 'clean': 'realistic-clean-input'}
MISSING = object()


def sig(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def pick_value(art, t, s, a):
    kind = art['KIND'].get(a)
    if kind is None:
        return None, 0.0
    if kind == 'boolean':
        return None, 1.0  # polarity filled in below
    cs = C.candidates(t, s, kind)
    if not cs:
        return None, 0.0
    c = cs[0]; v = dict(c['value'])
    pw = C.prefix_words(t, c['start'])
    op = art['op_t'].get((a, pw), MISSING)
    if op is MISSING:
        op = art['op_p'].get(pw, v.get('op'))
    v.pop('op', None)
    if op:
        v['op'] = op
    if 'unit' in v:
        v['unit'] = art['unit_t'].get((a, v['unit']), v['unit'])
    return v, (1.0 if len(cs) == 1 else 0.9)


def extract(rows, art):
    """rows: [dict(id, text)] in file order -> list of form dicts."""
    segs = [C.segment(r['text']) for r in rows]
    P = []  # flat piece list
    for ri, (r, (iv, pieces)) in enumerate(zip(rows, segs)):
        for i, (s, e) in enumerate(pieces):
            t = r['text'][s:e]
            m = C.mentions(t)
            P.append(dict(ri=ri, t=t, n=C.norm(t), pos=i, ment=bool(m), m=m))
    F = C.feats(art, P) if P else None
    sA = art['A'].decision_function(F); sS = art['S'].decision_function(F); sX = art['X'].decision_function(F)
    Ai = {a: i for i, a in enumerate(art['A'].classes_)}; Si = {s: i for i, s in enumerate(art['S'].classes_)}
    aside_pos = list(art['X'].classes_).index(1)
    out, prev, k = [], None, 0
    bool_jobs = []
    for ri, (r, (iv, pieces)) in enumerate(zip(rows, segs)):
        ass, cut, row_conf = [], False, 1.0
        for i in range(len(pieces)):
            p = P[k + i]
            if cut:
                continue
            xs = sX[k + i] if aside_pos == 1 else -sX[k + i]
            if i > 0:  # rule decides (generalises to unseen aside pools); the learned aside model only sets confidence
                if not (p['m'] or C.keep_piece(p['t'], art['vocab'])):
                    cut = True; row_conf = min(row_conf, sig(4 * xs) if xs > 0 else 0.6); continue
                row_conf = min(row_conf, sig(-4 * xs) if xs < 0 else 0.6)
            cands = {}
            for s in p['m']:
                if s in Si and s in C.ATTRS_OF:
                    cands[s] = sS[k + i, Si[s]] + 1.0
            mnorm = {C.norm(m) for m in p['m']}
            for j in np.argsort(-sS[k + i])[:3]:
                s = art['S'].classes_[j]
                if s != 'PRON' and s in C.ATTRS_OF and not (s not in p['m'] and C.norm(s) in mnorm):  # digit-blind twin of a mention
                    cands[s] = max(cands.get(s, -9.0), sS[k + i, j])
            if prev and C.PRON.search(p['t']) and prev in C.ATTRS_OF:
                cands[prev] = max(cands.get(prev, -9.0), sS[k + i, Si['PRON']] + (0.0 if p['m'] else 1.0))
            kinds = C.typed_kinds(p['t']) | {'name'}
            strong = kinds - {'quantity', 'name'}
            scored = []
            for s, ss in cands.items():
                for a in C.ATTRS_OF[s]:
                    if a not in Ai: continue
                    kd = art['KIND'].get(a)
                    if kd == 'boolean':
                        pen = -1.0 if strong else 0.0  # no training boolean piece holds a money/percent/date/duration/version
                    else:
                        pen = 0.0 if kd in kinds or (kd == 'percent' and '%' in p['t']) or (kd == 'version' and C._VER.search(p['t'])) else -1.0
                    scored.append((ss + sA[k + i, Ai[a]] + pen, s, a))
            if not scored:
                continue
            scored.sort(reverse=True)
            pick = None
            for rank, (sc, s, a) in enumerate(scored[:10]):  # best pair whose value is readable
                v, vc = pick_value(art, p['t'], s, a)
                if v is not None or art['KIND'].get(a) == 'boolean':
                    nxt = next((x[0] for x in scored[rank + 1:] if (x[1], x[2]) != (s, a)), sc - 2.0)
                    pick = (sc, s, a, v, vc * (1.0 if rank == 0 else 0.7), sc - nxt); break
            if pick is None:
                continue  # nothing readable: an unseen aside, not an assertion
            best, s, a, v, vc, margin = pick
            item = dict(subject=s, attribute=a, value=v, conf=round(sig(4 * margin) * vc, 4))
            if art['KIND'].get(a) == 'boolean':
                bool_jobs.append((item, k + i))
            ass.append(item); prev = s
        k += len(pieces)
        out.append(dict(id=r['id'], assertions=ass, interval=segs[ri][0],
                        conf=round(min([row_conf] + [x['conf'] for x in ass]), 4) if ass else 0.0))
    for item, j in bool_jobs:  # polarity rule: 3,102/3,102 training booleans are negated exactly when NEG_RE fires
        item['value'] = dict(kind='boolean', value=not C.V.NEG_RE.search(P[j]['t']))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--world', required=True); ap.add_argument('--data', default='/Users/mogaeduard/Downloads/evaluation-data')
    ap.add_argument('--artifacts', default=os.path.join(C.HERE, 'artifacts')); ap.add_argument('--out', default='/tmp/veridyct-evalsuite/forms/C')
    a = ap.parse_args()
    t0 = time.time()
    art = pickle.load(open(os.path.join(a.artifacts, 'model.pkl'), 'rb'))
    rows = list(csv.DictReader(open(os.path.join(a.data, WORLDS[a.world], 'public/universe.csv'), encoding='utf-8')))
    out = extract(rows, art)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, a.world + '.jsonl'), 'w', encoding='utf-8') as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    print(json.dumps(dict(world=a.world, rows=len(rows), seconds=round(time.time() - t0, 1))))


if __name__ == '__main__':
    main()
