"""w4: NLI / zero-shot cross-encoders on sentence PAIRS (tasks nli_conflict + speed, nli_anchor, nli_attr).
Usage:  python -I nli_run.py <model-key> <budget_s> [--only conflict,anchor,attr] [--reverse] [--tmpl2] [--scratch]
Budget model: a 64-pair calibration gives pairs/s v; N = v*budget pairs are split conflict 27% / anchors 28% / attr the rest
(each capped at the full workload). Items are scored in a FIXED seeded order, so every model's sample is a prefix of the
same order (common-N comparisons are recomputed offline from scores/<key>.*.npz). Logits are stored, nothing is thresholded."""
import sys, os, time, json, glob, inspect
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import numpy as np
from sklearn.metrics import roc_auc_score
from transformers import AutoTokenizer, AutoModelForSequenceClassification

ROOT = '/tmp/veridyct-emb/w4'
W = 'w4'
MODELS = {  # key -> HF id
    'ce-xsmall': 'cross-encoder/nli-deberta-v3-xsmall', 'ce-small': 'cross-encoder/nli-deberta-v3-small',
    'ce-base': 'cross-encoder/nli-deberta-v3-base', 'ce-minilm2-l6-h768': 'cross-encoder/nli-MiniLM2-L6-H768',
    'ce-distilroberta': 'cross-encoder/nli-distilroberta-base',
    'ml-base-mnli-fever-anli': 'MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli',
    'ml-base-zeroshot2': 'MoritzLaurer/deberta-v3-base-zeroshot-v2.0',
    'ml-large-zeroshot2': 'MoritzLaurer/deberta-v3-large-zeroshot-v2.0',
    'ml-modernbert-base-zeroshot2': 'MoritzLaurer/ModernBERT-base-zeroshot-v2.0',
    'ts-deberta-small-long-nli': 'tasksource/deberta-small-long-nli',
    'albert-xlarge-vitaminc-mnli': 'tals/albert-xlarge-vitaminc-mnli', 'bart-large-mnli': 'facebook/bart-large-mnli'}
TMPL1 = 'This sentence states the {attr} of {subj}.'
TMPL2 = '{subj}: {attr}'
SANITY = [  # (premise, hypothesis, expected)  e=entailment c=contradiction n=neutral
    ('Pixel 10 costs €799.', 'Pixel 10 costs €799.', 'e'),
    ('Pixel 10 costs €799.', 'Pixel 10 costs €549.', 'c'),
    ('Pixel 10 costs €799.', 'The Pixel 10 has a 6.3 inch display.', 'n'),
    ('Holdan joined Hooly on 12 January 2026.', 'Holdan joined Hooly on 12 January 2026.', 'e'),
    ('Holdan joined Hooly on 12 January 2026.', 'Holdan joined Hooly on 3 March 2026.', 'c'),
    ('Hooly Cloud has 4 engineers.', 'The platform serves small software firms.', 'n')]

ASYM = [  # (premise, hypothesis, expected): the reverse of an entailed pair is neutral, so the order matters
    ('Holdan joined Hooly on 12 January 2026.', 'Holdan joined Hooly.', 'e'),
    ('Holdan joined Hooly.', 'Holdan joined Hooly on 12 January 2026.', 'n'),
    ('The Pixel 10 costs \u20ac799 and has a 6.3 inch display.', 'The Pixel 10 costs \u20ac799.', 'e'),
    ('The Pixel 10 costs \u20ac799.', 'The Pixel 10 costs \u20ac799 and has a 6.3 inch display.', 'n'),
    ('Hooly Cloud has over 100 customers.', 'Hooly Cloud has more than 50 customers.', 'e'),
    ('Hooly Cloud has more than 50 customers.', 'Hooly Cloud has over 100 customers.', 'n')]


def model_dir(rid):
    d = f"{ROOT}/models/{rid.replace('/', '--')}"
    if os.path.exists(d + '/.dl_done'): return d
    g = sorted(glob.glob(f"/tmp/veridyct-bench/hf/hub/models--{rid.replace('/', '--')}/snapshots/*"))  # shared cache: read only
    if g: return g[0]
    raise FileNotFoundError(rid)


