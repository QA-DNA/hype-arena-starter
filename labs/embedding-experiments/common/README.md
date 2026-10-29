# VERIDYCT embedding experiments: shared harness

One module, `/tmp/veridyct-emb/common/harness.py` (stdlib + numpy + scipy + scikit-learn, no torch).
Python: `/tmp/veridyct-bench/.venv/bin/python`. Self-test (about 5 s): `python -I harness.py`.

    import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
    H.set_threads(2)                       # BEFORE importing torch; then torch.set_num_threads(2) yourself
    rows, lex = H.load(); sf = H.single_fact_rows(rows)       # 1897 rows, 291 pages, 1467 single-fact
    fa = H.page_folds(sf)                  # folds are positions in the list you pass; X rows must follow that list
    m, pred = H.run_probe_attr(X_sf, sf, lex, fa)             # X_sf: (1467, d) embeddings of [r['text'] for r in sf]
    H.ResultWriter(H.results_path('w3')).add('w3', 'bge-small', 'attr_probe', 'C=10', m, n=len(sf))

## Rules
- Write ONLY under `/tmp/veridyct-emb/<worker>/` and `/tmp/veridyct-emb/results/<worker>.jsonl`. Never edit `common/`
  or `/Users/mogaeduard/VERIDYCT`. Need a change in the harness? Say so in your report, do not fork it.
- Use these functions for every number you report, with the default folds, so results stay comparable.
- Probes, kNN and retrieval L2-normalise X themselves. All `run_*` return `(metrics, per_row_output)`.
- Folds: `page_folds(sf)` for attribute tasks, `page_folds(rows)` for truth tasks, `attribute_folds(sf)` for attr_unseen.
  The two page splits differ (GroupKFold sees different row counts); to fuse stages, derive sf folds from the all-row folds.

## Result JSONL (one object per line, `ResultWriter.add`)
`{"ts": ISO-UTC, "worker", "model", "task", "variant", "n", "notes", "metrics": {...}, ...extra}`
NaN/inf become null, numpy becomes plain python. Put the metrics dict the harness returned into `metrics` unchanged and
extra facts (dims, secs, C, k) in `**extra` or `notes`. A task name outside the list below only warns; fix it.

## Task names
`attr_probe` `attr_knn` `attr_zeroshot` `attr_hybrid` `attr_unseen` `key_retrieval` `truth_false` `truth_three`
`nli_anchor` `nli_conflict` `nli_attr` `speed`, plus prefixes `finetune_*` `fusion_*` `values_*`.

## Functions
- Setup: `set_threads(n=2)`, `load()`, `pages(rows)`, `single_fact_rows(rows)`, `results_path(worker)`
- Facts: `key(fact)`, `value_equal(v1, v2)`, `attr_words(a)`, `describe(subject, attribute)`, `candidates(lex, subject)`
- Folds: `page_folds(rows, n_splits=5)`, `attribute_folds(rows, n_splits=5)` (single-fact rows), `train_counts(rows_sf, folds)`
- Anchors (keyed by `idx`): `anchors(rows)`, `nearest_anchors(rows, k=2)`, `same_key_pairs(rows, max_per_key=50, seed=0)`
- Attributes: `run_probe_attr(X, rows_sf, lex, folds, C=10.0)`, `run_knn_attr(X, rows_sf, lex, folds, k=5)`,
  `zeroshot_attr(sim_matrix_fn, rows_sf, lex, desc_fn=describe)`; `sim_matrix_fn(descs: list[str])` returns cosine sims of shape
  `(len(rows_sf), len(descs))`, the `descs` being the 514 lexicon pairs in lexicon order
- Truth: `run_probe_false(X, rows, folds, C=1.0)` -> `(binary_metrics, scores)`, `run_probe_three(X, rows, folds, C=1.0)` -> `(three_class_metrics, proba)`
- Retrieval: `key_retrieval(X, rows, k=10)` -> recall_at_k, hit_at_k, mrr (+ `tfidf_*` reference), n_queries
- Metrics: `attr_metrics(y_true, y_pred, train_counts)`, `binary_metrics(y01, scores)`, `three_class_metrics(y_true, proba)`, `ece(y01, p)`
- Reference and cost: `tfidf_baseline(rows)`, `encode_speed(encode_fn, texts, bs=32)` -> sentences_per_s, est_sec_20k_x86

## Semantics that bite
- Attribute label = attribute string (321 classes); candidates = the GOLD subject's lexicon attributes (fallback: unrestricted).
  `acc_unseen` = rows whose attribute has 0 training rows in the fold. A probe or kNN scores 0 there by construction;
  `zeroshot_attr` has no training, so its `acc_unseen == acc_all`. Under `attribute_folds` every row is unseen.
- kNN applies the restriction to the neighbour pool (only the gold subject's attributes vote).
- `anchors`: TRUE rows on other pages sharing a (subject, attribute) key; `days = other.date - row.date`; same-day anchors
  exist (361) and count as "before" in `nearest_anchors`. `same_value` is exact gold-value equality (4 == 4.0 only).
- `run_probe_false/three` use class_weight='balanced' and RAW softmax (no isotonic), so brier/ece reflect that skew.
- `three_class_metrics.arena`: +1 right, -1 wrong, 0 abstain (max(p_true,p_false) < t) or unsure truth, over all n rows;
  `arena_always_true` = (n_true - n_false)/n = 0.687 is the bar to beat.
- `key_retrieval.recall_at_k` = share of the same-key rows found in the top k; it cannot reach 1 when a key has more than k rows.
- `est_sec_20k_x86 = 20000 / sentences_per_s * 2.0` (midpoint of the 1.5x-3x x86 slowdown); texts are encoded longest first.

## Sanity references (printed by the self-test, fold noise about 0.01)
TF-IDF + LinearSVC attribute: acc_all 0.873, acc_ge5 0.961, acc_unseen 0.000 (n 1467/673/718/76); TF-IDF + LR false-vs-rest AUC 0.633.
Beat these or say why not.
