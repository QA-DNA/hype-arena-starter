# 0003: Compiled evidence graph and CPU assertion extraction

Authorized by Teodor on 29 October 2026. Implementation `20b94a3` was merged into
main and pushed; see the [integration handoff](../handoffs/evidence-main-integration.md)
and [measurements and task handoff](../handoffs/evidence-graph-runtime.md).

The runtime has four stages: frozen non-generative CharCNN/BiLSTM ONNX assertion
proposals; schema-guided subject/attribute/value binding; exact evidence queries;
and structured claim templates with deterministic MMR. It contains no runtime LLM
or external API. Development-time LLM assistance and synthetic worlds are recorded
as development provenance, never as official Hooly evidence.

`KnowledgeGraph` indexes labelled true observations, atomic negative constraints,
and false conjunctions by canonical subject and attribute. Every proof retains its
source. Same-day evidence or an explicit inclusive `From DATE through DATE` scope
licenses hard deductions; a publication date does not invent persistence. Compound
false rows license an individual negative only when all other atoms are independently
supported. Unlabelled repetition and model predictions never establish trusted truth.
Conflicting constraints cause abstention. A partial parse cannot prove a conjunction
true, while one reliably refuted conjunct can prove it false.

Decimal values use bounded exact rational arithmetic. Compatible physical units
convert exactly; currency and billing periods, and fixed/calendar durations remain
separate. Version ordering uses numeric components; written equality distinguishes
`2.3` from `2.3.0`. The schema binder uses text and the public lexicon only, without
truth lookup, labels, page dates or gold-resolved subjects. Explicit unknown declarations
remain fact-free. Ordinary prose can retain span-grounded neural proposals.

The canonical practice world's truth is available only when its complete seed is
present in the runtime universe. Independent counterfactual worlds otherwise use
their own labelled evidence. The optional partition-validated boosted verifier supplies
statistical fallback for canonical/practice queries; those scores are uncalibrated.
A source-only counterfactual world without proof returns unsure.

[Dockerfile.competition](../../Dockerfile.competition) builds Rust solver and native
extractor from source and stages hash-pinned CPU model/runtime assets. It defaults
to exact-length batching, avoiding the frozen BiLSTM's measured padding dependence.
Context is disabled: CSV adjacency alone is not a documented document boundary.
Previous-three-text context remains an explicit experimental setting. The default
[Dockerfile](../../Dockerfile) continues to build the smaller Rust core application.
The older [Python prototype](../../Dockerfile.neural) is retained for reproduction.

Generation uses labelled true source assertions, explicit validity windows, typed
comparisons and overlapping event/relation witnesses. Multiple money channels
remain distinct; ambiguous reference-only money comparisons are skipped. Changes
require ordered non-overlapping witnesses, without claiming an exact transition day.
Templates produce the official form and readable text together; MMR selects diverse
candidates. Format compliance is separate from truth and text/form equivalence.

Evaluate extraction, classification, generation, calibration and runtime separately.
Practice partitions and the paired390 parser-development set are development
measurements. Final independent worlds require an explicit source/model freeze and
one-shot scoring; their controlled catalog language does not certify arbitrary English
or the organizer's private referee. Preserve every earlier run and failed result.
