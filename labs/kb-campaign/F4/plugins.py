"""F4 feature plugins for other families and the combination phase. Each ref is a run.py / api.feature_block spec
(paths relative to $KBC, the working directory of run.py on the Mac and on the box). Every plugin takes
(world, role=None) and returns (world.n_facts x k); anchor facts get leave-fold-out values (5 page folds), so the
same column means the same thing on labelled (training) and unlabelled (test) facts."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

PLUGINS = {
    "prop_feats_t10": {"ref": "F4/f4graph.py:prop_feats_t10", "k": 7, "desc": "prop_feats with a 10-day time kernel"},
    "prop_p": {"ref": "F4/f4graph.py:prop_p", "k": 1,
               "desc": "propagated P(fact true): signed label spreading over same-claim / contradicts edges "
                       "(time kernel tau 30, future x0.5), mapped by a 1-D logistic fit on anchors"},
    "prop_feats": {"ref": "F4/f4graph.py:prop_feats", "k": 7,
                   "desc": "spread score, clamped propagation score, PPR log-ratio and log-mass from true/false anchors, "
                           "log support and contradiction degree, propagated P(fact true)"},
    "page_lie": {"ref": "F4/f4graph.py:page_lie", "k": 3,
                 "desc": "page latent-lie EM posterior from the OTHER rows of the page (soft evidence only), "
                         "expected page false rate, log lift over the base false rate"},
    "page_lie_lab": {"ref": "F4/f4graph.py:page_lie_lab", "k": 3,
                     "desc": "page_lie observing the labels of labelled page neighbours (train/test mismatch; comparison only)"},
    "blame_feats": {"ref": "F4/f4graph.py:blame_feats", "k": 4,
                    "desc": "P(fact false), blame share q/sum q in the row, noisy-OR P(fact false | row false), "
                            "max P(false) of the other facts of the row"},
    "all_feats": {"ref": "F4/f4graph.py:all_feats", "k": 14, "desc": "prop_feats + page_lie + blame_feats"},
    "lex_features": {"ref": "F4/f4lex.py:lex_features", "k": 27,
                     "desc": "label-free lexicon classes: value kind one-hot, aliases, subject type (org/event/person/venue/"
                             "other), event date offset, subject birth offset, relation links, key volatility"},
    "lex_small": {"ref": "F4/f4lex.py:lex_small", "k": 19, "desc": "lex_features without the value-kind one-hot"},
}

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness"))
    os.chdir(os.path.dirname(HERE))
    import numpy as np
    from api import feature_block
    from world import load_track
    w = load_track("P10").folds[0][0]
    for name, p in PLUGINS.items():
        X = feature_block(w, p["ref"])
        assert X.shape == (w.n_facts, p["k"]) and np.isfinite(X).all(), (name, X.shape)
    print("plugins ok:", ", ".join(PLUGINS))
