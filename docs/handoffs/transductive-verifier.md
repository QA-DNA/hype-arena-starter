# Transductive verification research

- Status: done; negative recommendation for runtime integration.
- Task: `task_92f35c9f1e18`, dispatch `ctx_9aa4bc00d5c4`, 2026-10-29 UTC.
- Human owner: unassigned. Agent owner: transductive verification research.
- Branch/checkout: `teodorbalan/evidence-transductive`, `evidence-transductive`.
- Base commit: `d0af1691d49887870eb6dd638cf439afb7e7182d`.
- Scope: `tools/transductive_verifier/`, the new core example, and this handoff.
- Acceptance: fresh clean five-split comparisons, actual inferred assertions,
  statistical-only features, self/duplicate/family exclusion, unknown/conflict and
  repetition tests, order invariance, reproducible source hashes and error analysis.
- Core engine, model, knowledge, boosted and organizer files were not edited.
  No other checkout was modified. No commit, push, deployment or publication occurred.

## Result

Do not add these features to the default verifier. Global consistency yields only
two additional correct row appearances across the overlapping five splits, with
unchanged total false correctness, lower mean macro-F1 and worse mean log loss.
Temporal consistency improves some false decisions but causes more true errors;
it still predicts no unsure rows. This does not establish a useful generalization
gain or justify a more expensive GNN.

All results below use the same frozen current integration core and the existing
fixed GBT configuration. The selected neural extractor and its practice training
overlaps are excluded completely. The separately reported neural 390 diagnostic
is a different extraction/training protocol and was not run here.

| Mihai split | Clean train | Test | Baseline correct | + global correct | + temporal correct | Statistics only correct |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| random | 1,415 | 475 | 403 | 403 | 399 | 398 |
| bundle_group | 1,422 | 475 | 396 | 397 | 398 | 398 |
| template_group | 1,422 | 475 | 394 | 396 | 398 | 394 |
| forward_time | 1,306 | 583 | 478 | 478 | 468 | 479 |
| every_fifth | 1,513 | 380 | 329 | 328 | 330 | 328 |

| Unweighted mean over splits | Baseline | + global | + temporal | Statistics only |
| --- | ---: | ---: | ---: | ---: |
| Accuracy | 83.9453% | 84.0190% | 83.7391% | 83.8007% |
| Macro-F1 | 0.35406 | 0.35363 | 0.36675 | 0.36599 |
| Log loss | 0.48470 | 0.48780 | 0.49485 | 0.49264 |

The five splits share rows and development history. Their mean is descriptive;
row appearances are not independent samples. No final sealed-world evaluation
or independent confidence calibration is claimed. Test gold was used only after
feature extraction and classifier fitting, to score the fixed comparisons.

False correctness for baseline / global / temporal:

| Split | Gold false | Baseline | + global | + temporal |
| --- | ---: | ---: | ---: | ---: |
| random | 69 | 11 | 11 | 9 |
| bundle_group | 70 | 5 | 5 | 6 |
| template_group | 70 | 7 | 8 | 10 |
| forward_time | 94 | 1 | 1 | 9 |
| every_fifth | 49 | 5 | 4 | 6 |

Every model has zero unsure recall. Forward-time temporal features correct eight
previously wrong false rows and break eighteen previously correct true rows.

## Delivered change and boundaries

[The Rust example](../../crates/core/examples/transductive_features.rs) exports
baseline and statistical features and performs portable Rust scoring.
[The cluster module](../../tools/transductive_verifier/cluster.rs) returns only a
feature map; it creates no evidence, accepted facts, generation candidates or new
core interfaces. The [evidence MVP decision](../decisions/0002-evidence-mvp.md)
remains unchanged.

The corpus is a text/date-only view of all 1,897 allowed public practice rows.
Every corpus label and supplied form is cleared before Rust receives it. Only
fresh `Engine::extract` results become assertion nodes. The engine and accepted
labelled `FeatureIndex` are separately compiled from each cleaned training pool.
No expected values, gold proof IDs, world IDs, gold template IDs, target forms or
hidden source gold enter features. No evaluation archive, calibration gold or
sealed gold was opened.

Each typed subject/attribute/dimension cluster removes the query ID, its whole
normalized-text duplicate group and its inferred delexicalized template family.
Other families contribute at most one unit of mass, and repeated typed values
inside a family collapse to one vote. Compounds receive a `1 / sqrt(atom_count)`
weight. Multiple competing values divide their family's mass. Public lexical
aliases, inferred string values, numeric tokens and month tokens define exact
delexicalized families. Arbitrary paraphrase equivalence remains unsolved.

