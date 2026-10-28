# Context, versions and assertion extraction: improvement plan

Status: proposed work, not implemented. 28 October 2026.

**Recommendation:** keep the typed objects, lexicon normalization and CSV adapters,
but replace the fragment-first splitter with an extractor that resolves grammatical
roles and nearby discourse before emitting assertions. Preserve version, time,
population and condition wording with each assertion. Treat extraction and deciding
whether the assertion is true as separate stages.

The user's correction is right: preceding rows contain essential information. The
earlier [manual review](MANUAL-REVIEW-2026-10-28.md) correctly rejected blind subject
copying, but its row-local framing was too restrictive as a direction for development.
Nearby context should be a planned part of the extractor, not merely an optional
future feature. It will recover some omissions; it cannot establish every missing
subject or turn a claim into evidence of its own truth.

## What the data establishes

These examples were read directly from [practice.csv](../../data/practice.csv), with
their forms used to inspect the intended interpretation. They are development cases,
not independent test results. Canonical names and available attributes were checked
against [lexicon.json](../../data/lexicon.json).

| Practice evidence | Consequence for the design |
| --- | --- |
| `p-1`–`p-4`: Holdan joins Hooly, leads Cloud reliability, and previously worked at Nimbus Cloud; then “He begins with a small crew of 4 engineers.” | Resolve `He` to Holdan. The last entity in `p-3` is Gemini, so last-entity copying fails. Track people, products and grammatical roles separately. |
| `p-5`–`p-7`: Cloud's launch/regions, then “Its paid accounts” and “The platform”. | Resolve the product topic to Cloud even when the paragraph also mentions Holdan. Retain the person topic for later “His” in `p-10`. |
| `p-79`–`p-84`: Photos and its Lite/Plus/Max tiers, then “Paying for a year saves 17%”. | The form assigns the discount to Photos, not the immediately preceding Photos Max. Keep parent-product and plan topics distinct; recency alone is insufficient. Without a reliable attachment, retain alternatives. |
| `p-20`: “The Hooly Jules beta opens today, 14 April 2026.” `p-27`: general availability from 2 June 2026. | Beta opening and general availability are different attributes. The comma before an explicit date is not an assertion boundary. |
| `p-120`, dated 2 July: Android 17 beta has 480,000 testers. `p-122`, same date: stable release is still due on 8 September. Both are labelled true. | Testers can exist before a stable release. A future scheduled release is not the assertion that release has already occurred. |
| `p-1331`, 20 April: Jules has 500 initial testers; `p-22`, 20 September: Jules has 9,000 users. | Beta testers and users are distinct populations/attributes. Do not add the counts or substitute one for the other. |
| `p-135`, 12 January: Pixel Watch has reached 120,000 watches since launch. `p-147`, 1 April: it has sold 260,000 watches. Both are true. | Cumulative sales do occur. These are successive totals, not increments: the later total is 260,000, not 380,000. |
| `p-90`, 19 October 2025: Photos has 58 million monthly users; `p-95`, 2 April 2026: 64 million users each month. | Monthly active populations are snapshots/windows, not cumulative registrations. Do not add them. |
| `p-1398`: “Hooly Gemini 2.2 went live this week” with a 100 MB upload limit. | Emit the explicit `version` assertion and upload-limit assertion; preserve release context. Do not confuse a version release with the original product `launched` date. |
| `p-58`–`p-61`: Chrome 69.0, its release date, and a stable release every four weeks. | `stable_version`, `stable_release_date` and `release_cadence` are separate. Likewise Cloud's CLI version is not necessarily its service or API version. |
| Gemini versions appear under subject `Hooly Gemini`; Android 16 and Android 17 are separate lexicon subjects. | Follow the lexicon first. Do not universally strip version-like suffixes or universally create version-specific subjects. |
| `p-22` is dated September 2026; `p-23` is dated December 2025. | Input sequence and chronology are different orders. Keep sequence for discourse and dates for temporal reasoning. |
| `p-841`–`p-845`: “Growth: 64.3% then 37.7%”, “Growth now 41.1%”, then “Ads: 78%, 72%, 66%, 61%”. | Nearby text supports a series interpretation but does not explicitly provide all four quarter names or their mapping. Context does not automatically solve this list. Preserve an ordered unresolved group unless stronger evidence establishes its columns. |

