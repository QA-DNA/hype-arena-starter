# Independent evaluation builder

- Task: `task_baa4bd794b9c`, dispatch `ctx_95fd3ba1147a`.
- Status: builder ready; sealed model evaluation awaits coordinator freeze/request.
- Human owner: unassigned. Agent role: independent evaluation builder.
- Branch: `teodorbalan/evidence-independent-eval`.
- Checkout: `C:\Users\Teodor\orca\workspaces\QA-DNA-JEV\evidence-independent-eval`.
- Base: `d0af1691d49887870eb6dd638cf439afb7e7182d`.
- Authorized paths: `tools/independent_evaluation/` and this handoff; generated
  datasets/reports only under ignored `artifacts/`.
- No production/organizer changes, commit, push or deployment.

## Delivered behavior

[Oracle](../../tools/independent_evaluation/oracle.py),
[bounded value grammar](../../tools/independent_evaluation/grammar.py),
[factory](../../tools/independent_evaluation/factory.py),
[public-evidence audit](../../tools/independent_evaluation/audit.py),
[CSV label scorer](../../tools/independent_evaluation/score.py), and
[development claim scorer](../../tools/independent_evaluation/claims.py) are
independent Python standard-library implementations with no production imports.
Usage, freeze receipt fields and scope limits are in
[the tool README](../../tools/independent_evaluation/README.md).

Acceptance delivered: eight kinds; six input operators; exact rational numbers;
three-valued, false-dominating conjunctions; complete inclusive interval anchors
and explicit unknown gaps; conversions; date precision; unpadded versions;
separate currencies/periods; public within-row pronouns; numeric distractors;
fresh development/final worlds; independent semantic tests; target-only metrics
and separate confidence metrics. The coordinator subsequently authorized the
development generated-claim semantic scorer for all five output types.

The primary solver receives **only `universe.csv` and `lexicon.json`**. Actual
antecedent declarations are inside CSV text. `context.json` records boundaries for
diagnostics and contains no hidden subject pointer. Neither page publication time
nor the order of pages establishes a validity interval.

## Current artifacts and exact fingerprints

All current bundles are under this checkout's ignored
`artifacts/independent-evaluation-v3/`. Counts below are targets, plus 1,897 public
anchors per bundle. Public CSV columns are exactly `id,text,date,label`.

| Split | Targets | Public CSV SHA-256 |
| --- | ---: | --- |
| `development` | 1,000 | `30ffa0c503804499885826ea51f0872c9f4cc310d4f16644325ff27bf59f925a` |
| `sealed-5000` | 5,000 | `06707b59d6f7e53b115a83d06f8bf8e7313b121a1958f7e553354266c5a282ea` |
| `sealed-20000` | 20,000 | `24b78993494fa476e98dd4ec36980397252047485b9d6e53d63d088735ef2db6` |

| Split | Public bundle digest |
| --- | --- |
| `development` | `4e2cc89368cd701099f34df9ba9b852f93a36a6bcc76f4d5dde8dfab1c78a35a` |
| `sealed-5000` | `e9d9bef6abe4c9e3ed83a9679663538f3c0183608fca7c5e810b908b0f8de791` |
| `sealed-20000` | `dadc329184da500dee06f6253b8c368ad6c1277bcc2ac3bbb575d7efdaea9469` |

The public path is `<split>/public/universe.csv`, with adjacent `lexicon.json`.
`public/manifest.json` explains the digest of the four public artifact hashes.
Only development's `private/gold.jsonl` is released for development use. Sealed
gold, worlds and seeds stay private and must not be copied into root/model work.
Generated artifacts must be transferred explicitly; they are intentionally not
part of Git or a source-only integration.

Each bundle has 96 channels, 1,440 unique intervals (768 known, 672 unknown), and
457 consistent repeated anchors. Every declared interval is available in public
text. Known and unknown intervals cover 2024-01-01 through 2027-12-31 completely.
Money offers have three independent currency/period channels per selected
attribute. Values and duration partitions differ between freshly seeded worlds.

## Provenance and independence

Targeted `rg --files -uu -g bench.py` searches found no earlier factory in
`C:\Users\Teodor\orca\QA-DNA-JEV` or known worktrees under
`C:\Users\Teodor\orca\workspaces\QA-DNA-JEV`. No broader personal-data search was
performed. Archive filename metadata contained no `bench.py`; only the public
`evaluation-data/GUIDE.md` was read from the Downloads v3 archive. No existing
archive sealed/calibration gold or private data was read.

The earlier guide explicitly used zero-padded versions and interval-based partial
dates. This oracle follows the public as-written version distinction and exact
written date precision. Ordered partial-date cases use equal precision. The
five official value operators are retained; `ne` is a documented input extension,
never an output claimed-value operator. No former synthetic/official factual
value was imported.

