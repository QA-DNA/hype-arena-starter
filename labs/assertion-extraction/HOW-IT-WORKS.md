# How the assertion parser works

This describes the implemented schema-v2 parser, not the entire proposed extraction
plan. The implementation is a custom heuristic extractor built from regular expressions,
lexicon constraints and bounded context state. “Rule-based NLP” refers to those language
processing methods: there is no trained dependency parser, part-of-speech tagger,
coreference model or LLM/SLM in this pipeline.

For commands and output columns, see the [lab README](README.md). For measured coverage
and known errors, see the [v2 results](V2-RESULTS-2026-10-28.md).

## Libraries and implementation boundaries

| Library/component | Actual use |
| --- | --- |
| Rust `regex` | Entity matching, clause-boundary candidates, attribute cues, versions and qualifiers |
| `serde` | Serialization/deserialization of Rust structs |
| `serde_json` | Lexicon/index JSON and nested assertion metadata |
| `sha2` | SHA-256 fingerprints for index consistency |
| `csv` | CSV reading/writing, including quoted commas and multiline cells |
| Rust standard library | Ordered maps/sets, vectors, context queue and filesystem operations |
| Node.js and browser JavaScript | Build, serve and inspect the generated viewer; no extraction |

The exact dependency versions are recorded in [Cargo.lock](../../Cargo.lock); the
workspace uses Rust 1.90 and edition 2024. `axum` and `tokio` belong to the separate
HTTP application and do not participate in the CLI parser's execution path. Core
behavior lives in [crates/core/src/extraction](../../crates/core/src/extraction/mod.rs),
independent of CLI, HTTP and browser adapters. The workspace forbids unsafe Rust.

## 1. Lexicon indexing: canonicalization and inverted lookup

[lexicon.rs](../../crates/core/src/extraction/lexicon.rs) reads canonical subjects,
aliases and allowed attributes, validates them, and sorts/deduplicates their entries.
Lookup spellings are lowercased, apostrophes normalized and whitespace collapsed.
It builds an inverted lookup:

```text
surface spelling → set of canonical subjects
```

The target is a set because an alias may name more than one subject. `BTreeMap` and
`BTreeSet` give sorted iteration, making serialization and results deterministic.
Reviewed alias additions can supply extra spellings with explicit provenance; the
normalizer does not invent aliases by removing parts of canonical names.

The source and normalized index contents receive SHA-256 fingerprints. Rebuilding
and comparing the fingerprint catches inconsistent indexes. This is content-integrity
checking, not a signature proving the source is trustworthy.

The persisted “compiled index” contains prepared lookup data, not serialized regex
machine code. The normalizer constructs and compiles regex patterns at startup.

## 2. Entity recognition: dictionary matching and greedy overlap removal

Each indexed spelling becomes a case-insensitive regex. Literal name characters are
escaped; whitespace and apostrophe variations receive limited flexibility.
For each row, the normalizer:

1. Runs each entity pattern over the text and collects candidate byte spans.
2. Rejects matches embedded inside larger words, using adjacent-character checks.
3. Sorts candidates by descending span length, then position and spelling.
4. Accepts a candidate only if it overlaps no already accepted candidate.
5. Sorts accepted matches back into text order.

This is **greedy longest-match selection**. `Hooly Photos Max` wins over an overlapping
`Hooly Photos` match. The algorithm does not search every possible combination of entity
interpretations or optimize a global parse score.

Common-word aliases receive additional hand-written filters. A counted noun such as
“100 photos” is excluded; an appropriately positioned “Photos has…” can pass a
product-predicate rule. Colliding aliases and unresolved common words remain recorded
as ambiguity candidates. This disambiguation is limited pattern matching, not general
word-sense understanding.

## 3. Source alignment: piecewise byte-range mapping

Replacing `Gemini` with `Hooly Gemini` changes string lengths. The normalizer therefore
stores `OffsetSegment` records:

```text
original range → normalized range → replacement flag
```

For unchanged segments, positions translate arithmetically. For replacement segments,
a normalized match maps back to the whole original alias span. The code does not invent
a character-by-character correspondence between two different spellings.

