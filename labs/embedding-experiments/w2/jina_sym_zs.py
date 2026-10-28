"""extra jina-v3 zero-shot variant: text-matching task on BOTH sides (symmetric), via the harness + ResultWriter"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/w2')
import run_model as R, numpy as np
H = R.H
meta, Z, Xp, Xs, Xq = R.load_emb('jina-v3'); add = R.make_rec('jina-v3', meta)
for vn, fn, name in (('desc', H.describe, 'describe'), ('words', lambda s, a: H.attr_words(a), 'attr_words_only')):
    Q, D = R.l2(Xs[R.SF]), R.l2(Z[f'D_d_alt_{vn}'])
    m, _ = H.zeroshot_attr(lambda descs, D=D, vn=vn: (descs == R.DESC[vn]) and Q @ D.T, R.sf, R.lex, desc_fn=fn)
    add('attr_zeroshot', name + '+q_sym_view+d_alt', m, len(R.sf), 'text-matching task on both sides (rows and descriptions)')
