**Manual review of assertion extraction — 28 October 2026**

My judgment: **keep the structured representation and the normalization/provenance
work, but do not treat the present splitter as a reliable source of knowledge-base
facts.** It makes well-supported sentences substantially easier to consume. On other
sentences it leaves the original problem unresolved, and sometimes adds a wrong
subject–attribute assignment that a later stage would have to undo.

This is a useful first prototype, not a completed extraction layer. The examples
below—not the previously reported precision/recall numbers—are the basis for that
assessment. No parser changes are included in this review.

**What I inspected and how**

I read 47 distinct practice rows alongside their actual output fragments: 39 selected
to cover successes, suspected errors, ambiguity, normalization and splitting behavior,
plus eight additional rows sampled from the remaining rows containing paired output.
Those eight were `p-1897`, `p-1352`, `p-1250`, `p-1444`, `p-1488`, `p-1301`, `p-1856`,
and `p-92` (seed `20261028`, candidate IDs sorted numerically).

A CSV reader only retrieved and displayed records. I judged the original sentence,
the output wording and fields, and then the practice `form` manually. I also inspected
the implementation to explain a few failures. I did not use automated rates to grade
these examples, infer the truth of the claims, or extrapolate a population accuracy
from this deliberately selected sample. The appendix identifies every reviewed row.

The practice form is a useful reference, but not a perfect inventory of every claim
one could read from the prose. A mismatch with it is not automatically a semantic
error. Conversely, a matching subject–attribute pair does not establish that the
fragment includes all the necessary wording or that the whole row was extracted.

Sources:

- [Practice CSV](../../data/practice.csv) and [lexicon](../../data/lexicon.json).
- Existing `outputs/practice.assertions.csv`; original and normalized text, statuses,
  fields and reasons were inspected. No output was regenerated for this review.
- [Splitter](../../crates/core/src/extraction/split.rs),
  [attribute cues](../../crates/core/src/extraction/attribute-cues.json), and
  [normalizer](../../crates/core/src/extraction/lexicon.rs).
- [Runtime contract](../../contracts/README.md) and
  [existing KB experiment scope](../kb-experiments/README.md).

Snapshot: repository commit `51db366322abd98e5bbb735f93b2440b7a5988b0`.

```text
practice.csv SHA-256:
52743befaa0fa38b89b5c802c0f953d242ae027c86839c9c0f05a9e69a86d8e9
lexicon.json SHA-256:
d0fd5e9bdc6b33ad3ec160001f50e00e7f8bf2b25a92779022f893db7c3d5507
practice.assertions.csv SHA-256:
5a9150958ebf59347509188e766c8423f86bd785458fa1ba0ce04bca375f890c
```

**Where the output is useful**

**`p-5`: a clean shared-subject split.** The source is:

> Hooly Cloud has been open since November 2025 and covers 3 regions so far.

The tool produces:

| Subject | Attribute | Actual assertion text |
| --- | --- | --- |
| Hooly Cloud | launched | has been open since November 2025 |
| Hooly Cloud | regions | covers 3 regions so far. |

This is the intended result. The date and count stay with their predicates, the
shared subject is correct, and there is no need to interpret numbers yet. A later
stage can work on two small, relevant phrases instead of rediscovering their pairing.

**`p-1834`: the multi-subject example genuinely becomes easier.** Three products have
prices, seat counts and, for two products, SLAs. All eight emitted occurrences attach
to the correct products and attributes. In particular, `€1,200` stays intact, and
`Hooly Workspace Enterprise` does not collapse into `Hooly Workspace`. The eight
records are useful inputs to later value interpretation. This is the strongest
reviewed example in favor of keeping the representation.

**`p-493`: billing wording is preserved.** The source offers Jules at `€19 a month`,
`€190 a year`, after a `14-day trial`. The three outputs are `price`, `annual_price`,
and `free_trial`, with those phrases retained. Good first-stage extraction. The
word `or` and the trial wording still matter; a later stage must understand these as
billing options and a trial, not arbitrary mutually contradictory observations.

**`p-40` and `p-43`: useful handling of coordination and negation.** In `p-40`,
“checks spelling and grammar in 8 languages” stays together under `languages`;
splitting at that `and` would have damaged the assertion. In `p-43`, “does not work
offline yet” remains attached to `offline_editing`. The negative assertion is not
silently turned into a positive one. The extra unresolved explanation “you will need
a connection for now” is conservative but should not be confused with a missing
independent scalar assertion.