The [contract](../../contracts/README.md) defines `date` as the source page date and
runtime columns as `id,text,date,label`. It supplies no page identifier or explicit
promise that runtime rows preserve document order. We should use the adjacency seen
in practice, while recording that a context block is inferred. A shared date alone
does not prove a shared page; numeric ID continuity is not a semantic rule.

## Reading the six-row Gemini example

| Example row | What can be extracted | What cannot be concluded from this alone |
| --- | --- | --- |
| 1. Gemini v1 is out. | Gemini, version v1, a release assertion. | That the claim is true, or its exact event date without temporal evidence. |
| 2. It has 1,000 users. | The pronoun naturally refers to the Gemini/v1 topic from row 1. Preserve whether v1 scope is inherited or merely a candidate. | It is not automatically false: row 1 already says v1 is out. |
| 3. Gemini v2 has 1,000 users. | Explicit v2 context and a claimed count of 1,000. | Being before row 4 in the CSV does not establish a pre-release date. Even a pre-release count could describe beta users. |
| 4. Gemini v2 is out. | Explicit v2 release assertion; update linguistic focus. | This does not itself prove row 3 false or become an authoritative release record merely by being stated. |
| 5. Gemini v2 has 2,000 users. | Another v2 count, with its own date and source. | Truth depends on evidence. At different dates it could reflect growth; at the same effective time and scope it could conflict with row 3. |
| 6. Gemini has 3,000 users. | A product-level or unspecified-version count. | It does not automatically mean v2, nor 1,000 v1 users plus 2,000 v2 users. The populations could overlap or refer to different windows. |

There is also a schema detail: this lexicon does not give Gemini a `users` attribute.
The example is useful for design, but the real implementation must not invent that
key. Jules users, Android beta testers and Chrome monthly active users supply actual
count cases for this dataset.

Keep four different count interpretations: cumulative total, current population,
windowed activity, and explicit increment/decrement. A future value layer may combine
counts only when units, entity/version, population, time window and disjointness support
the operation. Do not infer monotonic growth for all counts. Even subtracting two
totals gives a change only when their definitions are comparable; it does not identify
unique newly acquired users or gross sales if churn/returns are involved.

## Proposed pipeline

### 1. Compile the lexicon and interpretation metadata

Continue using the shared Rust core and a compiled, fingerprinted lexicon index.
Keep canonical names, aliases, allowed attributes and exact source alignment.
Match the longest canonical entity before considering a numeric suffix as a version.

Add reviewed metadata for entity kinds and product/plan relationships, attribute
families, predicate patterns and expected unit families. Record where each hint comes
from. The lexicon's attribute names alone do not establish authoritative types,
temporal policies or entity relationships. Never derive these from real-world Google
facts. Compile a fresh index when the supplied runtime lexicon changes; unknown/new
attributes remain usable as candidates rather than being mapped to an old key.

Normalization first produces unambiguous replacements and ambiguous mention
candidates. Later context can select a candidate without rewriting the original text
or running a second text-to-text parsing pipeline. “Photos” used as counted objects
in `p-302` should not generate product-ambiguity errors; a product use of “Android”
such as `p-1239` should be resolvable from local predicates and surrounding mentions.

### 2. Build sentence structure before splitting

Recognize entity spans, predicate spans and lightweight value *shapes*: money with a
billing period, percentages, quantities with units, dates and versions. This provides
attachment clues without requiring the full typed-value/truth engine now.

