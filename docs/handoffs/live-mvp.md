# Live MVP task agreement

Task: live-mvp, authorized by Teodor on 2026-10-28. Base: e79e83c.
Human ownership remains unassigned. Integrator: root agent.

| Agent | Isolated checkout | Paths | Acceptance |
| --- | --- | --- | --- |
| Engine | mvp-engine | core engine.rs and forest.rs | Mihai analysis reused, actual seeded CPU forest, extracted facts, sourced evidence and uncertainty |
| Claims/runtime | mvp-claims | core claims.rs and io.rs, CLI | MMR selection, contract CSV and atomic output, 1,000 evidenced candidates when available |
| Web | mvp-web | apps/web | Real jobs, CSV upload, scores, evidence, architecture and stack diagrams |
| Contract review | mvp-contract-review | core claims and independent diagnostic | Schema, lexicon, newness, grammar subset and provenance checks |
| Docker QA | mvp-docker-qa | benchmark wrapper and handoff | Full 20,000-row offline container run and failure paths |
| Integrator | primary checkout | shared types, API, Docker, documentation | Bounded live jobs, container parity checks and end-to-end validation |

The shared types are in crates/core/src/model.rs. Staged interfaces:

- engine::Engine::new(practice: &[InputRow], lexicon: &serde_json::Value) -> Result<Self, String>
- Engine::predict(&self, rows: &[InputRow]) -> Vec<Prediction>
- io::read_csv(text: &str) -> Result<Vec<InputRow>, String>
- io::output_csv(predictions: &[Prediction], claims: &[Claim]) -> Result<String, String>
- claims::generate_claims(rows: &[InputRow], predictions: &[Prediction], lexicon: &serde_json::Value, limit: usize) -> Result<GenerationReport, String>

The API uses POST /api/runs {csv?: string, generate?: bool}; omitted CSV uses practice with every fifth label hidden. GET /api/runs/current returns a bounded job snapshot: id, status (idle/running/complete/error), progress 0..100, stage, logs [{time,message}], results [Prediction], generation GenerationReport, summary object, error optional string. GET /api/runs/current/output.csv downloads the finished contract CSV. GET /api/dataset returns source rows and summary. POST /api/runs performs actual CPU work in a blocking worker; progress changes only at completed processing stages.

Scores must be labelled model estimates. Practice demo includes familiar training rows and does not measure generalization. Page observation dates do not prove current truth. Organizer files remain unchanged. Runtime has no LLM or network dependency.

## Delivered and verified

Status: implemented. Primary branch: `mvp/live-workbench`. Start locally with
`docker compose up -d --build`; open http://127.0.0.1:8787. No host Rust or Node is
needed for this path. Docker Desktop was already running on the laptop.

- `cargo xtask check`: passes formatting, Clippy with warnings denied, document links,
  graph validation and organizer snapshot hashes.
- `cargo xtask test`: 20 tests passed across API, CLI, core and tooling.
- `tools/arena-check.ps1 -SkipBuild`: actual offline, read-only, UID 10001 execution
  passed the unchanged official output checker. 380 hidden rows: 373 correct, zero
  incorrect, seven unsure; exactly 1,000 claims from 1,315 candidates. These are
  familiar practice rows, not an unseen accuracy result.
- Live HTTP run: 1,897 rows, 2,402 extracted assertions, 1,000 claims, five real
  processing logs and a complete downloadable CSV. Concurrent jobs are rejected
  with 409. The web and CLI output CSVs are byte-identical (269,419 bytes).
- `tools/validate_claims.py artifacts/final-live/job.json`: all 1,000 entries pass
  organizer JSON schemas, lexicon checks, normalized newness, selected public grammar
  conditions and 1,960 source references. This is not the organizer's private referee.
- Real Chrome flow passed Run, upload, inspect, claims, download and malformed input;
  untrusted HTML stays text. Desktop 1440 px and mobile 390 px have no horizontal
  overflow or JavaScript errors. Screenshots retained in ignored `artifacts/web-qa/`.
- Final container stress run: 20,000 rows, 18,103 unknown, 4.373 seconds application
  time, 803,789-byte output, 1,000 claims, about 117.3 MiB cgroup peak memory, no OOM.
  The synthetic near-template input measures throughput, not correctness.

The local image uses about 120 MB, below the 3 GiB ceiling. Competition runtime has
network disabled; the separate web container publishes only the laptop's loopback
HTTP port. Both use the same core and 2 CPU / 6 GiB limits.

## Quality limits and continuation

The 380-row diagnostic holdout removes test text, labels and forms from training;
shared templates and facts remain. Accuracy is 80.26%, macro-F1 0.335, and non-abstaining
coverage 93.95%. Majority accuracy is 85.26%, macro-F1 0.307. False and unsure recall
remain weak; this is a statistical baseline, not a finished competition model. The
holdout informed tuning and is not an independent final evaluation.

Mihai's actual alias matcher is ported from commit `4478b99`. Details and reproducible
diagnostics are in [engine handoff](mvp-engine.md). Generation assumptions are in
[claims handoff](mvp-claims.md); independent checks in
[contract review](mvp-contract-review.md); browser checks in [web handoff](mvp-web.md).
Model scores and generated-claim confidence are estimates. Schema/provenance checks
do not prove every hidden temporal truth or every private referee grammar rule.

Next engineering work: improve false/unsure recognition and extraction on independent
chronological and subject holdouts, then run the organizer's new sample when published.
No remote push, submission PR or server deployment was performed.
