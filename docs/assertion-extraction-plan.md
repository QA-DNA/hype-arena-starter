# Plan for splitting rows into assertions

Status: proposed design only; no extractor or truth evaluator is implemented by this task.

- Task: `assertion-extraction-plan`, 2026-10-28.
- Human owner: unassigned. Planning author: Codex.
- Planning checkout: existing repository, branch `main`, base `14e71a0`.
- Authorized paths: this plan and its link in the documentation index.
- Delivery criteria: define the split, preserve meaning and uncertainty, cover observed
  practice cases, and specify how a future extractor will be evaluated.
- Future implementation belongs in an isolated task branch and checkout, in the Rust core;
  adapters must not contain a second extraction implementation. Exact code paths and
  interfaces remain to be agreed when implementation is requested.

## Scope and governing decision

Produce a list of individual assertions from each row. Each resolved assertion has
one subject, one attribute, and one typed claimed value. Preserve its source and
qualifiers so a later stage can evaluate it. Do not determine truth, retrieve truth
evidence, aggregate verdicts, or generate competition claims in this step.

The [input contract](../contracts/README.md) confirms that one false value makes a
row false. This is a logical rule, not a vote or a ratio of false to true assertions.
For the later evaluator, one true assertion cannot establish the whole row when
others remain unresolved. Extraction must therefore expose missing or ambiguous
content, rather than silently presenting a partial list as complete.

There are two distinct tasks:

1. **Practice form expansion:** parse the existing `form` JSON list and emit one
   record per list element. This is a reliable development reference for the
   annotated assertions, not a text parser.
2. **Runtime text extraction:** infer those records from `text`, `date`, and the
   lexicon. Runtime input has no `form`. Keep the extraction interface independent
   of row labels; a false sentence must still have its stated values extracted.

The output represents what the row claims, including incorrect values. Never
replace a stated value with a more plausible or known true value.

## Evidence from practice

The [practice CSV](../data/practice.csv) contains 1,897 rows and 2,402 annotated
assertions. There are 430 rows with multiple assertions, 68 with multiple subjects,
at most eight assertions per row, and at most four subjects per row. These are
observed maxima, not limits to impose on the extractor.

| Case | Example | Required split |
| --- | --- | --- |
| One subject, multiple attributes | `p-5`: Cloud has been open since November 2025 and covers 3 regions | `Hooly Cloud / launched / 2025-11`; `Hooly Cloud / regions / 3 region` |
| Multiple subjects and attributes | `p-1834`: prices, seats and SLAs for three plans | Eight assertions across the three plans |
| Same attribute, multiple subjects | `p-843`: `Ads: 78%, 72%, 66%, 61%` | Four quarterly-results subjects; names cannot be recovered from this text alone |
| Same subject and attribute repeated | `p-808`: Pro is €59 per month, or €590 per month if the yearly plan renews | Preserve both annotated `price` assertions; do not correct the second period or overwrite the first value |
| Subject omitted | `p-4`: `He begins with a small crew of 4 engineers, and he is hiring.` | `Holdan / team_size / 4 engineer` in the reference; text extraction needs subject resolution |
| Inequality | `p-7`: the platform serves over 100 customers | Preserve `gt 100`, not equality to 100 |
| Multiple billing options | `p-493`: Jules is €19 a month, or €190 a year, after a 14-day trial | Monthly price, annual price, and trial duration are separate assertions |
| Negation | `p-43`: Docs does not work offline yet | `Hooly Docs / offline_editing / false`; this boolean value is not a truth verdict |

The [analysis](../analysis/practice/README.md) flags 665 rows with at least one
annotated subject missing from surface-name matching. This is a heuristic review
count, not proof that every such row requires preceding-row context.

Practice forms also do not necessarily enumerate every implication in the prose:
`p-3` mentions the provider Gemini runs on but annotates only Holdan's previous
employer. Use forms as the reference for their annotated scope, and review plausible
extractions separately rather than assuming every additional clause is a gold fact.

## Proposed output