Use supported clause patterns to distinguish subject, object, possessor, apposition,
relative clause and condition. First recover relations such as “Holdan started at
Hooly” and “Cloud's team answers to Holdan”; do not treat every mention as a competing
subject. Attach “where the free tier gives 5 GB” to Drive in `p-44`. Protect date
appositions, decimal/version punctuation and comma-separated numbers before splitting.

Resolve attribute candidates using the predicate and its scope, with unit/type hints
as constraints. Specifically repair the reviewed confusions: cadence versus version
(`p-61`), trade-in credit versus price (`p-156`), extra-seat price versus plan price
(`p-527`), offline-area capacity versus capability (`p-903`), advertising share versus
revenue (`p-1307`), beta testers versus users (`p-1619`), and tab delay versus its
memory-saver condition (`p-1735`). Money or a matching keyword alone cannot decide.

### 3. Resolve nearby discourse with bounded state

Introduce a `DocumentExtractor` around the row extractor. It consumes normalized
rows in input order and keeps a bounded `DiscourseContext`: recent mentions and
their roles, active person, product/plan, event/reporting period, version track and
ordered-list header. These are linguistic topics, not accepted world facts.

Start with a tunable maximum of eight preceding rows, plus compact active-topic
records within the inferred block. Cap retained text and candidates by bytes/counts
as well as rows. Sweep nearby window sizes on development data; eight is a starting
setting, not a property of the dataset. Topic records retain the original antecedent
and dependency chain, so repeatedly resolving “it” does not fabricate fresh evidence.

Prefer explicit in-row subjects, then supported in-row references, then compatible
preceding topics. Score candidates by person/product compatibility, grammatical role,
predicate/attribute compatibility, explicit topic continuity and distance. Keep separate
person and product focus so Holdan and Cloud can remain active together. Avoid assuming
gender from a name; personal pronouns narrow to person candidates but do not establish
an identity. A known topic can be carried even if its preceding sentence failed to
produce a complete assertion.

Date changes, new explicit headings, incompatible topics and detected document breaks
reset or weaken inherited state. Same-date unrelated blocks must also be tested.
Preserve multiple plausible candidates and a reason when the winner is not supported
well enough. Bound dependency depth to prevent one mistaken reference contaminating
an arbitrarily long run. Never backfill a subject from the practice form while testing
text extraction. The first implementation needs previous rows only, not future-row
lookahead or arbitrary retrieval across the CSV.

### 4. Preserve version, time and scope explicitly

An assertion still has a canonical subject and attribute. Add qualifiers rather than
replacing its identity with an ad hoc string such as `Gemini_v2_users`:

- `version_context`: exact spelling, track (product/API/CLI/stable/beta when supported),
  explicit/inherited/ambiguous origin, and source references. Preserve the contract's
  distinction between versions such as `2.3` and `2.3.0`.
- `temporal_context`: page date separately from explicit effective-time wording,
  relative dates, intervals and scheduled/historical/current modality. Do not equate
  “went live this week” with one exact day. Date precision survives later interpretation.
- `population_context`: beta testers, users, paid accounts, monthly active users,
  cumulative sales, or an unresolved description; retain the measurement window.
- `scope`: negation, condition, approximation/bounds, billing option, comparison,
  and links to any shared group or alternative.

When wording explicitly states a version, emit its version assertion as well as any
other supported assertions (`p-1352`, `p-1444`, `p-1488`, `p-1398`). Do not inherit the
latest mentioned version into every later bare product name. Do not overwrite one
version's observations with another's, or mix product/API/CLI tracks. Keep linguistic
version scope separate from a later verified version timeline.

These qualifiers are internal provenance/meaning, not new organizer form fields.
Canonical practice forms often express a changing product-level attribute rather than
a permanent version-specific fact. Preserve both the official pair and the wording's
version context; defer any generalization across versions to the evaluator. Future
claim generation must serialize only contract-supported subjects, attributes and
forms, and decline claims whose essential qualifiers cannot be expressed faithfully.

### 5. Emit individual assertions and preserve unresolved groups

