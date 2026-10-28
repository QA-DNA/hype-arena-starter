---
name: hype-arena-evidence-policy
description: Implement or review Hype Arena ingestion, typed extraction, temporal evidence, row verdicts, claim generation, and offline packaging while preserving the project's evidence policy and submission contract.
---

# Hype Arena evidence policy

Use for the Hooly inference system. Repository contracts define the submission interface; the user's supplied pipeline rules define the conservative evidence policy below. Read the relevant contract before changing a component. Surface conflicts rather than silently weakening evidence rules to increase coverage.

## Sources and extraction

- Read `README.md` and `contracts/README.md` from the project root. For generation, also read `contracts/claim-forms.md`, `contracts/value-forms.md`, both JSON schemas in `contracts/`, and their good/bad examples.
- Hooly is a fictional closed universe. External knowledge supplies no world facts. The lexicon supplies entity names, aliases, attributes and event identities, not unstated values or persistence guarantees.
- Use practice forms across all labels as build-time parser supervision. Only trusted true observations become positive world evidence. Verify synthetic annotations before freezing resources; synthetic facts never become world evidence.
- Preserve supplied text, labels, dates and IDs as immutable sources with provenance. Recover packaged practice forms only after matching an ID/text/date fingerprint; a reused ID alone is insufficient.
- Resolve longest whole-name/alias spans first. Distinguish the entity mentioned from the assertion's subject. Score pronoun/context candidates and retain unresolved alternatives. Nearby rows supply context only when compatible; bound fallback searches by date and semantic compatibility.
- Extract money, counts, physical quantities, durations, percentages, dates, versions, names and Boolean polarity. Preserve operators, date precision, units, currency and price period. Use Decimal for exact arithmetic and attribute-specific cues to separate observed metrics from targets and similarly named attributes.
- Split compound assertions while retaining Boolean composition. Source sentences may contain quotations and incidental words; generated-claim grammar must not become the sole source parser.

## Evidence and temporal reasoning

- A true row supports every annotated assertion. A false row establishes that at least one required assertion fails; it does not negate every atom.
- A false single-atom numeric assertion excludes that predicate without supplying the correct value. Invert a false Boolean assertion only when subject, attribute, time, scope and interpretation are unambiguous.
- Keep false compound rows as constraints. Propagate only sound deductions, such as the remaining false atom after all other required atoms are proved true. Unsure and unlabelled rows supply no positive facts by default.
- Query evidence at the row's date and model effective boundaries explicitly. Prefer same-date observations and stated effective dates. Separate stable facts from changing metrics, documenting any persistence assumption.
- Do not silently carry forward the nearest value or treat equal observations surrounding a gap as proof of continuity. Preserve temporal conflicts and missing intervals.
- For required conjunctions, emit false if any required atom is proved false, true if every required atom is proved true, otherwise unsure. Preserve actual Boolean semantics for other compositions. Track parsing failure, missing evidence, world uncertainty and temporal conflict separately in traces.
- Classifier confidence and retrieval similarity are not proofs of world truth. Separate extraction uncertainty from evidence support; calibrate reported confidence on held-out evaluations.

## Generation and output

- Enumerate supported structured claims before rendering text. Retain proof traces and apply schema, lexicon, grammar, text/form agreement, novelty and truth gates before selection.
- `fact` and `compare` use 29 October 2026, the contract's as-of date. `at_event` uses the named event's supported date; `change` requires ordered observations; `relation` requires overlapping support for the link and target attribute.
- Target exactly 1,000 valid new claims distinct from input text. Never invent evidence or bypass gates to fill a shortfall; surface insufficient supported candidates during development.
- Validate input headers and IDs. Label only runtime rows with empty labels. Enforce the contract's CSV columns, IDs, lengths, label/confidence rules and 16 MiB output limit.
- Save a complete snapshot to a temporary name in `/output`, then atomically rename it to `/output/output.csv`. Respect `ARENA_DEADLINE` and reserve time for generation, validation and saving.

## Implementation and verification

- Start with Python CSV/JSON, compiled regexes, dictionaries, sorted histories, Decimal and local JSON Schema references. SQLite is optional; writable databases belong in memory or `/output`. Add offline TF-IDF/linear classifiers or a small CRF only where measured extraction errors justify them. Avoid runtime LLMs, graph databases, agent frameworks, all-pairs sentence inference and runtime large-model training.
- Share one inference library between a terminating batch CLI and a small live API. The frontend accepts sample-shaped rows, shows results and internal traces, and displays the architecture diagram.
- Package runtime resources. Build linux/amd64; end the Dockerfile with `USER 10001`. Support offline execution, read-only root, no home directory, 2 CPUs, 6 GiB RAM, 256 processes/threads, writable `/tmp` (128 MB) and `/output` (256 MB), and an unpacked image at most 3 GiB. Configure library caches under `/tmp` or prepackage them.
- Benchmark the actual constrained image. 20,000 rows in 30 minutes gives roughly 90 ms per row before generation/output reserves, not a measured performance guarantee.
- Test evidence invariants, boundary dates, false compound rows, reused IDs, numeric units/operators, ambiguity and CLI/API parity. Keep paraphrase/template families together in evaluation splits; distinguish parser generalization from retrieval of packaged practice annotations.
- Once an image exists, run `scripts/check.sh` plus local schema and generated-text checks: the supplied checker omits some claim validity gates. Its hidden-label score is an upper bound when practice labels are packaged.
