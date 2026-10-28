# Reviewed unlabelled demonstration

Task: presentation / LLM review demo. Agent owner: llm_demo_review; human owner
unassigned. Base: df5556a. Scope: these four demo files only. Acceptance: 20 novel
four-column CSV rows with empty labels, separately cited development-time reference
annotations, valid dates/source IDs, and a clear distinction from measured truth.

[reviewed-unlabelled.csv](reviewed-unlabelled.csv) is the file to download and upload
into the local workbench. It has exactly `id,text,date,label`; every label is empty
and no form or expected answer is included. Run it through the normal Rust pipeline.

[llm-reference.json](llm-reference.json) holds separate provisional reference labels,
brief reasons, source row IDs, source SHA-256 hashes, construction provenance and
input hash. [llm-reference.csv](llm-reference.csv) is the human-readable reference
export. The references contain eight true assessments, eight false and four unsure.

The LLM reviewer used only trusted true observations from the public practice data
and the supplied lexicon. The first sixteen cases are novel paraphrases or exact
value contradictions on their source date. The other four check missing knowledge
and the distinction between a lower bound and an exact count. References were fixed
before running the solver on this fixture. No model was tuned against this demo.

The comparison metric is **agreement with the LLM review**. These labels are not
organizer-certified ground truth. This curated, practice-derived fixture is not an
independent unseen benchmark, and agreement does not measure calibration. Neither
reference labels nor this file are included in model training. There is no LLM call
at runtime, and a model's background knowledge was not used as Hooly evidence.

Validation completed with Python standard-library CSV/JSON/date/hash checks: exactly
20 unique IDs and novel normalized texts; all 20 labels blank; valid dates; CSV
round-trip; references aligned; eight/eight/four distribution; every source exists,
is true, and has the same observation date as its demo claim. The eight factual
source keys have no conflicting true value on that date. No model prediction or
accuracy result is claimed by this artifact-only task. Organizer files are unchanged.
