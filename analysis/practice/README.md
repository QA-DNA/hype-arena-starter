# Practice CSV analysis

Open [practice_analysis.ipynb](practice_analysis.ipynb) in Jupyter or VS Code, or read
[practice_analysis.html](practice_analysis.html) in a browser. Both include executed
results and figures. This analysis is separate from the lexicon notebook; it reads
the lexicon only for reference validation and coverage measurements.

The notebook covers data integrity, label imbalance, sentence complexity, typed
assertions, operators and units, subject/attribute coverage, temporal observations,
duplicates and templates, implicit subjects, lexical associations, evidence gaps,
five evaluation splits, diagnostic classifiers, errors and confidence, candidate
claim inventories, and a prioritized practice-data/testing backlog.

Run from the repository root with Python 3.11 or newer:

```bash
python -m venv .venv-practice
.venv-practice/bin/python -m pip install -r analysis/practice/requirements.txt
.venv-practice/bin/python -m ipykernel install --prefix .venv-practice --name python3
.venv-practice/bin/python analysis/practice/run_analysis.py
```

Alternatively, select a Python environment with these dependencies and use **Run
All** in the notebook. The notebook locates the repository from its working
directory. The runner executes it and refreshes the HTML export. Jupyter needs
permission to open local kernel sockets; no network requests are made by the
analysis. The first verified run used Python 3.14 and took about 30 seconds;
runtime depends on the machine. Exact package versions and input SHA-256 hashes
are recorded in [outputs/manifest.json](outputs/manifest.json).

Outputs are regenerated under `outputs/`. Useful starting points:

| Artifact | Purpose |
| --- | --- |
| [headline_findings.json](outputs/headline_findings.json) | Machine-readable findings |
| [assertions.csv](outputs/assertions.csv) | Exploded assertions with original row IDs and parent-row labels |
| [fact_coverage.csv](outputs/fact_coverage.csv) | Coverage of every lexicon subject/attribute pair |
| [all_unsure_rows.csv](outputs/all_unsure_rows.csv) | Every unsure row and independent matching observations |
| [same_day_value_review.csv](outputs/same_day_value_review.csv) | Multiple exact true values observed for one key/date, requiring interpretation |
| [near_duplicate_label_review.csv](outputs/near_duplicate_label_review.csv) | Similar sentences with different labels |
| [split_leakage.csv](outputs/split_leakage.csv) | Shared text, templates, facts, and assertions across holdouts |
| [split_assignments.csv](outputs/split_assignments.csv) | Reproducible train/test row IDs |
| [baseline_metrics.csv](outputs/baseline_metrics.csv) | Majority and text-model results across five holdouts |
| [high_confidence_errors.csv](outputs/high_confidence_errors.csv) | Concrete errors to investigate |
| [claim_candidate_inventory.csv](outputs/claim_candidate_inventory.csv) | Building blocks for claim generation, before validity proof |
| [practice_generation_test_backlog.csv](outputs/practice_generation_test_backlog.csv) | Prioritized cases, oracle requirements, and evaluation rules |

All source files remain unchanged. A false multi-assertion row does not make every
assertion false. Page dates do not establish validity intervals. The runtime input
has no `form` column, so diagnostic baselines use training text only. Candidate
claims and latest observations are not certified current truths. The notebook's
review tables and final discussion explain these limits in detail.