**The additional sample includes straightforward good results.** `p-1897` correctly
normalizes `Workspace Enterprise` and extracts `storage_per_user: 1 TB`. `p-1301`
correctly resolves “Hooly's Q4 results” and keeps `€4.2 million` with `revenue`.
`p-1856` attaches “Desktop mode ... is enabled” to `Hooly Android 16 / desktop_mode`.
`p-92` correctly identifies the Photos free-storage claim. `p-1454` also distinguishes
the API/interface version from the general Gemini product version.

These examples support a narrow conclusion: **the current output is helpful when
the attachment is right and the fragment is self-contained for the intended claim.**
They do not establish that every record tagged `paired` meets those conditions.

**Paired output that I would not trust without correction**

| Row | What the sentence says | What the tool does | Manual judgment |
| --- | --- | --- | --- |
| `p-61` | Chrome ships a stable version **every 4 weeks**. | Pairs the whole phrase with `stable_version`. | Wrong attribute. This is a release cadence, not the version identifier. |
| `p-156` | A trade-in gives **up to up to €200** when ordering a Pixel Fold. | Pairs it with `Hooly Pixel Fold / price`. | Wrong relationship and attribute. A credit is not the phone's price. The repeated “up to” is source wording and should be retained, not silently repaired. |
| `p-527` | Workspace includes 10 seats; **each further seat costs €15/month**. | Correctly extracts included seats, then assigns the extra-seat amount to ordinary `price`. | The second pairing is wrong. Feeding it into the main-price timeline would create a false conflict. |
| `p-903` | Each offline Maps area can take **5 GB**. | Assigns `offline_maps`. | The phrase concerns `offline_area_limit`; it is not simply an on/off capability assertion. |
| `p-1307` | Advertising contributes **78% of revenue** in Q4 results. | Assigns `revenue`. | Wrong attribute. The percentage is the advertising share, not the revenue amount. Compare the correct revenue extraction in `p-1301`. |
| `p-1619` | Jules has **500 beta testers**. | Assigns `users`; leaves the beta-lead clause unresolved. | The paired count is assigned to the wrong population. General users and beta testers are different attributes. |
| `p-1735` | Tabs sleep after **10 minutes when memory saver is active**. | Assigns the entire sentence to `memory_saver`. | It misses `tab_sleep_delay` and treats wording in a condition as the attribute being asserted. The source does not simply assert that memory saver is active unconditionally. |

These are not just formatting defects. If a later evaluator assumes the pair is
correct, a perfectly good money, percentage or duration parser can still produce the
wrong fact. It will have faithfully interpreted a value under the wrong key.

There is also a systematic problem with version-bearing sentences:

- **`p-1352`** says “Hooly Jules **1.2** costs €29 per month and supports 8 languages.”
  The outputs are price (`1.2 costs €29 per month`) and programming languages.
  Both pairings contain real assertions, but **the version assertion is missing**.
  The row is nevertheless marked `split`. Its parent label is `false`; that does not
  identify which assertion is false, and extraction must preserve all stated claims.
- **`p-1444`** places `2.1 brings 5 sdks` under `official_sdks`, with `6 events` left
  unresolved. The SDK assignment is reasonable, but version `2.1` has no separate
  occurrence and webhook events are missed.
- **`p-1488`** pairs `1.5 ships on Nimbus Cloud` with `version`, but does not separately
  extract `cloud_provider`. The fragment contains more than the one asserted
  attribute its record exposes.
- **`p-1398`** assigns `2.2 went live this week` to product `launched`. That wording
  concerns the release of a particular version; it does not establish the product's
  original launch date. The version and file-upload-limit assertions are not recovered.

The first-stage contract is not met merely because a paragraph has become shorter.
Every separately stated claim needs either an appropriate occurrence or an explicit
unresolved indication. Leaving an extra claim inside a paired fragment can hide it
from algorithms that only iterate over the emitted keys.

**A particularly important boundary failure: `p-20`**

> The Hooly Jules beta opens today, 14 April 2026.

The tool pairs `The Hooly Jules beta opens today` with `beta_date` and emits
`14 April 2026.` as an unresolved fragment. The pair is correct, but the explicit date
has been detached from the assertion. A later component could infer “today” from the
row date here, yet it should not need to reconstruct an attachment the source stated
directly. This is a stage-one failure even though date normalization is deliberately
deferred to stage two. A comma is not sufficient evidence of an assertion boundary.

**Where annotation disagreement needs a more careful judgment**

