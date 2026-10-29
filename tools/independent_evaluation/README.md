# Independent temporal-world evaluation

Python 3.11+ standard-library tools, independent of production Rust, models,
organizer truth labels and the earlier evaluation factory. Names/aliases and
legal attributes come only from the fixed public lexicon. All factual values are
counterfactual inventions. Development used OpenAI Codex LLM assistance; no LLM
runs in the evaluator and no synthetic fact is official Hooly evidence.

The current authoritative artifacts are in ignored
`artifacts/independent-evaluation-v3/`. The task record and exact delivered hashes
are in [the handoff](../../docs/handoffs/independent-evaluation.md). No production,
organizer dataset, checker or contract file was changed.

## Inputs and isolation

| Split | True public anchors | Blank-label targets | Intended use |
| --- | ---: | ---: | --- |
| development | 1,897 | 1,000 | Open development; gold released |
| sealed-5000 | 1,897 | 5,000 | Fresh world, frozen evaluation only |
| sealed-20000 | 1,897 | 20,000 | Another fresh world, frozen evaluation only |

The solver receives only `public/universe.csv` (`id,text,date,label`) and
`public/lexicon.json`. `context.json`, `POLICY.md` and `manifest.json` are public
documentation/audit artifacts; the primary solver never needs them. Pronouns
have an explicit `Record subject: NAME.` declaration within the same CSV row.
Recorded Unicode code-point spans and document groups describe actual public
text, with no hidden resolved-subject table or cross-row lookup.

Every world has 96 channels, 768 known intervals and 672 explicitly unknown
intervals, fully published in anchors. The remaining 457 anchors repeat intervals
consistently. `From DATE through DATE` is inclusive. Page publication dates are
independent of validity; neither later publication nor a newer page implies a
value change or fills a gap. The scope is 2024-01-01 through 2027-12-31.

Development has 12 wording families. Sealed sets add 12 reserved families and
standard date comparison phrases. Preserve all world boundaries; use only
development for training, tuning, selection or calibration. Sealed public data,
reserved wording and private gold are evaluation-only.

`private/gold.jsonl`, `private/world.json` (including the seed), and metadata are
evaluator-only. Fresh seeds come from the OS and are never printed for sealed
worlds. Generation refuses to overwrite existing bundles or to accept a supplied
sealed seed. Source snapshots and hashes record the code used for generation.

## Semantics and limits

The [public contracts](../../contracts/README.md) constrain the schema, not the
invented factual values. Numeric truth uses `Decimal`/`Fraction` without binary
floating-point comparison. All eight kinds are included. Compatible SI units and
fixed durations convert exactly; months/years form a separate calendar dimension.
Money currency and billing period are independent channels, with no FX, annual
total inference or once-only/monthly conflation.

The six input operators are `eq,ne,lt,le,gt,ge`. `ne` is a documented input-language
extension; the official output claimed-value schema does not allow it. Names and
booleans use equality/inequality only. Date equality retains written precision;
ordered date input cases use equal precision. Versions use numeric component
tuples with their component count retained: `2.3 != 2.3.0`, `2.10 > 2.9`.

Conjunctions are false if any component is false, otherwise unsure if any component
is explicitly unknown, otherwise true. Only published world gaps produce unsure
input gold. Invalid/unsupported grammar or undeclared world channels raise errors;
failure to parse a known fact does not change its gold to unsure.

This is a controlled register/catalog language and an independently implemented
world oracle. It does not certify unrestricted English, reconstruct official Hooly
truth, or implement the organizer's private referee. Histories are independently
generated; corporate accounting, stable event histories, people-role realism and
other cross-fact constraints are not generally enforced. Human semantic review is
pending. A large row count is not that many independent facts or sources.

## Commands

Run from the repository root. On other platforms, replace `py -3.11` with a Python
3.11+ interpreter.

