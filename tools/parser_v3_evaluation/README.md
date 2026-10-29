# Independent parser V3 challenge

This standard-library Python harness constructs expected ASTs and counterfactual
worlds independently of the Rust parser. It reads only names, aliases and legal
attributes from `data/lexicon.json`; no organizer truth, practice rows, previous
million examples, sealed runs, model weights or production parser code are used.
The cases and oracle were authored with development-time OpenAI Codex assistance
on 2026-10-29. No LLM or network runs in generation, auditing or scoring, and none
of these invented facts is Hooly evidence.

Ownership and delivery are recorded in the
[task handoff](../../docs/handoffs/parser-v3-evaluation.md).

## Scope and artifacts

The development corpus has 512 rows, 32 per family; the fresh reserved final has
2,048 rows, 128 per family. The 16 families cover exact typed values, comparisons,
negated comparisons, multi-entity and multi-clause binding, nested all/any/not,
API versus product versions, object-name distractions, explicit pronoun context,
document resets, genuinely ambiguous ownership, missing/approximate values, raw
decimal precision, units/billing, punctuation, and truth-only metamorphic pairs.
All eight kinds occur, including booleans and names. Fact-reference comparisons
are included separately from typed constant comparisons.

All generated datasets, predictions, reports and test scratch files stay below
ignored `artifacts/`. Bundles refuse overwrite. Earlier development revisions
remain untouched; the handoff identifies the authoritative revision and hashes.
The final uses an OS seed and fresh IDs. Reusing a development seed repeats
constructed wording/values, while IDs remain fresh; exact input reproducibility
uses the preserved bundle and its SHA-256 hashes.

Each bundle contains:

| Path | Consumer |
| --- | --- |
| `public/input.jsonl` | The complete parser input |
| `public/lexicon.json` | Only the public lexicon |
| `public/interface.schema.json` | Static input/output structure |
| `public/POLICY.json` | Context and semantic policies |
| `public/adapter_variants.json` | Required adapter nuisance transformations |
| `private/gold.jsonl` | Evaluator-only AST, status, assertions, diagnostics, world and truth |
| `private/generation.json` | Seed and provenance; evaluator-only for final |
| `manifest.json` | Public-file, gold and factory-source digests |

The reserved final shares the published families and some templates, and adds
reserved clause/operator forms. This is not a claim of fully disjoint grammar or
2,048 independent linguistic constructions. Do not inspect final wording, labels
or the reserved factory branches for parser tuning or selection.

## Adapter interface

The [JSON schema](interface.schema.json) is rooted at input; output is its
`$defs.prediction`. Every public input has only:

```json
{"id":"opaque","document_id":"doc-x","text":"...","context":{"enabled":true,"document_id":"doc-x","prior_texts":["Record subject: Hooly Docs."]}}
```

There are no bound candidate owners, attributes, truth labels, expected forms,
family hints or profile tags. Generate value candidates with the frozen
input-only grammar. Candidate IDs, iteration order and untrusted gold-like fields
must never influence resolution. Public prior texts are eligible only when
`context.enabled` is true and their `context.document_id` equals the current
`document_id`. Start fresh for every independently bounded document. Local
coordination may bind a syntactically shared subject; ambiguous antecedents need
a diagnostic and abstention. No hidden source-ID selection is required.

Return exactly one JSONL object per input ID:

```json
{"id":"opaque","status":"parsed","ast":{"type":"atom","fact":{"subject":"Hooly Docs","attribute":"languages","value":{"kind":"quantity","value":"17","unit":"language"}}},"assertions":[{"subject":"Hooly Docs","attribute":"languages","value":{"kind":"quantity","value":"17","unit":"language"}}],"notes":[]}
```

AST nodes are `atom/fact`, `all/children`, `any/children`, `not/child`, and
`compare/left/op/right` with fact references. Operators are `eq,ne,lt,le,gt,ge`;
fact `value.op` defaults to `eq`. Assertions are the set of atom leaves in
negation normal form. Fact-reference comparisons produce no invented constant
assertions. Numeric strings or exact JSON numbers are accepted. The JSON loader
preserves decimal lexemes; binary-float rounding is not forgiven. Extra spans or
diagnostic fields are ignored.

