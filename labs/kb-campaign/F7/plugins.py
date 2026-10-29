"""F7 feature plugins (small neural models, CPU only). Refs resolve from the KBC root (cwd of run.py).
Each returns (n_facts x k) and trains on the world's own labelled rows only: page-grouped OOF scores for the
facts of labelled rows, the full model for every other fact. On a transfer track the plugin therefore refits
on the target world's public labels (never gold); on a one-class world it falls back to a model fitted on
practice. Torch threads: F7_THREADS (default 1)."""
PLUGINS = {
    "f7_deepsets": {"ref": "F7/deepsets.py:features", "k": 1,
                    "desc": "DeepSets over the fact's K=64 nearest same-key observations (gap, same/consistent value, "
                            "label one-hot, bracket flags); fact logit, product targets, 3-seed ensemble. Measured in V9-LR: "
                            "P80 0.807 / P10 0.679 vs 0.809 / 0.674 without (neutral)"},
    "f7_deepsets_mil": {"ref": "F7/deepsets.py:features_mil", "k": 1,
                        "desc": "same DeepSets trained end to end on row labels (row = product, uses multi-fact "
                                "false rows). Measured in V9-LR: P10 0.677 (P80 not finished)"},
    "f7_gnn": {"ref": "F7/gnn.py:features", "k": 1,
               "desc": "2-round GNN over facts, rows, pages and (key, value) claims with time-aware fact-fact "
                       "edges, page-level label trick; fact logit. NOT MEASURED (too slow on the loaded box); refit on a "
                       "20k-row world takes over 14 min on 2 threads, do not use in the final system"},
}
