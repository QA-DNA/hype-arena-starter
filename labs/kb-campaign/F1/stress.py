"""Copied-lie stress test (tell-free, as labs/kb-experiments/v12.py hlie / hctrl) on the P10 splits.
For each P10 seed: every hidden FALSE row gets 3 unlabelled copies (same text and facts) on new pages dated
+1, +7, +30 days (hlie); the control copies the same number of hidden TRUE rows (seed 12345, hctrl).
Copies are never labelled and never scored; metrics on the original hidden rows. Gold is used only by this
evaluator to pick which rows to copy and to score; the variant sees the augmented public world only.

  python -I stress.py '<params json>' ...   -> one JSON line per (params, scenario) to ../results/F1-stress.jsonl
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness")); sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import metrics as M  # noqa: E402
from api import check_prediction  # noqa: E402
from world import World, load_track, RESULTS_DIR  # noqa: E402
import f1var  # noqa: E402


def augment(w, src_rows):
    ids, text, date, iv, facts = list(w.ids), list(w.text), list(w.date), list(w.interval), list(w.facts)
    labelled, label, page = list(w.labelled), list(w.label), list(w.page)
    np_ = w.n_pages
    for i in src_rows:
        for k, dd in enumerate((1, 7, 30)):
            ids.append(f"copy{k}-{w.ids[i]}"); text.append(w.text[i]); date.append(int(w.date[i]) + dd)
            iv.append(None); facts.append(w.facts[i]); labelled.append(False); label.append(None)
            page.append(np_); np_ += 1
    return World(w.name + "+copies", w.static_key + "+copies", ids, text, date, iv, facts, w.lexicon,
                 labelled, label, page, dict(w.stats))


def main():
    tr = load_track("P10")
    out = open(os.path.join(RESULTS_DIR, "F1-stress.jsonl"), "a")
    for a in sys.argv[1:]:
        p = json.loads(a)
        res = {s: [] for s in ("clean", "hlie", "hctrl")}
        t0 = time.time()
        for seed, (w, gold, sc) in enumerate(tr.folds):
            fr = sc[gold == "false"]
            rng = np.random.default_rng(12345 + seed)
            trows = rng.choice(sc[gold == "true"], size=len(fr), replace=False)
            for s, src in (("clean", []), ("hlie", fr), ("hctrl", trows)):
                ww = augment(w, src) if len(src) else w
                assert not ww.labelled[w.n:].any() and (ww.labelled[:w.n] == w.labelled).all()
                pr = check_prediction(ww, f1var.Variant(**p).run(ww))
                res[s].append(M.compute(gold, pr.labels[sc], pr.conf[sc]))
        for s, ms in res.items():
            m, sd = M.mean_std(ms)
            rec = dict(worker="F1-stress", variant="F1/f1var.py:Variant", params=p, track=f"P10-{s}", metrics=m,
                       metrics_std=sd, runtime_s=round(time.time() - t0, 1), n_folds=len(ms))
            out.write(json.dumps(rec) + "\n"); out.flush()
            print(json.dumps(p), s, "pts=%.4f acc=%.4f frec=%.3f fprec=%.3f" % (
                m["points_per_row"], m["accuracy"], m["false_recall"], m["false_precision"]), flush=True)


if __name__ == "__main__":
    main()