Keep a row envelope containing `row_id`, original text, page date, resolved
assertions, unresolved fragments, and extraction status: `complete`, `partial`, or
`unresolved`. Here `complete` means every identified claim-bearing fragment has
been accounted for by the parser; it is an extraction claim to evaluate, not proof
of completeness or truth. Unknown clauses must prevent a confident complete result.

Each resolved assertion should carry:

- A stable occurrence ID, such as `p-5:a1`, and its parent row ID. Use deterministic
  source order, with explicit tie-breaking for shared spans.
- Canonical lexicon subject and attribute.
- Typed value: quantity, money, percent, date, version, duration, name, or boolean.
  Preserve units, currency, billing period, and the operator (`eq`, `lt`, `le`,
  `gt`, `ge`), as applicable under the [value schema](../contracts/claimed_value.schema.json).
- Page date separately from temporal qualifiers in the sentence. A date-valued
  assertion, an explicit historical date, and the page date are different things.
- Supporting spans in the original UTF-8 text, using byte offsets, plus the rule
  or context references responsible for each inferred field. Support multiple spans
  because a shared subject may be far from its predicate and value.
- Scope information where relevant: negation, condition, alternatives, approximation,
  and temporal wording. Retain original wording whenever normalization is uncertain.
- Extraction provenance: `practice_form` or `text_extraction`. A form record has no
  known text alignment unless separately established; do not invent offsets.

An unresolved fragment retains its spans, known fields, bounded alternative
interpretations, and a reason such as `ambiguous_subject`, `ambiguous_attribute`,
`unattached_value`, or `unsupported_scope`. Alternatives are mutually exclusive
parse candidates, not multiple simultaneously asserted facts. Extraction uncertainty
must remain distinct from a later `unsure` truth verdict.

Do not store assertions in a map keyed only by subject and attribute: repeated keys
can express different values, dates, or conditions. Preserve occurrence identity.

## Extraction sequence

1. **Read and preserve the row.** Use a CSV parser and retain exact text. Build a
   normalized matching view with offsets back to the original. Do not split on
   commas or the word `and` before understanding their roles.
2. **Find explicit entity mentions.** Match canonical names and aliases as whole
   words, preferring the longest matching entity name. `Hooly AI Pro` must not
   become a mention of the company Hooly. A mentioned entity can be a subject or
   a name-valued object; `Holdan joined Hooly` does not give both entities a
   `joined` assertion.
3. **Find typed values and predicate cues.** Recognize numbers in digits and words,
   units, money and billing periods, percentages, partial dates, versions, names,
   and boolean language. Protect numeric parts of entity names and decimal/version
   punctuation. Use exact decimal representations and preserve date precision.
4. **Build clause candidates.** Use verbs, possessives, punctuation, and supported
   coordination patterns to attach predicates and values. Distribute a shared
   subject across coordinated predicates, and shared predicates across coordinated
   subjects only when the wording supports that reading. Do not emit every possible
   combination of entities and values in the row.
5. **Resolve attributes within each subject's lexicon attributes.** Use reviewed
   phrase patterns derived from the development data, supported by value types and
   units. Types narrow possibilities but cannot choose between `included_seats` and
   `minimum_seats`, or different percentages, on their own. The lexicon lists allowed
   attributes; it does not supply authoritative attribute value types. Any inferred
   type hints need provenance and must allow ambiguous cases.
6. **Resolve omissions conservatively.** First use explicit mentions and grammatical
   links within the row. Then consider uniquely supported candidates from the
   lexicon and phrase meaning. Cross-row context is an optional, separately evaluated
   extension: the contract supplies no page ID or guaranteed document ordering.
   Adjacency, similar dates, and numeric row IDs do not prove shared context. Retain
   candidate subjects when unresolved; do not assign `He` to the nearest person or
   map a bare list to an arbitrary order of entities. Known practice forms remain
   reference annotations, not evidence that this resolution generalizes.