Spans are half-open UTF-8 byte ranges, `[start, end)`. Alignment validation checks
coverage, ordering and valid string boundaries. The viewer uses `TextEncoder` and
`TextDecoder` to interpret those offsets correctly. Cross-row `SourceReference` values
include their own row ID, so an antecedent's offsets are not mistaken for positions in
the current row.

## 4. Clause parsing: candidate boundaries followed by rejection rules

[split.rs](../../crates/core/src/extraction/split.rs) proposes boundaries at commas,
semicolons, sentence endings and selected connectors: `and`, `with`, `but`, `or`,
`after a`, and `at`.

Additional conditions reject inappropriate boundaries:

- A boundary cannot cut through a recognized entity.
- Commas inside thousands or recognized date constructions are protected.
- Supported leading temporal/conditional phrases remain attached.
- `and` requires evidence that the following text begins another supported clause.
- Certain conditions, alternatives and shared negations prevent splitting.
- Billing alternatives and venue/availability constructions have specific handling.

This is shallow parsing with guarded segmentation. It does not build a dependency
tree, use a context-free grammar or maintain a chart of alternative syntactic parses.
A subject can carry between supported clauses within a sentence, with state reset at
selected sentence/semicolon boundaries.

Explicit coordinated subjects receive separate handling. A supported shared predicate
can be distributed to them; aligned percentage lists with `respectively` use ordered
subject/value correspondence. An unaligned recognized list remains one unresolved group
with its member spans. No subject mapping is inferred by looking up which values would
make the list true.

## 5. Subject assignment: constraint filtering

The within-row algorithm is approximately:

```text
if exactly one distinct entity is mentioned:
    use that entity
else if no entity is mentioned and a supported continuation prefix matches:
    try the preceding clause's subject
else if multiple entities are mentioned and a recognized predicate occurs:
    find entities whose allowed attributes match the clause
    accept only one distinct compatible entity
else:
    retain the unresolved fragment
```

For “Holdan joined Hooly”, the `joined` cue matches an attribute allowed for Holdan.
That permits the intended attachment. The code is not deriving a grammatical subject
through a trained dependency parser; predicate cues and schema compatibility approximate
that relationship. If several entities remain compatible, it generally cannot choose.

## 6. Attribute assignment: cues, specificity and explicit precedence

Attribute patterns come from three sources:

- Literal attribute names: underscores become spaces or permitted separators.
- A limited regular-plural transformation for attributes ending in `s`.
- Reviewed patterns in [attribute-cues.json](../../crates/core/src/extraction/attribute-cues.json).

For a candidate subject, only its allowed attributes are considered. Each pattern
is matched separately. The algorithm rejects matches inside entity names or larger
words, applies explicit conflict rules, removes shorter cue matches contained inside
longer matches, and collects the remaining distinct attributes.

For “each extra seat costs €15”, both `price` and `extra_seat_price` may be candidates.
An explicit precedence rule suppresses the general price cue. Similar rules distinguish
beta testers from users, cadence from versions, and advertising share from revenue.

There are rejection heuristics too. Selected count attributes require digits or a
recognized number word somewhere in the clause. This is a simple filter, not a complete
quantity parser or proof that the number belongs to that attribute. Trade-in wording
suppresses an ordinary-price interpretation.

There is no learned score or probability. One remaining attribute can be accepted;
competing attributes generally keep the fragment unresolved. Attribute rules still
have false positives, missed paraphrases and incomplete clause coverage.

## 7. Cross-row resolution: a bounded state machine

[discourse.rs](../../crates/core/src/extraction/discourse.rs) implements
`DocumentExtractor`. Its state includes a `VecDeque<Topic>`, where a topic stores:

```text
canonical subject
original mention's row ID and byte span
input ordinal
person/non-person hint
explicit version qualifiers
```

For each row, it first runs the within-row parser. It then clears context on a changed
or missing date, removes topics older than eight preceding rows, and prunes unrelated
product topics when a recognized product takes focus. Eligible unresolved fragments
are revisited against the remaining topics. Reference type and matching attributes
filter the candidates; resolution requires one subject and one attribute. Finally,
the current row's explicit mentions update the queue, capped at 64 topics.

