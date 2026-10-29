"""Export parity fixtures for the Rust port of the F2 chain (crates/core/src/kb_chain.rs).

practice: labelled-page masks of P80 folds 0..4 and P10 seeds 0..9, expected predictions of P80 0..4 and
P10 0..2 (row index in id order, label, confidence as f64 bits). Small, public, committed.
--sdev OUT: Sdev-jt world (rows, dates, pages, labels, raw assertions, lexicon) plus expected predictions;
suite data, local only, never committed. --debug OUT: per-fact scores and per-row probabilities.

  KBC_ROOT=$PWD/labs/kb-campaign KBC_PRACTICE_DIR=$PWD/data python -I labs/kb-campaign/F2/export_rust_fixture.py \
      --practice crates/core/tests/data/kb-chain-practice.txt [--sdev /tmp/sdev.jsonl] [--debug /tmp/dbg.txt]
"""
import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import f2var  # noqa: E402
import world as W  # noqa: E402

PARAMS = {"d0": 0.03, "engine": "viterbi", "eps_a": 0.0005, "mono": "fit", "mono_a": 10, "pi_o": 1, "vote_lr": 48}


def bits(x):
    return "-" if x != x else struct.pack(">d", float(x)).hex()


def run(w):
    v = f2var.Chain(**PARAMS)
    v.fit(w)
    s = v.scores(w)
    pred = v.predict(w)
    return v, s, pred


def emit(out, w, pred, rows):
    for i in rows:
        out.write(f"pred {i} {pred.labels[i][0]} {bits(pred.conf[i])}\n")


def debug_dump(dbg, tag, w, v, s, pred):
    hz = v.hz
    dbg.write(f"world {tag} glob {bits(hz.glob)} kinds {json.dumps({k[1]: bits(x) for k, x in hz.tab.items() if k[0] == 'kind'})}"
              f" down {json.dumps({k: bits(x) for k, x in hz.down.items()})} u {bits(v.rc.u)}\n")
    for n in range(w.n_facts):
        dbg.write(f"fact {n} {int(w.frow[n])} {bits(s[n])} {bits(pred.fact_scores[n])}\n")
    prow = f2core_row(w, pred.fact_scores)
    for i in range(w.n):
        dbg.write(f"row {i} {int(w.page[i])} {bits(prow[i])}\n")


def f2core_row(w, pf):
    import f2core
    return f2core.row_prob(w, pf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--practice")
    ap.add_argument("--sdev")
    ap.add_argument("--debug")
    a = ap.parse_args()
    dbg = open(a.debug, "w") if a.debug else None
    if a.practice:
        _, base, gold = W.practice_full()
        with open(a.practice, "w") as out:
            out.write(f"# F2 chain parity fixture {json.dumps(PARAMS, sort_keys=True)}; rows in practice id order\n")
            for track in ("P80", "P10"):
                masks = list(W.practice_splits(base.n_pages, track))
                for f, lab_pages in enumerate(masks):
                    out.write(f"fold {track} {f} {''.join('1' if x else '0' for x in lab_pages)}\n")
                    if track == "P10" and f > 2:
                        continue
                    lab = lab_pages[base.page]
                    w = base.with_labels(lab, gold)
                    v, s, pred = run(w)
                    emit(out, w, pred, np.where(~lab)[0])
                    if dbg:
                        debug_dump(dbg, f"{track}-{f}", w, v, s, pred)
    if a.sdev:
        t = W.load_track("Sdev-jt")
        w, gold, sc = t.folds[0]
        uni_p, lex_p, forms_p = W._suite_files("dev", "gold")
        recs = {}
        for line in open(forms_p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                recs.setdefault(str(r.get("id")), r)
        v, s, pred = run(w)
        with open(a.sdev, "w") as out:
            out.write(json.dumps({"lexicon": w.lexicon}) + "\n")
            for i in range(w.n):
                rec = recs.get(w.ids[i]) or {}
                out.write(json.dumps({"id": w.ids[i], "date": int(w.date[i]), "page": int(w.page[i]),
                                      "label": w.label[i], "assertions": rec.get("assertions") or [],
                                      "pred": pred.labels[i][0], "conf": bits(pred.conf[i])}) + "\n")
        if dbg:
            debug_dump(dbg, "Sdev-jt", w, v, s, pred)


if __name__ == "__main__":
    main()