7. **Attach scope before emitting assertions.** Preserve `over`, `up to`, negation,
   billing alternatives, conditions, and temporal phrases. In `p-49`, “I will not
   call it good” does not negate the stated recovery time. In `p-493`, `or` describes
   two available billing options; a true disjunction elsewhere must not be flattened
   into two independently required facts. Keep unsupported relations, comparisons,
   and changes as structured unresolved fragments rather than inventing scalar values.
8. **Validate and account for the remainder.** Check subject/attribute membership,
   typed values, span bounds, and attachment consistency. Record unhandled
   claim-bearing fragments and values, with reasons. Output a stable list, not a
   verdict. Bounded candidate generation must expose truncation as partial extraction.

The strict [generated-claim grammar](../contracts/claim-forms.md) governs submitted
claims. It must not be used as a restriction on the prose accepted from input rows.

## Implementation stages for a future task

1. Expand practice forms into reference records with parent IDs and occurrence IDs;
   preserve the parent label only as metadata, never as an individual truth label.
2. Implement explicit subject/value cases and attribute phrase rules in safe Rust
   on CPU. Keep normalization, entity matching, value parsing, and attachment
   independently inspectable. No LLM is part of the submitted extractor.
3. Add multi-attribute and multi-subject coordination, shared spans, scope handling,
   and unresolved-fragment reporting. Include repeated keys before any deduplication.
4. Evaluate omitted subjects as a separate slice; add context rules only when their
   evidence is sufficient and measurable. Improve recall without hiding ambiguity.

No dependencies, models, or runtime components are selected or installed by this
plan. The first implementation milestone is reference expansion plus explicit
text extraction; later stages depend on its measured errors.

## Evaluation and acceptance

Evaluate extraction independently of truth labels. Rules may use only the
development partition's forms. Freeze held-out template groups before deriving
phrase rules, keep duplicates together, and add subject-held-out and independently
authored cases. A random row split alone is inadequate for repeated templates.
Held-out forms must not enter a context resolver or a lookup used during evaluation.

Report assertion precision, recall, and F1 using multiset matching of canonical
subject, attribute, operator, and typed value. Also report exact whole-row extraction,
field-level errors, complete/partial/unresolved rates, and false-complete cases
(claimed complete despite a missed or incorrect assertion). Report each metric by
single/multiple assertions, single/multiple subjects, implicit subjects, repeated
keys, value kind, negation, and temporal/conditional scope. Review annotation-scope
mismatches separately without silently changing the reference data.

Initial acceptance gates for implementation:

- Reference expansion reproduces all 2,402 annotated occurrences from all 1,897
  practice rows, with reversible parent linkage and no lost value fields.
- Curated examples above have expected splits or explicit unresolved outcomes;
  `p-843` cannot be declared resolved from its bare text alone.
- Hand-authored cases verify shared subjects, ambiguous attributes, unknown entities,
  unhandled clauses, local negation, dates, and unit attachment. Record development
  authorship; synthetic examples are parser tests, not Hooly truth evidence.
- Same-key occurrences survive, candidate interpretations are not promoted to facts,
  and unsupported input never becomes an empty list reported as complete.
- Extraction from text produces identical results when labels are changed or removed;
  the evaluation path never reads the held-out form.
- Publish measured accuracy and coverage before choosing an overall quality threshold.
  No achieved accuracy is claimed by this plan.

## Planning handoff

Decision: preserve a list of scoped assertion occurrences and unresolved content;
use practice forms to assess a separate runtime text extractor. This refines the
planned [core architecture](architecture.md) without changing a runtime interface.

Open decisions for discussion: how much explicit-pattern coverage is sufficient for
the first milestone, and whether independently validated cross-row context is worth
adding after the local extractor. The immediate next step is to review these output
semantics and the difficult examples before authorizing implementation.

Planning verification: inspected the contract, value schema, practice forms and
existing analysis; directly recounted row and assertion totals. `git diff --check`
passed. A Python check confirmed that all 22 local links across the changed documents
resolve and neither file has trailing whitespace. `cargo xtask docs` could not run
because `cargo` is unavailable in this environment. Foundation checks/tests were not
run for this documentation-only change. No solver or extraction accuracy check has run.