```powershell
py -3.11 -X utf8 -m unittest tools.independent_evaluation.test_independent_evaluation tools.independent_evaluation.test_claims tools.independent_evaluation.test_coverage -v

# Generate a NEW set; existing destinations are never overwritten.
py -3.11 -m tools.independent_evaluation.factory --output artifacts/independent-evaluation-new --split all

py -3.11 -m tools.independent_evaluation.audit --bundle artifacts/independent-evaluation-v3/development --report artifacts/independent-evaluation-v3/development/audit-rerun.json
py -3.11 -m tools.independent_evaluation.score --bundle artifacts/independent-evaluation-v3/development --predictions artifacts/my-run/output.csv --report artifacts/my-run/label-score.json
py -3.11 -m tools.independent_evaluation.claims --bundle artifacts/independent-evaluation-v3/development --predictions artifacts/my-run/output.csv --report artifacts/my-run/claim-score.json
```

The audit reconstructs a world from public anchor text. For development it also
recomputes every gold label from that reconstructed public evidence, verifies
actual context bounds and reports nuisance/class associations. For sealed data
the audit is strictly public-only and does not open gold or private world files.

The label scorer counts blank input labels only, uses the first prediction for
each target, ignores claim rows and non-target IDs, and treats missing/invalid
target labels as unsure with explicit diagnostics. It reports target accuracy,
three-class macro-F1, per-class metrics, confusion, coverage and answered accuracy.
These are research metrics, not a claimed official competition score.

`confidence_brier_correctness` is the mean squared difference between reported
confidence and whether the selected label is correct, on definitive predictions
with valid confidence. Missing/invalid confidences and the denominator are explicit.
A separate binary label Brier is restricted to answered true/false gold. Neither
is a multiclass Brier over absent probabilities, and abstentions do not receive an
invented confidence. Accuracy and confidence calibration remain separate.

## Freeze and one-shot sealed scoring

The coordinator must explicitly confirm source/model freeze and request scoring.
Do not use a sealed dataset as an iterative development score. Freeze the same
solver/model artifacts for both final worlds and run both before inspecting either
score. A JSON freeze receipt must contain:

| Field | Required value |
| --- | --- |
| `freeze_id` | Stable identifier for this source/model freeze |
| `confirmed_by` | `coordinator` |
| `confirmed_at_utc` | ISO timestamp with UTC/offset, before predictions were produced |
| `training_and_selection_finished` | `true` |
| `source_commit` | Actual base/revision, including dirty-state description if needed |
| `source_tree_sha256` | SHA-256 of the complete frozen source snapshot |
| `evaluation_public_sha256` | Array containing both exact final public bundle digests |
| `solver_artifacts` | Array of actual `{path,sha256,role}` objects; at least one role `solver`, plus separately loaded models |

The receipt is an explicit coordinator attestation of source completeness; the
scorer verifies the listed artifact hashes and public input hashes. It cannot
discover unlisted external model files on its own. A missing/invalid receipt is
rejected before gold is opened.

```powershell
# Only after the coordinator's real freeze confirmation AND scoring request.
py -3.11 -m tools.independent_evaluation.score --bundle artifacts/independent-evaluation-v3/sealed-5000 --predictions artifacts/frozen-run-5000/output.csv --freeze-receipt artifacts/frozen/freeze.json --report artifacts/frozen-run-5000/score.json
```

An exclusive `private/one-shot-evaluation.json` marker is written before gold
access. A second attempt is refused; a crash leaves its marker for coordinator
review. There is deliberately no force/reset flag. Sealed claim scoring is not
exposed by the development-only claims command.

## Generated-claim score

The first 1,000 claim rows are judged; missing, excess, structurally invalid,
lexicon-invalid, not-new, text-unsupported, world-unsupported, false and unsure
claims are separate fields. Structural checks explicitly cover the official entry
fields/value subset without installing dependencies; they are not a private
referee pass. World truth is evaluated independently of text certification.