Numeric-equivalent values share a canonical bin by exact mutual core entailment;
no f64 conversion decides identity. Adjacent large integers, different currencies,
units, periods and exact version spellings stay separate. A first implementation
used raw JSON value spelling for bins, splitting values such as `12` and `12.0`.
That run remains in ignored `artifacts/transductive-verifier-raw-json/` for audit.
The tables above use the corrected implementation; all baseline trees are
identical across the correction, as the verification script checks.

Features include family mass, support/contradiction/incomparability, ambiguity,
entropy, dominant value share, missingness, nearest compatible observations and a
soft consistency score. Windows cover all dates, the same day, +/-30 and +/-180
days, prior/future 365 days and 90-day exponential decay. Future text contributes
only statistical context. These dates never establish accepted temporal
continuity or exact change boundaries. Output records explicitly mark
`statistical_estimates_only: true`.

For supervised feature fitting, five deterministic text-hash folds exclude each
query's whole fold and duplicate texts from both the extractor and labelled
evidence. Each fold parses the entire unlabelled corpus afresh. The GBT trains on
the combined fold features; outer test extraction uses the complete cleaned
training partition. This avoids exact-text template memory for fit queries. Its
80%-sized fold contexts still differ from full outer contexts, equally for all
paired ablations, so the baseline is specific to this protocol.

Each model uses 120 GBT iterations, depth 2, minimum leaf 20, learning rate 0.045,
seed 417, no subsampling and no class balancing. Baseline excludes lexical hash
and cue features, matching the existing selected feature ablation. Global adds
39 aggregated features; all statistical features add 289. Configurations were
fixed in advance; outer results did not select parameters, thresholds or a winner.
No Random Forest prior restoration is applied to GBT scores.

## Coverage and actual errors

| Split | Empty inferred forms | Eligible independent-family vote rows | Literal JSON exact forms | Exact after numeric spelling normalization |
| --- | ---: | ---: | ---: | ---: |
| random | 240 / 475 | 233 / 475 | 59 / 475 | 167 / 475 |
| bundle_group | 312 / 475 | 160 / 475 | 30 / 475 | 95 / 475 |
| template_group | 238 / 475 | 235 / 475 | 71 / 475 | 166 / 475 |
| forward_time | 349 / 583 | 232 / 583 | 70 / 583 | 168 / 583 |
| every_fifth | 181 / 380 | 198 / 380 | 60 / 380 | 146 / 380 |

Literal JSON comparison counts `12` versus `12.0` as different. The second metric
normalizes only numeric spelling while retaining dimensions and version strings.
Missing clauses and wrong subjects still produce substantial real parser errors.

Concrete public practice cases in `error-analysis.json`:

- `p-770`, random: "151,000,000 users monthly" is about Hooly Translate but
  extracts Hooly Chrome. Cluster contradiction moves the true row from true to
  false. Additional agreement cannot repair a wrong subject link.
- `p-1092`, template-group: the extractor retains Hooly Jules's beta date but
  drops its supported-IDE clause. The retained atom gets unanimous global
  support from seven eligible families; the false compound stays predicted true.
- `p-1042`, random: the false Hooly Photos Plus EUR 5.99/month price has a correct
  parse and approximately 80.8% capped global support from ten eligible families.
  The statistics-only model predicts true; accepted labelled features retain false.
- `p-34`, forward-time: Hooly Docs's true 8,800-user assertion is numerically
  parsed correctly. All four eligible global families disagree, and the temporal
  model regresses from true to false. Majority disagreement is not falsity.
- `p-253`, random: the correctly extracted false "Gemini speaks 12 languages"
  changes from baseline false to temporal true. Even correct query extraction
  does not make broad unlabelled consistency reliable.

## Verification and reproduction

See [the research README](../../tools/transductive_verifier/README.md) for setup
and the detailed input policy. Main commands, run from this checkout:

```powershell
py -3.14 tools/transductive_verifier/run.py --integration ../evidence-graph-runtime
py -3.14 tools/transductive_verifier/verify.py
py -3.14 tools/transductive_verifier/analyze.py
```

The delivered measurement used `--reuse-core` for both runs so the root's changing
checkout could not change the frozen core. Artifacts stay under ignored
`artifacts/transductive-verifier/`. The runner records exact Cargo commands and
outputs in `logs/`; the snapshot adapts only workspace membership and its derived
lockfile. It copies current manifests/core for research commands, without editing
the checkout's old engine or the integration checkout.

