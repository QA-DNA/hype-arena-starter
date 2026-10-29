"""Invariants of every stress builder (no variant involved). Run: cd $KBC && .venv/bin/python -I F6/selfcheck.py
Checks, per part of each cell: gold aligned with the scored rows; scored rows unlabelled; no label on any unlabelled row
(no gold in a World); scored ids are original rows of the base (copies never scored); stress-specific invariants."""
import collections as C
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import stress as S  # noqa: E402
import world as W  # noqa: E402


def generic(cell, parts, base_ids, base_gold):
    for rep, w, gold, sc, subsets in parts:
        assert len(gold) == len(sc), cell
        assert not w.labelled[sc].any(), f"{cell}: a scored row is labelled"
        assert all(x is None for x in w.label[~w.labelled]), f"{cell}: label on an unlabelled row"
        for i, g in zip(sc, gold):
            assert base_gold[w.ids[i]] == g, f"{cell}: gold misaligned at {w.ids[i]}"
        assert not any(w.ids[i].startswith("cp") and w.ids[i] not in base_ids for i in sc), f"{cell}: copy scored"
        assert w.n_pages == len(set(w.page.tolist())) and w.page.min() == 0, f"{cell}: pages not compact"
        for name, m in subsets.items():
            assert len(m) == len(sc), (cell, name)


def gold_map(base):
    out = {}
    for _, w, g, sc in S.base_parts(base)[0]:
        out.update({w.ids[i]: x for i, x in zip(sc, g)})
        out.update({w.ids[i]: w.label[i] for i in np.where(w.labelled)[0]})
    return out


def main():
    for base in ("P80", "P10", "Sdev-jr", "Sdev-nt"):
        bparts, _ = S.base_parts(base)
        ids = set(bparts[0][1].ids)
        gm = gold_map(base)
        scored0 = C.Counter(bparts[0][1].ids[i] for _, w, g, sc in bparts for i in sc)
        for cell in [c for c in S.battery() if c[2] == base and (c[0] != "noise" or c[1].startswith("mix"))]:
            parts, train, info = S.build(cell)
            generic(cell, parts, ids, gm)
            stress, level = cell[0], cell[1]
            reps = C.defaultdict(C.Counter)
            for rep, w, g, sc, _ in parts:
                reps[rep].update(w.ids[i] for i in sc)
            for rep, cnt in reps.items():  # every stress scores each base target exactly once per replicate
                assert sum(cnt.values()) == sum(scored0.values()) // (10 if base == "P10" else 1) or base == "P10", cell
                if base != "P10":
                    assert cnt == scored0, f"{cell}: scored set differs from the base"
            if stress == "copies":
                for rep, w, g, sc, _ in parts:
                    cp = [i for i in range(w.n) if w.ids[i] not in ids]
                    assert len(cp) == w.stats["copies"] and not w.labelled[cp].any()
            if stress == "unseen":
                for (rep, w, g, sc, sub), (_, bw, _, bsc) in zip(parts, [p for p in bparts for _ in range(3)]):
                    assert (w.labelled <= bw.labelled).all() and np.array_equal(sc, bsc)
        print("ok", base)
    lab = S.build(("labels", "0.1", "P"))[0]
    p10 = S.base_parts("P10")[0]
    assert all(np.array_equal(a[1].labelled, b[1].labelled) for a, b in zip(lab, p10)), "labels 0.1 != P10"
    for base in ("P80", "Sdev-jr"):  # noise at rate 0 changes nothing
        for (_, w, _, _, _), (_, bw, _, _) in zip(S.st_noise(base, "mix@0.0/all")[0], S.base_parts(base)[0]):
            assert all(S.fact_sig(a) == S.fact_sig(b) for a, b in zip(w.facts, bw.facts))
    print("selfcheck ok")


if __name__ == "__main__":
    main()