- **`p-58`:** “Hooly Chrome 69.0 brings an AI sidebar.” The tool extracts `ai_sidebar`,
  while the form lists `stable_version`. The sidebar claim is linguistically supported;
  I would not call it invented just because it is absent from the form. However, the
  explicit version is missed and the result is not a complete split.
- **`p-169`:** “On 24 March 2026 in Berlin we launched Hooly Gemini 2.0.” The form
  includes an I/O event's date and city plus Gemini's version. The row alone does not
  name that event. The tool should recover or flag the explicit version and other
  wording; it should not be expected to invent `Hooly I/O 2026` from an unstated link.
  Its product-level `launched` assignment is too coarse to settle the meaning.
- **`p-1134`:** “Hooly's payroll lists 380 employees, each one a legend.” The tool
  emits `Hooly / employees`; the form uses Q4-results `headcount`. The company-level
  reading is reasonable from this sentence alone. The specific reporting-period
  subject needs additional evidence. The residual assertion also starts with the
  awkward possessive `'s` after removing the name; that is a wording issue rather
  than proof that the value or company reference is wrong.
- **`p-1335`:** “Hooly Jules has no price yet” is a real statement about price
  availability, but not an ordinary numeric price. Its absence from the practice
  form does not make the wording meaningless. Keep it as a distinct negative/
  availability statement or scoped unresolved content; do not turn it into price
  zero or another numeric observation. The Workspace €199/month assertion later in
  the row is recovered correctly, although the apposition is split into noisy pieces.

The improvement target should therefore be semantic fidelity, not simply maximizing
agreement with every existing form or deleting every extra pair.

**Unresolved output: some caution is justified, but much is avoidable**

| Row | Actual unresolved behavior | What I think should happen |
| --- | --- | --- |
| `p-1` | Rejects “Holdan started at Hooly on 12 January 2026” because two entities are mentioned. | Resolve `Holdan / joined`; Hooly is the employer/object in this construction. Two mentioned entities do not imply two competing grammatical subjects. |
| `p-2` | Separates “From today”; rejects the reliability-team clause because it names both Hooly Cloud and Holdan. | Recognize the role relation: Cloud's `reliability_lead` is Holdan. Retain the temporal wording with that relation. |
| `p-8` | Knows Cloud but cannot assign “Last quarter ... was up 99.82% of the time.” | Resolve `uptime_last_quarter`; this is a clear local paraphrase. |
| `p-11` | Correctly normalizes Cloud Next, but keeps “closed after 3 days at Ringsend Forum” unresolved. | Extract event duration and venue as separate attachments. No interpretation of “3 days” into a numeric duration is needed yet. |
| `p-22` | Treats “Jules users accept 38% of its suggestions” as multiple competing attributes. | Distinguish the actors (“users”) from what is asserted: suggestion acceptance rate. |
| `p-27` | Keeps general availability date and monthly price in one unresolved fragment. | Both are explicit, separable claims about Jules. Support the date predicate and price phrase without requiring `and` or a semicolon. |
| `p-44` | Leaves the Drive mention in one fragment and “where the free tier gives 5 GB” without a subject. | Bind the relative clause to Drive and extract `free_storage`. Current splitting makes the attachment problem harder. |
| `p-82`, `p-611`, `p-1250` | Misses “holds 1 TB,” “starts at 256 GB,” and “stores 256 GB.” | Use the local predicate, unit family and allowed attributes to propose storage/base-storage. Do not generalize every “starts at” into a price. |
| `p-1048` | Misses Search's “answers in 80 languages.” | Use language-serving cues, not a response-time interpretation of the words “answers in.” |
| `p-808` | Leaves the entire monthly-price/billing-condition sentence unresolved. | Caution is reasonable, but at least the first explicit monthly price can be preserved separately; retain the second as conditional. Never silently change its stated `€590 per month` to per year. |
| `p-817` | Keeps “Chair: Peter Gregori” unresolved but fills `subject=Peter Gregori`. | Peter is naturally the named chair, not necessarily the entity whose chair is being described. Preserve the known role/object and leave the governing subject uncertain unless supported. |

Some unresolved cases should **remain** unresolved from row-local text:

- **`p-4`:** “He begins with a small crew of 4 engineers...” does not identify who
  “he” is. The reference supplies Holdan, but the isolated sentence does not.
- **`p-7`:** “The platform already serves over 100 customers...” gives a count and
  operator but not a uniquely established platform identity.