def label_map(id2label):
    """-> {'e','c','n','ne'} -> column index, from the config's own label names."""
    m = {}
    for i, n in id2label.items():
        n = str(n).lower().replace('_', ' ')
        if n in ('not entailment',): m['ne'] = int(i)
        elif n.startswith('entail') or n in ('supports', 'support'): m['e'] = int(i)
        elif n.startswith('contradict') or n in ('refutes', 'refute'): m['c'] = int(i)
        elif n.startswith('neutral') or n == 'not enough info': m['n'] = int(i)
    return m


class Scorer:
    def __init__(self, key):
        self.key, self.rid = key, MODELS[key]
        self.dir = model_dir(self.rid)
        self.tok = AutoTokenizer.from_pretrained(self.dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.dir, dtype=torch.float32).eval()
        self.lm = label_map(self.model.config.id2label)
        self.params_m = sum(p.numel() for p in self.model.parameters()) / 1e6
        self.disk_mb = sum(os.path.getsize(f) for f in glob.glob(self.dir + '/*.safetensors')) / 1e6
        self.accepts_tt = 'token_type_ids' in inspect.signature(self.model.forward).parameters
        # transformers 5.x: the converted ALBERT tokenizer returns NO token_type_ids by default (model then sees one segment and
        # misclassifies identical sentences as NOT ENOUGH INFO). Ask for them explicitly when the model has real segment embeddings.
        self.need_tt = getattr(self.model.config, 'type_vocab_size', 0) >= 2
        self.swap = False  # True: feed (hypothesis, premise) -- decided by sanity() for VitaminC-style models

    @torch.inference_mode()
    def _batch(self, A, B):
        a, b = (B, A) if self.swap else (A, B)
        enc = self.tok(a, b, padding=True, truncation=True, max_length=192, return_tensors='pt', return_token_type_ids=True if self.need_tt else None)
        if not self.accepts_tt: enc.pop('token_type_ids', None)
        return self.model(**enc).logits.float().numpy()

    def logits(self, A, B, bs=32):
        """(premises, hypotheses) -> (n, n_labels) float32 logits in input order; batches sorted longest first."""
        order = np.argsort([-(len(a) + len(b)) for a, b in zip(A, B)], kind='stable')
        out = np.zeros((len(A), self.model.config.num_labels), np.float32)
        for s in range(0, len(A), bs):
            ix = order[s:s + bs]
            out[ix] = self._batch([A[i] for i in ix], [B[i] for i in ix])
        return out

    def timed(self, A, B, bs=32):
        """One untimed warm-up batch (the longest pairs), then the full pass timed. -> (logits, wall_s)."""
        order = np.argsort([-(len(a) + len(b)) for a, b in zip(A, B)], kind='stable')[:bs]
        self._batch([A[i] for i in order], [B[i] for i in order])
        t0 = time.perf_counter(); lg = self.logits(A, B, bs); return lg, time.perf_counter() - t0

    def feats(self, lg):
        """logits -> (p_entail, p_contra, entail_logodds). Binary zero-shot models have no contradiction class:
        p_contra := p(not_entailment) (a proxy that also counts neutral)."""
        z = lg.astype(np.float64); P = np.exp(z - z.max(1, keepdims=True)); P /= P.sum(1, keepdims=True)
        e = self.lm['e']
        pc = P[:, self.lm['c']] if 'c' in self.lm else P[:, self.lm['ne']]
        return P[:, e], pc, z[:, e] - np.logaddexp.reduce(np.delete(z, e, axis=1), axis=1)

    def sanity(self):
        """Hand-made pairs (SANITY). VitaminC-style models (labels SUPPORTS/REFUTES/...) were trained on (claim, evidence), and
        value-only sanity pairs are symmetric, so for them the input order is picked on 6 ASYMMETRIC pairs (entailed vs neutral
        flips with the order). -> (note string, passed bool)."""
        def run(swap, items):
            self.swap = swap
            lg = self.logits([p for p, _, _ in items], [h for _, h, _ in items]); pe, pc, _ = self.feats(lg)
            P = np.exp(lg - lg.max(1, keepdims=True)); P /= P.sum(1, keepdims=True)
            ok, out, good_n = True, [], 0
            for k, (_, _, exp) in enumerate(items):
                if 'c' in self.lm:
                    got = {self.lm['e']: 'e', self.lm['c']: 'c'}.get(int(P[k].argmax()), 'n')
                else:
                    got = 'e' if P[k, self.lm['e']] > .5 else 'x'   # x = not_entailment (contradiction or neutral)
                good = got == exp or (got == 'x' and exp in 'cn')
                ok &= good; good_n += good; out.append(f"{exp}->{got}({pe[k]:.2f}/{pc[k]:.2f}){'' if good else '!'}")
            return ok, ' '.join(out), good_n
        extra = ''
        if str(self.model.config.id2label.get(0, '')).upper() == 'SUPPORTS':
            _, sa, na = run(False, ASYM); _, sb, nb = run(True, ASYM)
            swap = nb > na
            extra = f' | order test on {len(ASYM)} asymmetric pairs: premise-first {na}/{len(ASYM)} [{sa}] vs hypothesis-first {nb}/{len(ASYM)} [{sb}] -> swap={swap}'
        else:
            swap = False
        ok, s, _ = run(swap, SANITY)
        return f"labels={self.model.config.id2label} swap={self.swap} sanity[exp->got(p_ent/p_con)]: {s} => {'PASS' if ok else 'FAIL'}{extra}", ok