The person hint currently means the subject has a `joined` or `previous_employer`
attribute. Product relatedness uses equality or a space-delimited name-prefix
relationship. These are heuristics, not a learned entity-type classifier or ontology.
A same-date run is a candidate discourse block, not verified page membership.

Explicit mentions refresh topic age; inferred pronouns do not. Thus repeated “it”
references cannot perpetually renew an old antecedent. Additional guards prevent an
unrecognized named actor such as “Lite” from inheriting a previously mentioned Max plan
for all its coordinated predicates. Ambiguous subjects remain visible as candidates.

No row labels or practice forms enter this algorithm. A source reference records a
linguistic dependency; it does not establish that the source sentence is true.

## 8. Versions and qualifiers: specialized span recognizers

[syntax.rs](../../crates/core/src/extraction/syntax.rs) recognizes versions with an
anchored regex immediately after a recognized subject mention. It supports marked
versions such as `v1` and dotted versions such as `2.2`, plus selected track prefixes
including CLI/API. Allowed lexicon attributes determine the applicable version slot.

The splitter can emit a version assertion separately from other attributes. Version
context propagates through supported coordination and selected preceding-row references,
with original source references. A fresh bare product mention does not automatically
receive the preceding version. Multiple inherited version candidates are marked ambiguous.
Numeric suffixes inside canonical entity names, such as Android 17, stay part of those
names rather than automatically becoming generic version attributes.

Other recognizers scan for qualifier spans, including:

```text
condition:  if / unless / when / while ...
bound:      over / under / at least / up to ...
time:       today / now / last quarter / since ...
population: beta testers / monthly users ...
billing:    per month / per year / per seat ...
```

These are text-span detectors. They do not construct formal temporal logic, evaluate
conditions, interpret every numeric value or perform count arithmetic. Their coverage
and span boundaries can still be imperfect. Version identity is preserved as written;
there is no automatic semantic-version equivalence such as `2.3` equaling `2.3.0`.

## 9. Objects, persistence and execution costs

The internal representation is ordinary Rust structs and vectors. `NormalizedRow`
contains text, mentions, ambiguity records and alignment segments. `ParsedRow` contains
its assertion occurrences and stream metadata. Each `AssertionText` holds fields and
provenance; repeated subject/attribute pairs remain distinct occurrences.

The combined command passes these objects directly between stages. CSV serialization
happens at the boundary, with nested fields represented as JSON cells. The separate
`split` command validates persisted normalization by recomputing it and comparing the
result; the combined command does not perform that second normalization.

The [CLI adapter](../../crates/cli/src/preprocessing.rs) reads rows sequentially, retains
a set of IDs to reject duplicates, and writes temporary sibling output files before
flushing/synchronizing and renaming them. Assertion and summary files are individually
atomic, not a single multi-file transaction. One extractor instance serves an ordered
stream, and context resets between files or explicit core resets.

The parser uses one thread. Its costs mainly come from scanning each row with multiple
regexes. Entity candidate sorting costs O(K log K); greedy overlap checks can be O(K²)
for K candidates. Cue-containment filtering also uses pairwise comparisons. Source-span
mapping scans and validates alignment segments. Consequently, the whole pipeline is
not globally linear-time or a single-pass lexical automaton.

Resource guards include a 1 MiB input-text limit, at most 4,096 entity candidates,
and grammar abstention above 64 KiB of normalized text or 256 mentions. Context and
recognized list/qualifier collections are bounded. These limits control work but do
not establish a worst-case runtime guarantee for every legal input. Benchmarks in the
results document cover actual practice and scaled repetition of it.

## Limits and possible next algorithms

The main limitation is coverage and reliability of the hand-written grammar. A
non-LLM sequence tagger could learn span boundaries, and a statistical candidate ranker
could learn ambiguous attachment preferences. Neither is currently implemented; there
are no embeddings, model weights, training loop or calibrated parse probabilities.
Any such addition needs manually reviewed supervision and independent evaluation.

`paired` means a rule selected a pair. `split` means all emitted fragments are paired
without normalization issues. Neither is a semantic correctness or completeness
certificate. Unknown syntax can leave claims undiscovered, and a schema-compatible pair
can still be wrong. The truth evaluator, typed-value interpretation and claim generator
remain separate future components.