Code/design used development-time OpenAI Codex assistance. Facts are generated
from private random seeds, not the model's background knowledge. The public
lexicon supplies names/aliases/legal attributes only. No synthetic fact becomes
official Hooly evidence. Source hashes and source snapshots accompany generated
bundles; the development-only claim scorer subsequently refined mixed-precision
ordering reporting without changing any input/gold file.

## Sampler audit and retirement

Before final scoring, an independent source audit found two prototype shortcuts:
the primary-slot cycle aligned modulo 96 with modulo-3 labels, and distractors
were added at a modulo-3 index. No sealed score or prediction file was opened.
The original artifacts remain byte-for-byte unchanged under v1/v2; retirement
markers identify them as historical development diagnostics, not final tests.

Revision 3 pairs every primary slot and nuisance draw with all three labels,
includes all arities for all classes, and independently randomizes interval
durations instead of using common seasonal boundaries. Development contingency
audits report **0.334 category-majority accuracy** for each of primary fact,
style, context, distractor and arity, with no category missing a class. These
checks address identified shortcuts; they do not certify arbitrary prose or
eliminate all synthetic distribution bias. No solver-output-driven wording or
unknown-interval weakening was performed.

## Verification

- `py -3.11 -m unittest tools.independent_evaluation.test_independent_evaluation
  tools.independent_evaluation.test_claims -q`: **44 tests passed**; hand-specified rational/operator tables, version
  precision, temporal endpoints, money channels, context bounds, false dominance,
  unsupported grammar, CSV metrics, freeze gate/one-shot lock, all five generated
  claim semantics, and sampler shortcut regressions.
- Public-anchor reconstruction recomputed all 1,000 current development labels
  from public evidence, without private world lookup. The result is
  `development/evidence-audit.json`.
- Both current sealed `evidence-audit.json` reports are public-only and record
  `gold_opened=false`. There has been **no current sealed solver score**.
- Development has 198 public pronoun contexts and three repeated target texts;
  sealed public-only audits found 906/3,924 contexts and 21/101 repeated texts.
  Repeated text can have different validity dates. Input target length is not the
  300-character generated-claim limit.
- `cargo xtask test`: 23 foundation tests passed through the existing WSL Rust
  1.90.0 toolchain. Format/Clippy passed on the first `cargo xtask check`, after
  which Git failed on the checkout's Windows `.git` pointer in WSL. The final
  **`cargo xtask check` passed**, including 126 local links, 15 graph nodes,
  14 relationships and organizer snapshot checks, with process-local `GIT_DIR`,
  `GIT_COMMON_DIR` and `GIT_WORK_TREE` paths. No Git metadata or global configuration
  was changed.
- A development-only CSV harness copied released development labels intentionally
  to verify scorer plumbing: 1,000 target rows, exact expected perfect join,
  coverage 0.667 and confidence Brier 0 for 667 definitive rows. This is **not a
  solver/model accuracy result**. Its three claim fixtures independently yielded
  one true, one false, one invalid and 997 missing claims, as expected; reports are
  under `development/harness/` with explicit fixture provenance.

The WSL command form is:

```text
wsl -d Ubuntu-ASC --cd /mnt/c/Users/Teodor/orca/workspaces/QA-DNA-JEV/evidence-independent-eval --exec env GIT_DIR=/mnt/c/Users/Teodor/orca/QA-DNA-JEV/.git/worktrees/evidence-independent-eval GIT_COMMON_DIR=/mnt/c/Users/Teodor/orca/QA-DNA-JEV/.git GIT_WORK_TREE=/mnt/c/Users/Teodor/orca/workspaces/QA-DNA-JEV/evidence-independent-eval /home/teodor/.cargo/bin/cargo xtask check
```

## Limits and next action

This is a bounded counterfactual language/world evaluation, not open-domain
English, official Hooly reconstruction or a private-referee pass. Human semantic
review is pending. The generated-claim scorer separates structural validity,
lexicon validity, novelty, bounded exact-fact text grammar and world truth. Other
text templates remain unsupported by its text checker. Compare forms can be
ambiguous across simultaneous money channels; partial event dates, out-of-scope
dates and mixed-precision ordering remain unsupported rather than invented truth.

The builder is ready for integration by copying only the owned source paths.
Continue solver improvements against **development only**, freeze the complete
source/model/binary artifacts and both final public digests, then explicitly
request one-shot scoring. The label scorer rejects a missing freeze receipt and
creates an exclusive attempt marker before opening sealed gold. Use the same
frozen artifacts for both final worlds; do not tune after the first result.

Generated-claim evaluator revision
`independent-claims-2-mixed-date-unsupported` corrects the earlier reporting of
mixed-precision date orderings as invalid semantics. Such legal forms are outside
this oracle's declared ordering coverage and now return unsupported. A dedicated
hand-authored test covers that status and precision-preserving equality. No
previous true/false comparison, existing input/gold artifact, or historical v1
report was changed. The revision is emitted in new claim reports; prior reports
retain their original interpretation and must not be silently overwritten.