- **`p-843`:** “Ads: 78%, 72%, 66%, 61%” supplies neither four subjects nor their
  ordering. The reference supplies four quarterly results. Splitting it into four
  independent resolved facts would require an unsupported guess. The present tool
  correctly declines to do that, but four disconnected unresolved fragments lose
  the useful shared `Ads` cue. Prefer one unresolved list group with ordered members.
- **`p-46`:** “Holdan has run Hooly Cloud reliability since January 2026” supports a
  role relation and its temporal qualifier. It does not necessarily establish a
  general employment `joined` date just because the practice form includes one.
  Extract the supported role relation; do not manufacture the extra inference.

Adjacency in the CSV might suggest context to a human browsing practice. It is not a
contractual guarantee of page membership or discourse continuity in evaluation.
I would not fix these by blindly borrowing the preceding row's subject.

**Normalization: useful foundation, overly coarse ambiguity in places**

Reviewed positive cases include Gemini in `p-23` and `p-25`, Cloud Next in `p-11`,
Workspace Enterprise in `p-1897`, the quarterly-results aliases in `p-1301`/`p-1307`,
and Android 16 in `p-1856`. These replacements reduce superficial variation without
changing the intended entity, and the retained source text makes them auditable.

Two reviewed cases show why a blanket ordinary-word policy is not enough:

- **`p-302`:** “Photos stored in Hooly Photos: 4,200,000,000 photos” gets a useful
  `photos_stored` pairing, but both ordinary uses of “Photos/photos” generate alias
  ambiguity warnings. Here they are nouns describing the counted objects, not
  unresolved product references.
- **`p-1239`:** “Android runs on 2,900,000,000 devices...” leaves Android unresolved,
  even though the predicate and the nearby Android 16 context strongly support the
  platform reading. The longer Android 16 alias is normalized, but its device-share
  claim also remains unresolved.

Keep the conservative fallback, but add contextual disambiguation. Ordinary nouns
should not automatically become entity problems; clear product uses should not be
permanently blocked just because the same spelling can sometimes be ordinary language.

**What the implementation inspection explains**

These are concrete design weaknesses, not evidence that an LLM is required:

1. The splitter often treats a set of entity mentions as a set of possible subjects.
   That explains why easy subject–object constructions such as `p-1` and `p-2` fail.
2. Attribute assignment is primarily cue matching within a fragment. It lacks a
   sufficient distinction between a predicate, its objects, modifiers, and conditions.
   This explains cases such as stable-version wording versus release cadence, users
   versus beta testers, and memory saver versus tab-sleep delay.
3. `find_attributes` rejects a cue match whenever its full span overlaps an entity
   mention. This protects against finding attributes inside names, but also rejects
   legitimate longer patterns that span a subject. The existing last-quarter pattern
   in `p-8`, and the extra-seat pattern crossing “Hooly Workspace” in `p-527`, are
   affected. Adding more synonyms alone will not repair that structural problem.
4. Delimiter handling sometimes precedes attachment decisions. `p-20` and `p-44`
   show a date apposition and relative clause becoming detached fragments.
5. There is no sufficient account of unrepresented claims inside already paired
   fragments. The extra version in `p-1352` is still in the text, but invisible as a
   separate claim to a consumer iterating over the emitted pairs.

**Does this help solve the actual task?**

| How it is used | My assessment |
| --- | --- |
| As an optional structured view alongside the original text | Helpful: easier inspection, useful candidate keys, and less repeated work on supported patterns. |
| As the only representation passed to the future reasoner | Not ready: wrong keys, missing claims and detached context can produce confident wrong answers. |
| To reconstruct the supplied practice forms before building the practice KB | An unnecessary source of errors. Import the supplied forms directly. |
| As a finished solution for unknown evaluation text | No. Extraction, value interpretation, evidence evaluation and row-level decisions are still incomplete. |

The current output does **not** make the task uniformly easier. It makes the clear
cases easier and exposes some uncertainty usefully. Where a correct value is put
under the wrong attribute, it makes downstream reasoning harder: the reasoner must
first detect and undo the parser's claim before comparing evidence. Where a sentence
is fragmented poorly, the next stage has to reconstruct the original attachment.

This is recoverable because the full original text and provenance have been retained.
The problem is not irreversible data loss in the CSV; it is loss of meaning if a
consumer trusts the derived fields and ignores the retained context.

The correct precompute/runtime distinction matters:

- **Practice precompute:** import the original `form` records with their row IDs,
  dates and parent labels. They describe what each row claims. A false compound row
  does not label every contained assertion false, and its forms do not supply true
  replacement values. The lexicon supplies allowed keys, not truth values.
