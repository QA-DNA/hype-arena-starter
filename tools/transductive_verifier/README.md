# Transductive statistical verifier probe

Task `task_92f35c9f1e18`, owner: transductive verification research; human owner
unassigned. This is research code, with no default engine or generation change.
Read the [handoff](../../docs/handoffs/transductive-verifier.md) for measured results
and limits. The [evidence decision](../../docs/decisions/0002-evidence-mvp.md) still
governs accepted evidence and the offline CPU runtime.

The probe adds statistical features from a text-only view of all public practice
rows. Each row's assertions come from a fresh pure-Rust extractor, using only the
cleaned training partition. Test labels and supplied forms never enter extraction
or cluster construction. Gold remains in a scoring sidecar. No archive, sealed
world, calibration gold, frozen neural parser, pretrained verifier, expected value,
world ID, gold proof ID or gold template identifier is read.

Clusters retain subject, attribute, typed value dimensions and observation date.
Numeric-equivalent decimal spellings share a value cluster using the core's exact
mutual entailment; adjacent large integers and distinct version spellings remain
separate. No value identity is rounded through a floating-point conversion.
Every query removes itself, all normalized duplicate texts, and its inferred
delexicalized template family from votes. Other template families contribute at
most one unit of weight, with repeated identical typed values collapsed. Conflicting
values within a family split that family's mass. The lexical family normalizer uses
public aliases, inferred string values, numbers and month tokens; it does not solve
arbitrary paraphrase equivalence. Compound assertions receive reduced weight.

Features describe support, conflict, missingness, entropy, dominant-value share and a
soft consistency gap. They cover all time, the same day, 30/180-day neighborhoods,
prior/future 365-day windows and 90-day exponential decay. These are statistical
compatibility estimates. An observation date does not establish a change boundary,
and agreement never produces an accepted fact or generation evidence.

Supervised training uses five text-hash folds. For every fit query, its entire fold
and normalized duplicates are absent from both the extractor and labelled evidence.
The GBT is then fit fresh on the combined fold features. Outer queries use the full
cleaned training partition. This avoids the extractor's exact-text memory during
feature fitting. The fold evidence pools contain about 80% of outer training,
which creates a documented train/test context-size difference. It affects all
paired ablations equally.

The predeclared ablations are the existing nonlexical verifier features, those
features plus global clusters, those features plus all temporal clusters, and a
statistics-only diagnostic. Every model uses 120 GBT iterations, depth 2, leaf
minimum 20, learning rate 0.045, seed 417 and no class balancing. There is no model
selection on outer outcomes, probability threshold tuning or RF prior restoration.
Probabilities have no independent final calibration.

## Reproduce

Prerequisites: host Python 3.14 with `numpy` and `scikit-learn`, Docker, the existing
`veridyct:dev` image and the integration checkout. The executable harness lives in
[the new Rust example](../../crates/core/examples/transductive_features.rs); the
cluster implementation is [cluster.rs](cluster.rs).

Create this task's private registry cache from the existing cached registry, once:

```powershell
docker run --rm --network none --user 0 -v veridyct-mvp-registry:/source:ro -v veridyct-transductive-registry:/registry veridyct:dev sh -c 'cp -a /source/. /registry/'
py -3.14 tools/transductive_verifier/run.py --integration ../evidence-graph-runtime
py -3.14 tools/transductive_verifier/verify.py
py -3.14 tools/transductive_verifier/analyze.py
```

The runner copies current core sources and manifests to an ignored core-only
snapshot, recording SHA256s. It builds and tests the example against that snapshot;
the older core in this isolated checkout is unchanged. The snapshot's workspace
membership and derived lockfile differ from the original only to isolate core.
All containers use user 0, no network, two CPUs, six GiB and task-owned registry and
target volumes. The runtime recorder captures hardware, wall time, child peak RSS
and cgroup memory peak. Generated source copies, JSONL features, model artifacts,
predictions and logs remain under ignored `artifacts/transductive-verifier/`.

`--reuse-core` retains the frozen core while refreshing owned harness code.
`--skip-stage --skip-build --reuse-features` repeats only model fitting and parity
when the frozen source and staged inputs are unchanged. `--splits` accepts a
comma-separated subset of the five Mihai splits. A feature export checks exact
cluster equality after a deterministic corpus shuffle for every fit/test row.

Rust scoring uses `BoostedVerifier::from_json` and validates training IDs, source
texts, dates and labels before opening an output file. The runner checks exported
tree parity against scikit-learn. `verify.py` also executes real negative cases:
the wrong training partition, a query gold label and a corpus supplied gold form
must exit 2 without creating output. It audits snapshot hashes, cleaned partition
boundaries and all corpus-shuffle checks.

The five practice splits overlap and share development history. Their mean is a
descriptive comparison, not an independent pooled sample or a sealed final score.
Extraction reports distinguish literal JSON tuple equality from equality after
normalizing only numeric decimal spelling; all dimensions and versions are kept.
The separate neural 390 result in other handoffs is not comparable to this
pure-Rust extractor protocol.