def strat_order(groups, weights, seed):
    """Permutation of range(n) whose every prefix has group counts ~ proportional to weights[group] (until exhausted)."""
    rng, g = np.random.default_rng(seed), np.asarray(groups, dtype=object); key = np.zeros(len(g))
    for k, w in weights.items():
        ix = rng.permutation(np.flatnonzero(g == k)); key[ix] = (np.arange(len(ix)) + rng.random(len(ix))) / w
    return np.argsort(key, kind='stable')


def auc(y, s):
    y = np.asarray(y, int); return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float('nan')


def main():
    key, budget = sys.argv[1], float(sys.argv[2])
    if os.path.exists(f'{ROOT}/budget_cap'): budget = min(budget, float(open(f'{ROOT}/budget_cap').read()))  # time-box throttle, set by hand
    only = (sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else ['conflict', 'anchor', 'attr'])
    reverse, tmpl2 = '--reverse' in sys.argv, '--tmpl2' in sys.argv
    wr = H.ResultWriter(f'{ROOT}/scratch.jsonl' if '--scratch' in sys.argv else H.results_path(W))
    os.makedirs(f'{ROOT}/scores', exist_ok=True)
    rows, lex = H.load(); byidx = {r['idx']: r for r in rows}
    sf = H.single_fact_rows(rows)
    t_load = time.time(); S = Scorer(key)
    note0, ok = S.sanity()
    print(f'[{key}] loaded {time.time() - t_load:.1f}s params={S.params_m:.1f}M disk={S.disk_mb:.0f}MB {note0}', flush=True)
    base = dict(params_m=round(S.params_m, 2), disk_mb=round(S.disk_mb, 1))

    # ---- workloads (fixed seeded order) ----
    P = H.same_key_pairs(rows)
    kind = [byidx[i]['facts'][0]['value']['kind'] for i, _, _ in P]
    kn = {k: kind.count(k) for k in set(kind)}
    ordC = strat_order(kind, {k: n ** .5 for k, n in kn.items()}, 0)
    NA = H.nearest_anchors(rows, k=2)
    tf = [r for r in sf if r['label'] in ('true', 'false') and NA[r['idx']]]
    ordA = strat_order([r['label'] for r in tf], {'false': 1., 'true': 2.}, 1)
    ordR = np.random.default_rng(2).permutation(len(sf))
    ncand = [len(H.candidates(lex, r['facts'][0]['subject'])) for r in sf]

    # ---- calibration -> allocation ----
    cal = ordC[:64]; _ = S._batch([rows[P[k][0]]['text'] for k in cal[:32]], [rows[P[k][1]]['text'] for k in cal[:32]])
    t0 = time.perf_counter()
    S.logits([rows[P[k][0]]['text'] for k in cal], [rows[P[k][1]]['text'] for k in cal]); v = 64 / (time.perf_counter() - t0)
    N = v * budget
    pc = int(min(len(P), max(96, .27 * N)))
    if only == ['conflict']: pc = int(min(len(P), max(96, N)))   # conflict-only top-up run: whole budget goes to conflict (same prefix of the same order)
    ra = int(min(len(tf), max(40, .28 * N / 2.68)))
    pa = sum(len(NA[tf[i]['idx']]) for i in ordA[:ra])
    rr = int(min(len(sf), max(10, (N - pc - pa) / 14.3)))
    if v < 50: rr = min(rr, 400)     # brief: slower than 50 pairs/s -> at most 400 sampled rows
    if reverse or tmpl2: pass
    print(f'[{key}] calibration {v:.1f} pairs/s -> N={N:.0f} pairs: conflict {pc}/{len(P)}, anchor rows {ra}/{len(tf)} ({pa} pairs), attr rows {rr}/{len(sf)}', flush=True)
    samp = lambda full, n: '' if n >= full else f' SAMPLED {n}/{full} (seeded, stratified prefix)'

    # ================= nli_conflict + speed =================
    if 'conflict' in only and not (reverse or tmpl2):
        try:
            sel = ordC[:pc]; A = [rows[P[k][0]]['text'] for k in sel]; B = [rows[P[k][1]]['text'] for k in sel]
            ns = min(2000, pc); lg1, wall = S.timed(A[:ns], B[:ns])
            lg = lg1 if ns == pc else np.vstack([lg1, S.logits(A[ns:], B[ns:])])
            np.savez(f'{ROOT}/scores/{key}.conflict.npz', sel=sel, logits=lg)
            pe, pcn, lo = S.feats(lg)
            y = np.array([not P[k][2] for k in sel], int); kd = np.array([kind[k] for k in sel])
            variants = {'p_contra': pcn} if 'c' in S.lm else {}
            variants['1-p_entail'] = 1 - pe
            for vn, sc in variants.items():
                vn_ = 'p_not_entail' if 'c' not in S.lm else vn
                m = H.binary_metrics(y, sc)
                bk = {k: dict(auc=auc(y[kd == k], sc[kd == k]), n=int((kd == k).sum()), n_differ=int(y[kd == k].sum())) for k in sorted(kn)}
                wr.add(W, key, 'nli_conflict', vn_, m, n=len(sel), notes=f'{note0} | premise=text_i hypothesis=text_j target=values differ{samp(len(P), pc)}',
                       by_kind=bk, **base)
            wr.add(W, key, 'speed', 'bs32-2threads-pairs', dict(pairs_per_s=ns / wall, wall_s=wall, est_sec_20k_pairs_x86=20000 / (ns / wall) * 2.0, n_pairs=ns),
                   n=ns, notes=f'{note0} | timed pass over {ns} conflict pairs (text_i, text_j), bs 32, longest first, 1 warm-up batch, torch fp32 2 threads, load avg {os.getloadavg()[0]:.1f}',
                   pairs_per_s=ns / wall, **base)
            print(f'[{key}] conflict done: auc={H.binary_metrics(y, variants.get("p_contra", 1 - pe))["auc"]:.3f} speed={ns / wall:.1f} pairs/s n={len(sel)}', flush=True)
        except Exception as e:
            print(f'[{key}] CONFLICT FAILED {type(e).__name__}: {e}', flush=True)

    # ================= nli_anchor =================
    def anchor(direction):
        nrow = ra if direction == 'forward' else min(len(np.load(f'{ROOT}/scores/{key}.anchor_forward.npz')['rows']), int(v * 100 / 2.68))
        sel_rows = [tf[i] for i in ordA[:nrow]]  # reverse reuses the forward run's rows (same prefix of the same order)
        pr = [(r, a) for r in sel_rows for a in NA[r['idx']]]
        prem = [byidx[a['idx']]['text'] if direction == 'forward' else r['text'] for r, a in pr]
        hyp = [r['text'] if direction == 'forward' else byidx[a['idx']]['text'] for r, a in pr]
        lg = S.logits(prem, hyp)
        np.savez(f'{ROOT}/scores/{key}.anchor_{direction}.npz', rows=np.array([r['idx'] for r in sel_rows]), pair_row=np.array([r['idx'] for r, _ in pr]),
                 pair_anchor=np.array([a['idx'] for _, a in pr]), logits=lg)
        pe, pcn, _ = S.feats(lg)
        y, pcm, pem, pcnr, penr, diff = [], [], [], [], [], []
        pos = 0
        for r in sel_rows:
            k = len(NA[r['idx']]); sl = slice(pos, pos + k); pos += k
            y.append(int(r['label'] == 'false')); pcm.append(pcn[sl].max()); pem.append(pe[sl].max())
            pcnr.append(pcn[pos - k]); penr.append(pe[pos - k]); diff.append(not NA[r['idx']][0]['same_value'])
        y, pcm, pem, pcnr, penr, diff = map(np.asarray, (y, pcm, pem, pcnr, penr, diff))
        det = {}
        for nm, sc in (('p_contra_max', pcm), ('p_contra_nearest', pcnr)):
            det[f'{nm}_auc_all'] = auc(y, sc)
            det[f'{nm}_auc_nearest_value_differs'] = auc(y[diff], sc[diff]); det[f'{nm}_auc_nearest_value_same'] = auc(y[~diff], sc[~diff])
        det.update(n_differs=int(diff.sum()), pos_differs=int(y[diff].sum()), n_same=int((~diff).sum()), pos_same=int(y[~diff].sum()),
                   auc_p_entail_nearest_all=auc(y, 1 - penr), auc_1m_p_entail_max_differs=auc(y[diff], 1 - pem[diff]), auc_1m_p_entail_max_same=auc(y[~diff], 1 - pem[~diff]),
                   auc_value_differs_vs_p_contra_nearest=auc(diff.astype(int), pcnr), n_pairs=len(pr))
        nt = f'{note0} | direction={direction} ({"premise=anchor text, hypothesis=row text" if direction == "forward" else "premise=row text, hypothesis=anchor text"}); true/false single-fact rows with >=1 anchor{samp(len(tf), len(sel_rows))}; binary models: contra := not_entailment'
        pn = 'p_contra_max' if 'c' in S.lm else 'p_not_entail_max'
        wr.add(W, key, 'nli_anchor', f'{direction}:{pn}', H.binary_metrics(y, pcm), n=len(sel_rows), notes=nt, detail=det, **base)
        wr.add(W, key, 'nli_anchor', f'{direction}:1-p_entail_max', H.binary_metrics(y, 1 - pem), n=len(sel_rows), notes=nt, detail=det, **base)
        print(f'[{key}] anchor {direction} done: auc_pcmax={auc(y, pcm):.3f} auc_1-pe_max={auc(y, 1 - pem):.3f} n={len(sel_rows)}', flush=True)

    if 'anchor' in only:
        for d in (['reverse'] if reverse else [] if tmpl2 else ['forward']):
            try: anchor(d)
            except Exception as e: print(f'[{key}] ANCHOR {d} FAILED {type(e).__name__}: {e}', flush=True)

    # ================= nli_attr =================
    if 'attr' in only and not reverse:
        try:
            tm, tn = (TMPL2, 'tmpl2') if tmpl2 else (TMPL1, 'tmpl1')
            if tmpl2:  # same rows as the tmpl1 run of this model (read its stored row count), bounded by a 100 s pass
                z = np.load(f'{ROOT}/scores/{key}.attr_tmpl1.npz'); rr = min(len(z['rows']), int(v * 100 / 14.3))
            sel = [sf[i] for i in ordR[:rr]]; prem, hyp, own = [], [], []
            for n_, r in enumerate(sel):
                f = r['facts'][0]
                for a in H.candidates(lex, f['subject']):
                    prem.append(r['text']); hyp.append(tm.format(attr=H.attr_words(a), subj=f['subject'])); own.append((n_, a))
            lg = S.logits(prem, hyp); _, _, lo = S.feats(lg)
            best, pred = {}, []
            for (n_, a), s in zip(own, lo):
                if n_ not in best or s > best[n_][0]: best[n_] = (s, a)
            pred = [best[n_][1] for n_ in range(len(sel))]
            yt = [r['facts'][0]['attribute'] for r in sel]
            m = H.attr_metrics(yt, pred, np.zeros(len(sel), int))
            chance = float(np.mean([1 / ncand[i] for i in ordR[:rr]]))
            np.savez(f'{ROOT}/scores/{key}.attr_{tn}.npz', rows=np.array([r['idx'] for r in sel]), pred=np.array(pred, dtype=object), y=np.array(yt, dtype=object), logits=lg)
            wr.add(W, key, 'nli_attr', f'{tn}:{tm}', m, n=len(sel), notes=f'{note0} | premise=row text, hypothesis={tm!r} (attr words, gold subject); argmax of entailment log-odds over the gold subject\'s lexicon attributes; train_counts all 0{samp(len(sf), len(sel))}',
                   n_pairs=len(prem), chance_acc=chance, **base)
            print(f'[{key}] attr {tn} done: acc={m["acc_all"]:.3f} n={len(sel)} (chance {chance:.3f}) pairs={len(prem)}', flush=True)
        except Exception as e:
            print(f'[{key}] ATTR FAILED {type(e).__name__}: {e}', flush=True)
    print(f'[{key}] FINISHED', flush=True)


if __name__ == '__main__':
    main()