- **Runtime unknown text:** use normalization and extraction to produce candidate
  assertions, then interpret values and scope, retrieve relevant evidence, and
  decide the row label with explicit uncertainty handling. No `form` is supplied
  for these unknown rows. Known practice rows can use their bundled annotations
  after checking identity/text/date; that does not solve the unknown rows.
- **Row decisions:** a missing claim matters. Even if two recovered assertions are
  true, an omitted third assertion could make the row false. A trustworthy
  contradiction can establish a false compound row; missing evidence cannot simply
  be treated as support for a true row.

The repository now also contains KB experiments, but their documented inputs are
the supplied structured practice forms, including the facts of held-out rows. They
evaluate downstream reasoning under that input assumption; they do not demonstrate
that the current text extractor can supply equally good facts for unknown prose.
Their inferred page grouping is also an experimental assumption. We should measure
the combined pipeline before transferring any downstream performance claim to it.

**Can this be completed offline without an LLM?** The concrete improvements above
are compatible with ordinary rules, explicit lexical resources, and possibly small
task-specific classifiers if later justified. None requires internet access at run
time. That is an engineering feasibility judgment, not a promise that arbitrary
English or missing context is easy to resolve. An LLM would not make an unstated
subject mapping into established evidence either.

The complete competition task still needs typed values, temporal/evidence reasoning,
calibrated row decisions and a valid generator for the required 1,000 new claims.
Those are separate from this review's extraction layer. The present tool and lab
experiments together are not yet a completed competition solution.

**What I would improve, in order**

| Priority | Change | Concrete acceptance examples |
| --- | --- | --- |
| 1 | Treat `paired` as an attachment proposal, not a trusted fact. Record unresolved claim-bearing content even inside a paired fragment; separate that from ordinary commentary. | `p-1352` cannot appear fully accounted for while version 1.2 has no record; `p-25` need not be treated like a missed numeric claim just because narrative text remains. |
| 2 | Recognize local predicate/role structure and subject–object distinctions. | Resolve Holdan's joining in `p-1` and Cloud's reliability lead in `p-2`; do not interpret a named chair as the entity owning the chair attribute in `p-817`. |
| 3 | Identify candidate attachment spans before committing to comma/conjunction boundaries. Preserve appositions, relative clauses and shared list scope. | Keep the explicit date with `p-20`; attach the free-tier relative clause in `p-44`; retain a list group for `p-843`. |
| 4 | Fix cue-span filtering and attribute specificity; add phrase patterns with contrasting negative examples. | Extra-seat price in `p-527`, uptime in `p-8`, cadence in `p-61`, trade-in credit versus price in `p-156`, advertising share in `p-1307`. |
| 5 | Account for inline version claims and multiple predicates without relying only on delimiters. | Recover version plus price in `p-1352`, version plus SDKs/events in `p-1444`, and general availability plus price in `p-27`. |
| 6 | Use light lexical value cues to help attachment while preserving raw wording. | Storage phrases in `p-82`/`p-611`/`p-1250`; distinguish a percentage share from money revenue. Recognizing a money/duration/version-shaped phrase does not require implementing all typed-value semantics yet. |
| 7 | Add contextual alias handling and preserve bounded candidates where context is insufficient. | Avoid noun warnings in `p-302`; recognize supported platform use in `p-1239`; keep `p-4`, `p-7` and `p-843` unresolved unless real evidence establishes their subjects. |
| 8 | Make a reviewed semantic fixture set and evaluate downstream impact as well as pair agreement. | Check missing/extra claims, predicate/value attachment, negation, conditions, and full-row support; then compare actual-text input with form input in an independent test. |

For priorities 2–6, prefer a modest set of inspectable predicate frames and local
attachment rules over an indefinitely growing collection of disconnected keyword
exceptions. Include hard negatives: “ships a stable version every four weeks” versus
“stable version 69.0”; base price versus extra-seat price versus trade-in credit;
general users versus beta testers. A pattern should explain why it selects the pair.

We can keep the two-stage design, with one qualification: **stage one cannot defer
all semantics.** It must understand enough to keep each claim's subject, predicate,
value phrase and scope together. Stage two can still own exact number parsing,
unit conversion, typed dates, operators and truth evaluation.

The reviewed rows are now development material. Do not tune on them and later
describe them as unseen evaluation. Freeze independent examples/template groups for
the next comparison, including examples where abstaining is the correct behavior.

