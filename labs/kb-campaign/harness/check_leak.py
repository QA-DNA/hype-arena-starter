"""Evaluator-side leakage checks (reads gold; never imported by a variant).
Usage: python -I check_leak.py [dev,diag,cal,sealed,syn]"""
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world as W  # noqa: E402


def check_suite(w):
    wkey = W.SUITE_WORLDS[w]
    base = os.path.join(W.SUITE_DIR, W.SUITE_PATHS[wkey])
    labeled = {r["id"]: r for r in csv.DictReader(open(os.path.join(base, "gold", "labeled.csv"), newline="",
                                                        encoding="utf-8"))}
    verd = {}
    for line in open(os.path.join(base, "gold", "rows.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        verd[r["id"]] = r["assertion_verdicts"]
    pub = {r["id"]: r for r in csv.DictReader(open(os.path.join(base, "public", "universe.csv"), newline="",
                                                    encoding="utf-8"))}
    out = {}
    for mode in ("j", "n"):
        t = W.load_track(f"S{w}-{mode}r")
        wd, gold, sc = t.folds[0]
        assert set(wd.__dict__) <= {"name", "static_key", "ids", "text", "interval", "facts", "lexicon", "date",
                                    "page", "n", "n_pages", "stats", "fidx", "frow", "flat", "n_facts", "fstart",
                                    "obs", "obs_typed", "labelled", "label"}, sorted(wd.__dict__)
        hid = ~wd.labelled
        assert all(x is None for x in wd.label[hid]), "a hidden row carries a label"
        assert all(wd.label[i] == pub[wd.ids[i]]["label"] for i in np.where(wd.labelled)[0])
        assert all(pub[wd.ids[i]]["label"] == "" for i in sc)
        assert all(wd.date[i] == W.A.ordinal(pub[wd.ids[i]]["date"]) for i in sc), "target date changed"
        if mode == "j":
            assert all(iv is None for iv in wd.interval)
        n_false = n_false_atoms = stated_eq_expected = rows_all_expected = 0
        for i in sc:
            rid = wd.ids[i]
            form = json.loads(labeled[rid]["form"])
            assert [f.raw for f in wd.facts[i]] == [a["value"] for a in form], f"{rid}: world fact != stated form"
            if labeled[rid]["label"] != "false":
                continue
            n_false += 1
            allexp, anyeq = True, False
            for f, v in zip(wd.facts[i], verd[rid]):
                if v["label"] != "false" or f.op != "eq":  # 'more than 4 h' with expected 4 h is false by its op
                    continue
                n_false_atoms += 1  # eq-op false atoms only
                anyeq = True
                e = v.get("expected_value")
                same = e is not None and W.A.canon(e, W.A.alias_map(wd.lexicon)) == f.acanon
                stated_eq_expected += same
                allexp &= same
            rows_all_expected += allexp and anyeq
        out[mode] = dict(targets=len(sc), false_targets=n_false, eq_false_atoms=n_false_atoms,
                         false_atoms_whose_fact_equals_expected=stated_eq_expected,
                         false_rows_all_false_atoms_expected=rows_all_expected, stats=wd.stats)
    return out


def check_practice():
    for name in ("P80", "P10"):
        t = W.load_track(name)
        for wd, gold, sc in t.folds:
            assert all(x is None for x in wd.label[sc]) and not wd.labelled[sc].any()
            assert all(x is not None for x in wd.label[wd.labelled])
            pl = np.zeros(wd.n_pages, bool); pl[wd.page[wd.labelled]] = True
            assert (pl[wd.page] == wd.labelled).all(), "labelled mask is not page-aligned"
    return "ok: hidden rows carry no label in every fold; labelled masks are whole pages"


if __name__ == "__main__":
    ws = sys.argv[1].split(",") if len(sys.argv) > 1 else ["dev", "diag", "cal", "sealed", "syn"]
    print("practice", check_practice())
    for w in ws:
        print(w, json.dumps(check_suite(w)))