Status is `parsed`, `partial`, `unresolved` or `ambiguous`. Private expected status
sets accept deliberate ambiguous/unresolved abstention on genuinely ambiguous
English. A missing/ambiguous row has no guessed owner or arbitrary source ID.
Diagnostic categories are `subject`, `ambigu`, `unknown`, `approx`; the scorer
accepts documented descriptive aliases. Diagnostic accuracy is separate from
parse and assertion accuracy.

## Independent truth and metrics

The [oracle](oracle.py) implements exact rational arithmetic and strong Kleene
all/any/not. Currency and billing periods are separate channels. Fixed durations
convert exactly; months/years are a calendar dimension. Version components are
numeric tuples and preserve component count in equality. Date equality preserves
written precision; mixed-precision date ordering is unsupported. Boolean and
name values have no ordering. The [factory](factory.py) constructs ASTs first,
then renders text; it never calls a parser to calculate expected answers.

Counterfactual worlds balance true/false/unsure by formula where attainable.
They remain private and never supply parser evidence. Parsing gold and truth
gold are separate fields; ambiguous/partial text has no invented semantic label.
Scoring reports status, scope-aware AST exactness, assertion-set exactness,
assertion micro precision/recall/F1, subject/attribute resolution, diagnostics,
AST coverage and semantic truth with explicit denominators. Normalization accepts
associativity, commutativity, De Morgan and inverted operators, while preserving
logical scope. Semantic unsure can be guessed by abstention; report AST coverage
and semantic accuracy conditional on an AST alongside it.

Truth-only pairs have identical wording and different hidden worlds; resolution
must remain stable. Adapter variant runs additionally reverse/shuffle candidates,
replace candidate IDs, inject unrelated gold-like fields, and reverse document
processing order. Supply their output paths to the scorer; an absent variant run
is untested, never a passing invariant. The scorer verifies output equality, not
whether an adapter honestly executed its declared transform.

## Commands

Run from the repository root with Python 3.11+; this task used `py -3.14`.

```powershell
py -3.14 -X utf8 -m unittest tools.parser_v3_evaluation.test_evaluation -v
py -3.14 -X utf8 -m tools.parser_v3_evaluation.factory --output artifacts/parser-v3-new/development --split development --seed public-development-seed
py -3.14 -X utf8 -m tools.parser_v3_evaluation.audit --bundle artifacts/parser-v3-new/development --include-gold --report artifacts/parser-v3-new/development/audit.json
py -3.14 -X utf8 -m tools.parser_v3_evaluation.score --bundle artifacts/parser-v3-new/development --predictions artifacts/parser-v3-adapter/dev.jsonl --variant-predictions reverse_candidates=artifacts/parser-v3-adapter/dev-reversed.jsonl --report artifacts/parser-v3-adapter/dev-score.json
```

Generate a fresh final only once; the delivered final already exists at the path
in the handoff. Public auditing never opens final gold. Final scoring requires
the coordinator's explicit freeze and request. A receipt must attest:

| Field | Required content |
| --- | --- |
| `freeze_id` | Stable source/model freeze name |
| `confirmed_by` | `coordinator` |
| `confirmed_at_utc` | Timestamp before all prediction runs |
| `training_and_selection_finished` | `true` |
| `source_commit` | Actual commit and dirty-state description if relevant |
| `source_tree_sha256` | Hash of a complete preserved source snapshot |
| `evaluation_public_sha256` | Array containing the exact final public bundle digest |
| `solver_artifacts` | Actual `{path,sha256,role}` objects, including `solver`, `source_snapshot`, and all separately loaded models |

The source snapshot artifact must hash to `source_tree_sha256`; all listed files
are rehashed. Completeness of listed files is the coordinator's attestation.
The scorer writes exclusive `private/one-shot-evaluation.json` before opening
final gold. Repeat scoring is refused and a crash retains the marker for review.
There is no reset/force flag. Freeze all candidate variants before viewing any
held-out score and submit them together in the one-shot scoring command.

This controlled challenge does not certify unrestricted English, competition
accuracy, calibration, temporal history reconstruction or the private referee.
Human linguistic review is still needed beyond the documented self-review and
hand-authored arithmetic/scope sentinels.