**Compact ledger of all 47 inspected rows**

“Useful” below concerns the specified fragment or row, not its truth. Mixed rows are
described explicitly; this ledger is not a scored benchmark.

| Row | Manual finding |
| --- | --- |
| `p-1` | Avoidable abstention: employer mention confused with a second subject. |
| `p-2` | Avoidable abstention: role holder and owning product not distinguished. |
| `p-4` | Unidentified pronoun: row-local abstention justified. |
| `p-5` | Useful complete split of launch wording and regions. |
| `p-7` | Platform identity absent; retain the count phrase without guessing identity. |
| `p-8` | Explicit subject and uptime phrasing missed; cue-span filtering is implicated. |
| `p-11` | Good event normalization, missed duration and venue attachments. |
| `p-20` | Correct beta-date pair but explicit date detached. |
| `p-22` | Useful users/languages outputs; actor noun blocks suggestion-acceptance extraction. |
| `p-23` | Useful alias normalization and version extraction; prefix text is harmless here. |
| `p-25` | Both annotated scalar assertions recovered; unresolved narrative is a different kind of remainder. |
| `p-27` | Two explicit predicates are not separated. |
| `p-40` | Correctly retains object coordination within the language assertion. |
| `p-43` | Negation preserved; explanatory remainder should not be mistaken for a missing scalar fact. |
| `p-44` | Relative clause detached from its available product subject. |
| `p-46` | Role relation can be recovered; general joining-date inference is not assured by wording alone. |
| `p-58` | Sidebar assertion is supported but unannotated; version claim missed. |
| `p-61` | Release cadence misassigned to stable version. |
| `p-82` | Correct price; explicit storage phrase unresolved. |
| `p-92` | Useful Photos/free-storage extraction. |
| `p-156` | Trade-in credit incorrectly becomes phone price. |
| `p-169` | Version/event structure missed; event identity is not explicit in the row. |
| `p-302` | Useful photos-stored pair; ordinary nouns generate unnecessary entity warnings. |
| `p-493` | Useful monthly/annual/trial separation, with billing wording retained. |
| `p-527` | Included seats correct; additional-seat price incorrectly becomes base price. |
| `p-611` | Clear base-storage phrase unresolved. |
| `p-808` | Conditional abstention is safe but overly broad; preserve the stated monthly units. |
| `p-817` | No resolved pair, but the filled subject likely represents the role's object. |
| `p-843` | Subject mapping genuinely missing; unresolved list should remain grouped. |
| `p-903` | Area capacity misassigned to an offline capability. |
| `p-1048` | Language-serving claim missed despite an explicit subject. |
| `p-1134` | Company-employee reading reasonable; annotation's quarterly subject needs context. |
| `p-1239` | Conservative alias rule and attachment gaps leave a strong local platform reading unresolved. |
| `p-1250` | Battery capacity useful; storage missed. |
| `p-1301` | Useful quarterly alias and monetary revenue extraction. |
| `p-1307` | Advertising percentage misassigned to monetary revenue. |
| `p-1335` | Workspace price useful; no-price-yet statement needs distinct semantics; apposition fragmented. |
| `p-1352` | Price/languages useful individually; version omitted under a misleadingly complete-looking row status. |
| `p-1398` | Version release confused with product launch; file limit missed. |
| `p-1444` | SDK count useful; inline version and events not represented separately. |
| `p-1454` | Useful distinction between interface/API version and product version. |
| `p-1488` | Version useful; cloud-provider claim buried in the same fragment. |
| `p-1619` | Beta testers misassigned to general users; leadership clause unresolved. |
| `p-1735` | Conditional feature wording displaces the actual delay assertion. |
| `p-1834` | Useful eight-way split across three explicitly named products. |
| `p-1856` | Useful Android 16 alias normalization and desktop-mode claim. |
| `p-1897` | Useful Enterprise alias normalization and per-user storage extraction. |

**Review record**

Task `assertion-output-review`; human owner unassigned; review author Codex. Prepared
in isolated branch `review/assertion-output`, checkout `/tmp/veridyct-assertion-review`,
from the snapshot identified above. Scope: this report and a link from the lab README.
Acceptance: concrete paired/unresolved examples checked against source prose and
practice annotations, an honest assessment of downstream usefulness, and prioritized
improvements. No implementation, training, truth labeling, or dataset changes.

This document contains review conclusions and source examples, not an internal
reasoning transcript. The source text remains authoritative for what a row claims;
the review does not establish new Hooly truth evidence.