Facts and comparisons use 2026-10-29. Changes require a strictly earlier `from`
witness and later `to` witness in validity time. At-event claims use the event's
full date value at the fixed as-of snapshot, then query the target on that event
day; partial/out-of-scope dates are unsupported. Relations require overlap between
the subject's link naming the target and the target's attribute holding the value.
Unknown intervals can hide a witness and produce unsure; absence of a known
witness alone is not enough for false when such a gap exists.

Legal facts outside the 96 declared channels are unsupported. Compare forms that
cannot select among simultaneous currency/period channels and mixed-precision
date orderings are unsupported, not false/invalid. Different money channels are
not silently treated as historical changes. Text certification covers a small
exact-fact subset plus necessary name/relation-word checks; other wording is
reported unsupported even when its structured world truth is known.

New claim reports emit revision
`independent-claims-3-unit-aliases-bounded-facts`. Exact physical spellings from
the public value contract (including `inch` / `inches` / `in`, metre/meter words,
data-unit spellings, mass, frequency and power words) resolve to existing rational
dimensions. Case-sensitive symbols retain their case; binary-byte and unsupported
unit spellings are not inferred. The canonical factor table and factory sampling
vocabulary are unchanged.

The bounded fact grammar also reads `SUBJECT ATTRIBUTE is VALUE.` with the
published attribute's exact words, ISO-code prefix money such as
`EUR 12.50 per month`, and literal boolean `not` as no. It still requires a whole
isolated value and the named subject; comparisons, approximations, added dates,
other sentences and other templates are not certified by this extension. A valid
text match never overrides an independently false or unsupported world verdict.
Revision 2's mixed-precision date-ordering policy remains unchanged: those
comparisons are unsupported, not false or invalid. Historical reports and all
input/gold bytes remain unchanged.

### Reproduce the development coverage comparison

The coverage command consumes a preserved development report and the exact
prediction CSV. It reconstructs truth only from public anchors and never opens
gold or private worlds. It refuses sealed data, changes to an existing supported
world verdict, and output-directory reuse. Its output is confined to the
evaluator's ignored `.cache` directory so the original reports survive.

```powershell
py -3.11 -X utf8 -m tools.independent_evaluation.coverage_audit --bundle artifacts/independent-evaluation-v3/development --predictions artifacts/universe-20261029-031946/output/output.csv --baseline-report artifacts/universe-20261029-031946/claims-score.json --output-directory tools/independent_evaluation/.cache/coverage-audit/revision3
```

The fresh directory contains a byte-for-byte `before.json`, `after.json`, and
`coverage.json` with every changed row's ID, text, original form, both reasons,
source hashes and input/report hashes. On the released development run, world
truth changes from 949 to 951 true, 32 to 30 unsupported, with all 16 false and
3 unsure claims preserved. Text support changes from 0 to 82; 80 claims pass the
combined bounded checks. A separate audit of the newer released
`universe-20261029-033259` output changes 998 true / 2 unsupported to 1,000 true,
with 83 fact texts supported and certified; it preserves zero false, unsure and
invalid claims. Use a fresh `--output-directory` for every comparison. The exact
evidence, row lists and limitations for both runs are in
[the coverage handoff](../../docs/handoffs/evaluator-coverage.md).

## Sampling audit and retired prototypes

The first prototype aligned a modulo-96 primary-slot cycle with modulo-3 labels,
and included distractors at a modulo-3 index. That allowed slot/distractor class
shortcuts. A preflight replacement corrected only the first issue. Those files
remain unchanged under v1/v2 with retirement markers and must not be final tests.
No sealed score was opened before retirement.

Revision 3 pairs each primary slot and independent nuisance draw with all three
labels before shuffling, includes all arities for all classes, and randomizes
interval duration partitions across timelines. Regression tests and development
contingency/shortcut diagnostics verify those specific shortcuts are absent. This
does not prove removal of every possible synthetic-language bias.