Split shared subjects/predicates only when their mapping is supported. Preserve one
ordered group for an unaligned list, including its shared cue and candidate columns.
Use a preceding explicit list header or “respectively” when available; do not select
columns by matching numbers to remembered true values. False statements must still
be parsed as stated. Keep conditional/alternative assertions linked so a disjunction
does not become two independently required facts.

Account for every claim-bearing span as extracted or unresolved. Distinguish a
supported extra assertion absent from a practice form from an invented assertion
(`p-58`), and a scoped availability statement from numeric zero (`p-1335`). A shorter
fragment containing an unextracted version is not a complete extraction.

## Object, CSV and viewer interfaces

Use a schema-versioned Rust object throughout; CSV serialization happens only at the
boundary. Retain current row and occurrence IDs, canonical fields, original wording,
unresolved reasons and normalization fingerprint. Add:

| Field/group | Purpose |
| --- | --- |
| `input_ordinal`, inferred context block and boundary reason | Reproduce discourse decisions independently of dates or ID spelling. |
| Subject origin and candidate alternatives | Distinguish explicit mentions, in-row references and preceding-row inheritance. |
| Cross-row source references `{row_id, start, end, role}` | Point to both current assertion wording and earlier subject/version/header evidence. Byte offsets always identify their own original row. |
| Version, temporal, population and scope records | Preserve the distinctions described above without forcing full semantic interpretation now. |
| `group_id`, relation, ordered members | Preserve shared lists, alternatives and conditional dependencies. |
| Resolution method, model/rule version and scores | Make decisions reproducible; scores are not automatically calibrated probabilities. |
| Coverage and unresolved claim spans | Expose missing content separately from whether some emitted pairs are correct. |

Simple fields remain separate CSV columns; repeated references/qualifiers can use JSON
cells. Never render a sentence and parse it back. Keep `paired` distinct from verified
truth, and do not silently redefine existing `split` as a completeness guarantee.
Version the persisted schema and document conversion/rejection of older staged files.

`parse` and standalone `split` must share the same ordered stream/context behavior;
splitting one row in isolation explicitly lacks preceding context. Reset context
between files, not between arbitrary processing batches. Carry state across batches
within the same stream, preserving deterministic output and staged/combined parity.
Keep a row-local mode for comparison and missing-context fallback.

The existing viewer should show current wording beside inherited subject/version
evidence, with links to antecedent rows, competing candidates and unresolved groups.
Do not display the earlier row's wording as though it occurred in the current row.
Practice forms remain a separate reference panel.

## Practice precompute versus runtime truth evaluation

Both paths share lexicon compilation and text extraction. Precompute can also import
the supplied practice forms directly through a separate, explicit form adapter. Those
forms supply stated structure; labels determine their evidential role. A false
multi-assertion row does not identify which individual assertions are false.

At runtime, the supplied CSV includes labelled practice rows and unlabelled additional
rows but no forms. Bundled practice forms may be used for validated matching practice
records; check identity/content rather than trusting an arbitrary ID collision. New
rows require text extraction. They do not become true merely because they follow a
true row, repeat an earlier claim, or have a confident parse. Labelled false rows can
still supply linguistic antecedents without supplying trusted factual values.

The downstream KB needs dated observations with provenance, scope and dependencies,
not a map that overwrites `(subject, attribute)` with the last CSV value. It must keep
input order for discourse separately from effective-time ordering for truth, and
avoid counting a query's own assertions or copied context as independent support.
Repeated publication is not necessarily independent corroboration.

At row level, one established false assertion makes the row false. A true verdict
requires sufficient support and coverage for the relevant assertions; unresolved
extraction is not evidence of falsehood. The future evaluator must preserve `unsure`
when the dataset cannot decide. Existing [KB experiments](../kb-experiments/README.md)
consume practice forms even for held-out unlabelled facts: they help study reasoning
but do not measure the deployed text-to-answer pipeline.

## Optional non-LLM machine learning

