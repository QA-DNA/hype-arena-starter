# Evidence evaluation harness

Task `task_2b8200e2ed41`; agent owner: evaluation worker; human owner unassigned.
Checkout: `evidence-evaluation`, branch `teodorbalan/evidence-evaluation`.
Base: `d0af1691d49887870eb6dd638cf439afb7e7182d`.
Scope: [Rust example](../../crates/core/examples/evaluate_splits.rs),
[PowerShell wrapper](../../tools/evaluate-splits.ps1), and this handoff.
The worker did not edit engine/model/forest/Docker or organizer files and did not
commit, push, publish or deploy. Integration owns engine selection and installation.
See the [CPU evidence decision](../decisions/0002-evidence-mvp.md).

## Reproduce

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/evaluate-splits.ps1
# Explicit Docker, separate target cache, offline cached registry:
powershell -NoProfile -ExecutionPolicy Bypass -File tools/evaluate-splits.ps1 -Docker -Output artifacts/evaluation-splits/report.json
# External gold labels, optional form column:
powershell -NoProfile -ExecutionPolicy Bypass -File tools/evaluate-splits.ps1 -External C:/evaluation/gold.csv
# A verified parser-held-out set; automatically reports text-only and hybrid:
powershell -NoProfile -ExecutionPolicy Bypass -File tools/evaluate-splits.ps1 -TestIds C:/evaluation/test-ids.json -Predictions C:/evaluation/predictions.jsonl
```

Native equivalent: `cargo run --locked --release -p veridyct-core --example
evaluate_splits -- --practice data/practice.csv --lexicon data/lexicon.json
--assignments analysis/practice/outputs/split_assignments.csv --output
artifacts/evaluation-splits/report.json`. These are one command when entered in a
shell. `--splits` selects comma-separated named splits; `--help` documents options.
Path options also accept `VERIDYCT_EVAL_PRACTICE`, `_LEXICON`, `_ASSIGNMENTS`,
`_OUTPUT`, `_EXTERNAL`, `_TEST_IDS`, `_PREDICTIONS`; set `VERIDYCT_EVAL_COMMIT`
when invoking Rust directly. The wrapper records commit, dirty state, SHA-256 of
inputs/core sources/harness/manifests, compiler, Docker image and resource limits
in `<output>.metadata.json`. Direct Rust reports include byte counts and FNV-1a64
input fingerprints. The default direct Rust output is JSON on stdout; progress
uses stderr. Source and test ordering follow the input CSV, irrespective of
assignment-file ordering. Output cannot overwrite an input file.

Docker defaults: existing `veridyct:dev`, 2 CPUs, 6 GiB, no network, release mode,
one compute thread, repository mounted read-only. The default target volume has
a checkout-path hash, separate from other workers; `-TargetVolume` overrides it.
`-RegistryVolume` defaults to the already cached `veridyct-mvp-registry` and
`--offline` fails if dependencies are absent. This is a development image run,
not a submission-container compliance check.

## Evaluation boundary

Each partition constructs a new Engine using only cleaned training rows. Every
training row whose normalized text matches any test text is removed, regardless
of date or label; matching IDs are removed too. Normalization mirrors the engine:
NFKC, lowercase, sharp-s/final-sigma folds and whitespace collapse, retaining
punctuation. All requested partitions must assign every practice ID once to
train or test; duplicates, omissions, unknown IDs and invalid partitions fail.

Test inputs are constructed using only ID/text/date. Gold labels and forms stay
in the reporting/scoring layer. Both `predict` and `extract` receive empty labels
and gold-free forms. Predictions must have no known label, preserve row order,
and cite only cleaned training IDs. A regression test changes test gold labels
and a unique secret fact and verifies that predictions/extraction do not change;
an uppercase duplicate in training is excluded.

External CSV uses `id,text,date,label` and optional `form` (JSON fact array).
Every row needs a true/false/unsure gold label. A separate external report trains
on full practice after exclusion; external rows never train the model. Blank or
missing forms are unannotated, while explicit `[]` is an annotated empty set.
The two-row external smoke fixture is drawn from practice and tests plumbing;
its accuracy is not independent validation.

Classification reports gold-row/prediction-column confusion in true/false/unsure
order, accuracy, all-class macro-F1, per-class support/precision/recall/F1 and a
majority baseline selected from cleaned training labels only. Undefined class
metrics are zero, with stable true/false/unsure majority ties. Tuple extraction
compares exact typed `(subject, attribute, value JSON)` sets, ignoring tuple order
and duplicates; no fuzzy or numeric-equivalence adjustment is applied. Reports
include row exact accuracy, pooled micro precision/recall/F1, row macro-F1 and
TP/FP/FN counts. Empty/empty row F1 is one. Per-row gold, predictions, extractions,
evidence and counts remain available in JSON to audit every aggregate.

`--test-ids` replaces the five splits with a custom holdout, using a JSON ID
array or one ID per line. `--predictions` is rejected without explicit test IDs:
a frozen parser trained on 1,507 practice rows must not be used on arbitrary
Mihai splits. Its JSONL schema is `id,prediction:[{atom:Fact,...}]`; direct Fact
entries are also accepted. Every selected ID must occur exactly once, although
unselected synthetic rows may coexist. Only the prediction field is read; gold
label/form fields in a sidecar are ignored. Selecting IDs does not itself verify
a parser's training provenance; callers must verify its held-out manifest.

The coordinator explicitly authorized the separate neural-plus-template mode:
only frozen model-predicted tuples enter test `InputRow.form`, labels remain
blank, and no test rows enter Engine construction. Empty predicted forms invoke
the engine's existing template fallback, so hybrid extraction and raw parser
metrics are reported separately. The paired text-only and hybrid runs use the
same cleaned training IDs and gold test references.

## Original engine baseline: all five partitions

Measured 2026-10-28 UTC, Rust/Cargo 1.90.0, Linux amd64, AMD Ryzen 9 6900HS,
Docker 2 CPUs/6 GiB, one compute thread, release profile. Original engine SHA-256
`817c89d80903149038f09c6d30fbf2511a44aad47d0e747b2e5fa2161dc227d9`.

| Split | Clean train | Test | Removed text duplicates | Accuracy | Macro-F1 | Majority accuracy | Tuple exact | Tuple micro-F1 | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| random | 1415 | 475 | 7 | 0.766316 | 0.335035 | 0.833684 | 0.124211 | 0.201313 | 1.844 |
| bundle_group | 1422 | 475 | 0 | 0.747368 | 0.327227 | 0.831579 | 0.063158 | 0.118100 | 2.006 |
| template_group | 1422 | 475 | 0 | 0.785263 | 0.330401 | 0.831579 | 0.149474 | 0.225513 | 1.847 |
| forward_time | 1306 | 583 | 8 | 0.708405 | 0.279526 | 0.825043 | 0.120069 | 0.193035 | 1.867 |
| every_fifth | 1513 | 380 | 4 | 0.802632 | 0.334635 | 0.852632 | 0.157895 | 0.227778 | 2.079 |

All majority labels were true. Majority macro-F1 respectively: 0.303100,
0.302682, 0.302682, 0.301378, 0.306818. Total measured harness time was 9.765 s;
process peak RSS 45,980 KiB. Stage timing includes train/predict/separate extract;
per-split elapsed additionally includes filtering and scoring. Compilation is
excluded from these figures and recorded separately by the wrapper.

Confusion rows, with columns true/false/unsure:

| Split | Gold true | Gold false | Gold unsure |
| --- | --- | --- | --- |
| random | 360,4,32 | 59,2,8 | 8,0,2 |
| bundle_group | 351,4,40 | 58,2,10 | 8,0,2 |
| template_group | 370,5,20 | 61,2,7 | 8,1,1 |
| forward_time | 413,0,68 | 83,0,11 | 8,0,0 |
| every_fifth | 302,3,19 | 42,3,4 | 7,0,0 |

Per-class precision/recall (true; false; unsure), in the same split order:

| Split | True P/R | False P/R | Unsure P/R |
| --- | --- | --- | --- |
| random | 0.843091 / 0.909091 | 0.333333 / 0.028986 | 0.047619 / 0.200000 |
| bundle_group | 0.841727 / 0.888608 | 0.333333 / 0.028571 | 0.038462 / 0.200000 |
| template_group | 0.842825 / 0.936709 | 0.250000 / 0.028571 | 0.035714 / 0.100000 |
| forward_time | 0.819444 / 0.858628 | 0 / 0 | 0 / 0 |
| every_fifth | 0.860399 / 0.932099 | 0.500000 / 0.061224 | 0 / 0 |

Accuracy is below majority for every split. False/unsure recall and extraction
coverage are material weaknesses. These are practice-derived diagnostics that
have informed tuning; they are not independent final accuracy or calibration.

## Frozen parser development set and integration comparison

The frozen sidecar has 390 official practice IDs plus 8,088 synthetic predictions.
The evaluation selects only the 390 official IDs, leaving exactly 1,507 training
rows and zero additional duplicate-text exclusions. Sidecar SHA-256 matches its
frozen manifest: `bdc6d08a52a33232d745034896310b46d951647823e1eba444d3151c3f88aedb`.
The parser metadata identifies these as its previously tuned grouped development
set, not a sealed final test. The parser's original practice CSV byte hash differs
from this worktree's serialization, but all 1,897 parsed CSV records compare equal.

Raw parser extraction: exact 336/390 = 0.861538; micro precision 0.956140,
recall 0.891616, F1 0.922751; TP 436, FP 20, FN 53. Thirty parser outputs are empty.
After engine template fallback, extraction exact is 339/390 = 0.869231 and
micro-F1 0.925184. Those figures must not be conflated with verdict accuracy.

Final integration v5 was measured from a consistent copied source snapshot;
engine SHA-256 `565e5bd5f14c6b5dfc72d753caac3b34f6fe143cb590d0b7b013b0a107fb2241`.
The source manifest also fingerprints knowledge/forest and other core files.

| Engine | Mode | Verdict accuracy | Macro-F1 | Elapsed seconds |
| --- | --- | ---: | ---: | ---: |
| Original | Text only | 0.741026 | 0.313905 | 1.633 |
| Original | Neural plus template | 0.746154 | 0.338953 | 1.906 |
| v4, unselected | Text only | 0.746154 | 0.331434 | 2.750 |
| v4, unselected | Neural plus template | 0.784615 | 0.384641 | 3.374 |
| v5, final | Text only | 0.802564 | 0.321825 | 2.563 |
| v5, final | Neural plus template | 0.802564 | 0.343248 | 2.586 |

Majority is 312/390 = 0.800000 accuracy, macro-F1 0.296296. Final v5 is
313/390, only one correct row above majority. Removing the lexical abstention
threshold improves accuracy over v4 while reducing macro-F1; v3 was also
unselected after lowering accuracy. No fresh final-test or calibrated-probability
claim follows from these tuning runs.

Final hybrid confusion is `[[307,5,0],[68,6,0],[4,0,0]]`. True precision/recall:
0.810026/0.983974; false: 0.545455/0.081081; unsure: 0/0. The system predicts no
unsure rows in this particular set, so minority recognition remains weak despite
the accuracy gain. The final paired run took 5.282 s total with 39,768 KiB process
peak RSS, excluding compilation and including both separately trained modes.

Final v5 text-only results on all five Mihai partitions, from the same snapshot:

| Split | Verdict accuracy | Macro-F1 | Majority accuracy | Elapsed seconds |
| --- | ---: | ---: | ---: | ---: |
| random | 0.833684 | 0.337452 | 0.833684 | 2.352 |
| bundle_group | 0.829474 | 0.328372 | 0.831579 | 2.374 |
| template_group | 0.829474 | 0.335659 | 0.831579 | 2.274 |
| forward_time | 0.826758 | 0.308680 | 0.825043 | 2.168 |
| every_fifth | 0.857895 | 0.365951 | 0.852632 | 2.613 |

Clean training/test counts, duplicate exclusions and extraction metrics are the
same as the original five-split table. Total elapsed was 11.869 s and process peak
RSS 48,696 KiB. Full confusion, per-class precision/recall/F1, tuple counts and
source references for every final split are in `graph-v5-five.json`.

## Verification and artifacts

The original five-split baseline was repeated: every prediction, evidence entry
and extraction was identical. Independent Python recomputation checked source
gold, assignment membership, normalized text/ID disjointness, evidence provenance,
confusion, accuracy, per-class metrics, majority and tuple metrics. A final audit
passed across 16 split reports, covering the baseline five, final five and paired
390-row original/v4/v5 reports, including raw parser scores. External CSV smoke
passed with two exact text exclusions and only the one annotated form scored.

Six example tests pass, covering strict assignment validation, typed set metrics,
gold isolation/duplicate exclusion and selected parser sidecar completeness.
`cargo xtask test` passes 23 workspace tests; example tests require the explicit
`cargo test --locked -p veridyct-core --example evaluate_splits` command.
`cargo xtask check` passes format, all-target Clippy with warnings denied, 120
local documentation links, graph and organizer hashes. Docker needs the host common Git directory mounted
read-only with `GIT_DIR=/git/worktrees/evidence-evaluation` and
`GIT_WORK_TREE=/workspace` for xtask documentation checks; Windows worktree `.git`
paths are otherwise invalid inside Linux. No organizer checker is claimed here.

Ignored artifacts under the evaluation checkout:

- `artifacts/evaluation-splits-baseline/report.json`, `reproduced.json`,
  `reproduced.json.metadata.json`, `audit.json`: original five-split evidence.
- `artifacts/parser390/test-ids.json`, `baseline.json` and its metadata: original
  engine's paired parser-development comparison.
- `artifacts/parser390/graph-v5-five.json`, `graph-v5.json` and
  their metadata plus `graph-v5-source-sha256.json` and `final-audit.json`: final
  integration snapshot reports, source provenance and independently checked metrics.
- `artifacts/graph-v5-source-snapshot/`: immutable copied source used for the
  integration measurements, with the current example overlaid only in the copy.
- `artifacts/parser390/graph.json` and `graph-v4.json`: earlier tuning experiments,
  retained as unselected historical measurements.
- `artifacts/evaluation-fixtures/external-report.json`: external CSV plumbing smoke.

Artifacts are intentionally outside Git. The coordinator must copy these when
retaining run evidence; source changes remain uncommitted in the three owned paths.