Passed checks:

- `cargo test --offline --release --manifest-path artifacts/transductive-verifier/snapshot/Cargo.toml -p veridyct-core --example transductive_features`:
  seven tests covering self/normalized duplicates/family exclusion, exact and
  varying-surface correlated repetition, ambiguity, date/dimension separation,
  empty parses, hidden-label guards, numeric equivalence above 2^53, and versions.
- `cargo clippy --offline --locked --release --manifest-path artifacts/transductive-verifier/snapshot/Cargo.toml -p veridyct-core --example transductive_features --no-deps -- -D warnings`:
  passes against the frozen snapshot.
- `rustfmt --edition 2024 --check crates/core/examples/transductive_features.rs tools/transductive_verifier/cluster.rs`:
  passes. Python scripts compile successfully.
- All 9,466 fit/test query appearances have exactly equal cluster features after
  deterministic corpus shuffling. Query label/form and duplicate-text input guards
  are exercised, including actual rejected processes with exit 2 and no output.
- All twenty exported models load through `BoostedVerifier::from_json`, validate
  exact training IDs/texts/dates/labels and match scikit-learn verdicts. Largest
  observed Rust probability difference is `1.1102230246251565e-16`.
- A wrong training partition actually fails before an output file is created.
  Valid model scoring never applies a second RF prior correction.

Foundation xtask and the official competition checker were not rerun: no
foundation/runtime behavior changed, and this research example uses APIs from the
current copied integration core rather than the older core in this checkout.
This is not a submission-container or generation-quality validation.

Environment: release Rust/Cargo 1.90.0, Docker image
`sha256:fd69385ab339602c033529a3b21e751750ad6757f148e3a894e953800fa79210`,
Linux x86_64 on AMD Ryzen 9 6900HS, two-CPU/six-GiB limit, user 0, network disabled,
one Rust compute thread and host library threads capped at two. Task-owned cache
volumes are `veridyct-transductive-registry` and `veridyct-transductive-target`.
Host training used Python 3.14.0, scikit-learn 1.9.1 and NumPy 2.4.4.

Per-split Rust export includes six engines, the complete corpus for each engine,
features and full shuffle checks. It takes 12.32-14.59 seconds, with child peak RSS
35.49-38.76 MiB and cgroup peaks below 41.69 MiB. Host model fitting/export/parity
for twenty models takes 135.11 seconds; host peak RSS was not measured. These are
research timings, excluding compilation, on the frozen source below.

Key SHA256s:

| Artifact/source | SHA256 |
| --- | --- |
| Public practice CSV | `52743befaa0fa38b89b5c802c0f953d242ae027c86839c9c0f05a9e69a86d8e9` |
| Public lexicon | `d0fd5e9bdc6b33ad3ec160001f50e00e7f8bf2b25a92779022f893db7c3d5507` |
| Mihai assignments | `e84baec6fc52372d4e6adaa8771ab58a11ee75191e28343ee299b6f6cc53f8af` |
| Frozen integration engine | `61f88e96a8edd53006cabbe379340070ce8b9a33561e325fae6a4f42f2053ecc` |
| Frozen typed comparisons | `07086bd5a62166b6b951d51312c6ccf3605aea2385f924f79c19cd52c80d3aac` |
| Corrected cluster implementation | `866d0ebdfa685050e3cbb424b65bdf54450ebe1746a54018a334c6b4038e089b` |
| `source-sha256.json` | `47effe217514a75df704e7fbdab824b8cdd64cbd4ad1f790da4fa672563efb12` |
| `report.json` | `39767eaae9b3641c828aaab1de6880d4fb1c9ba92f07dd6c927595d8e8a5e96c` |
| `rust-parity.json` | `f34c1481cf1cfde84cd1fe34f9281f38a8a8a91ea26498edd9791995bd5e690c` |
| `error-analysis.json` | `255a24fdb59c296976e5477c15ad062cebd9c64fca485652ce403ddcdcf9b855` |

The source manifest records every copied source/manifest hash. `verification.json`
adds current research-script hashes, negative guard receipts and frozen-baseline
tree equality. Models retain their partition signatures and feature-input hashes.

## Next action

Retain the harness as a research diagnostic and prioritize extraction completeness
and subject resolution. If the parser changes, freeze a new core and repeat the
same predeclared comparisons; current results do not transfer automatically.
Any future consistency model still needs clean split-specific extraction training,
calibration selected inside training, and separate accepted evidence. No additional
runtime integration is needed for this result. Sealed final worlds remain untouched.