Start with the structural/context rules and inspect their errors. If subject or
attribute ranking remains the bottleneck, train a small sparse linear classifier to
rank candidates from lexical cues, grammatical patterns, units and discourse features.
For example, scikit-learn documents sparse linear classifiers and logistic regression
through `SGDClassifier(loss="log_loss")`; training can happen in the development lab,
with coefficients and a fixed feature mapping exported for Rust inference.
[Official classifier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.SGDClassifier.html).

If span boundaries remain the bottleneck, test a linear-chain conditional random field
for entity/predicate/value/qualifier tagging. This is a sequence labeller, not a
generative language model; CRFsuite's documentation describes this model family.
It is a reference for the experiment, not a decision to add its C/C++ runtime to our
default Rust graph. Prefer a small safe Rust inference implementation with parity
tests if the experiment earns its inclusion.
[CRFsuite documentation](https://www.chokkan.org/software/crfsuite/).

Neither model supplies Hooly world knowledge. They rank or label spans using supervised
examples; no LLM/SLM, online API, pretrained generative model or retrieval from the
internet is needed in the submitted system. Forms supply weak pair supervision but
not token spans or antecedent links: manually reviewed annotations are needed for
those tasks. Record development-assistance and synthetic-data provenance. Use a fixed
feature budget and bounded candidate sets; include a model only after measured gains
over the rules on a frozen evaluation set. No installation is needed for this planning
task; a later ML experiment can use an isolated Python environment without adding
Python or training dependencies to the competition image.

## Implementation order and acceptance criteria

1. **Establish reference cases and schema.** Convert the 47-row manual review into a
   reviewed regression ledger; add the context/version/count blocks above and negative
   controls. Annotate spans, antecedents, scopes and expected unresolved cases. Freeze
   separate evaluation blocks before new rules/models are tuned. Define the v2 object
   and CSV migration. Acceptance: expectations separate supported wording, reference
   forms and truth labels; no ID-specific extraction rules.
2. **Repair attachment and completeness.** Implement predicate/role patterns, protected
   date spans, version extraction and attribute distinctions before adding broad
   subject carryover. Acceptance: the reviewed wrong-pair cases are corrected or
   explicitly unresolved; date/version wording is not silently dropped; established
   good cases such as `p-5`, `p-493` and `p-1834` retain their meaning.
3. **Add context resolution.** Implement bounded stream state and cross-row provenance.
   Acceptance: Holdan/Cloud examples resolve with traceable antecedents; parent-plan,
   version switches and unrelated-neighbour controls do not get confident wrong
   carryover. Removing necessary context produces uncertainty rather than a guessed
   fact. Long chains stay within explicit limits.
4. **Evaluate and optionally add a statistical ranker/tagger.** Measure subject and
   attribute attachment, qualifier/span retention, completeness, unresolved coverage
   and confident errors separately. Acceptance: compare at matched precision/coverage,
   report actual mistakes and sample sizes, and keep ML only if its benefit survives
   independent review and resource measurements. Do not set a success claim from
   full-practice pair rates alone.
5. **Integrate CSV and viewer, then test downstream effects.** Preserve deterministic
   staged/combined output, show inherited evidence and schema versions, and regenerate
   the practice outputs. Compare the same KB reasoning with oracle forms versus real
   parser output once a solver exists. Acceptance: quantify how extraction changes
   row-level errors; do not substitute the oracle-form experiment for this test.

Use grouped evaluation that keeps nearby discourse, duplicate sentences and close
templates together. In a text-extraction holdout, hide the forms and labels of the
whole held-out block from training, feature derivation and context state. Split before
learning aliases/cues. Existing reviewed examples are development regressions, not
fresh holdout data. Since the team has inspected much of practice, describe remaining
practice tests as prospective development holdouts with that limitation; reserve
new independently collected cases when available.

Run ablations with context off/on, truncated context, same-date unrelated neighbours,
version changes and shuffled blocks/rows. Distinguish loss of legitimate context from
wrong confident borrowing; do not demand that unavailable antecedents be recovered.
Synthetic stress cases test mechanics, not unseen Hooly factual accuracy. ML export
parity, UTF-8/cross-row span validation, bounded-state tests and parser-to-KB comparisons
matter more than tests that merely repeat the implementation's cue table.

## Resource envelope and offline delivery

The [runtime contract](../../contracts/README.md) allows at most 3 GiB unpacked image,
6 GiB memory, two CPUs, 256 processes/threads and 30 minutes for the **whole system**.
The run is offline with read-only root, UID 10001, no home, 128 MB `/tmp`, 256 MB
`/output`, and a maximum 16 MiB final CSV. These limits include the solver and 1,000
generated claims, not only extraction.

Proposed engineering targets below are budgets to verify, not measured performance:

| Component | Initial target |
| --- | --- |
| Final image | At most 1 GiB as an internal target; multi-stage build with Rust executable and versioned data/model artifacts only. |
| Optional extraction model | At most 64 MiB, fixed feature/candidate budgets; reject an oversized artifact. |
| Extraction/context/index working memory | At most 512 MiB; stream rows, cap text retention and candidate growth, and avoid copying full text per assertion internally. |
| Complete application peak memory | Target at most 4 GiB to leave room under 6 GiB; account for tmpfs and all concurrent stages. |
| Extraction on approximately 20,000 representative rows | Target at most five minutes on two CPUs; benchmark actual long and ambiguous inputs as well as ordinary rows. |
| Whole application | Aim to finish within 25 minutes, reserving five minutes before the contractual deadline. |

Keep discourse state updates sequential; use at most two bounded worker threads in
the application rather than introducing unbounded library thread pools. Reconcile
stage budgets with measured KB/claim-generation costs before approving the complete
pipeline. Bake models into the image; no downloads, training cache or implicit home
directory writes at runtime. Debug assertion CSVs are lab outputs, not extra copies
of every row written into the limited competition `/output` filesystem.

Benchmark release builds and then the real offline CPU container, recording commit,
hardware, thread count, input size, elapsed time, peak memory and unpacked image size.
Use `ARENA_DEADLINE` for deadline-aware orchestration and atomic final CSV replacement.
No official-checker success can be claimed until the solver and 1,000 claims exist.

## Decision and handoff

This makes the approach more promising: supported subject–attribute assertions are
the right interface for later algorithms, provided they retain scope and provenance.
A flat pair with detached wording is insufficient. The next milestone is better
attachment plus context-aware extraction, not a larger pile of keyword rules or
automatic truth decisions based on release order. Whether the entire challenge is
solved well remains an end-to-end evaluation question.

- Task: `contextual-extraction-plan`; planning author: Codex; human owner unassigned.
- Snapshot: `51db366322abd98e5bbb735f93b2440b7a5988b0`; organizer files unchanged.
  The local branch is behind six fetched research commits; this task does not merge
  them or claim to validate their latest experimental results.
- Planning checkout: `/tmp/veridyct-contextual-extraction`, branch
  `plan/contextual-extraction`. Existing uncommitted review/README changes preserved.
- Planning changes: this document and its lab README link. This is the forward plan
  following the [original proposal](../../docs/assertion-extraction-plan.md) and
  [implemented baseline decision](DECISION.md); their historical status is unchanged.
- Future implementation paths: `crates/core/src/extraction/`,
  `crates/cli/src/preprocessing.rs`, lab evaluation/fixtures/viewer, and corresponding
  decision/handoff documentation. Use a dedicated implementation branch/worktree.
- Intended interfaces: versioned context-aware extraction objects, stream API and
  CSV adapters; no HTTP dependence in the core and no truth evaluator in this task.
- Planning acceptance: evidence-backed context/version/count distinctions, concrete
  stages and interfaces, evaluation criteria and resource budgets. No parser code,
  generated output, dependency installation, merge or push is part of this change.
