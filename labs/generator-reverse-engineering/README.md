# Generator reverse-engineering lab (2026-10-28)

Scripts behind [docs/research/generator-reverse-engineering.md](../../docs/research/generator-reverse-engineering.md):
how deterministic the organizers' data generator is, measured on `data/practice.csv` and `data/lexicon.json`.

| File | What it measures |
|---|---|
| `rev_common.py` | Shared loaders: rows, gold forms, pages (runs of consecutive ids sharing a date), keys, unit normalisation |
| `a1_templates.py` | Template inventory: placeholder templates, Good-Turing unseen-template rate, slot signatures (`templates.txt`) |
| `a2_lies.py` | Lie signature: how each false value relates to the true values of its key (`a2_details.json` per row) |
| `a3_unsure.py`, `a3b_voice.py` | Unsure rows: text features, temporal rule, first-person voice and id-block priors |
| `a4_pages.py` | Page structure: sizes, clustering of false and unsure rows, subject antecedents, id and date order |
| `a5_keys.py`, `a5b_conflicts.py`, `a5c_timeline.py` | Key density, value changes over time, the per-key timeline rule and its density curve |
| `a6_claims.py` | Mapping practice rows onto the five claim types |
| `hyp.py` | Hypotheses from other teams' public notes: multiples, stale values, stable keys, social pages, joke tails |

Run any script with `python -I <script>` from this directory using an environment that has numpy and scikit-learn
(the scripts import `/tmp/veridyct-emb/common/harness.py` and `/tmp/veridyct-emb/w7/values.py` by absolute path;
copy `labs/embedding-experiments/common/harness.py` and `labs/embedding-experiments/w7/values.py` there, or edit the
paths at the top of `rev_common.py`). Each `*_out.txt` is the output the report quotes.
