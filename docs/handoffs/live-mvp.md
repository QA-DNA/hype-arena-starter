# Live MVP task agreement

Task: live-mvp, authorized by Teodor on 2026-10-28. Base: e79e83c.
Human ownership remains unassigned. Integrator: root agent.

| Agent | Isolated checkout | Paths | Acceptance |
| --- | --- | --- | --- |
| Engine | mvp-engine | core engine.rs and forest.rs | Mihai analysis reused, actual seeded CPU forest, extracted facts, sourced evidence and uncertainty |
| Claims/runtime | mvp-claims | core claims.rs and io.rs, CLI | MMR selection, contract CSV and atomic output, 1,000 evidenced candidates when available |
| Web | mvp-web | apps/web | Real jobs, CSV upload, scores, evidence, architecture and stack diagrams |
| Integrator | primary checkout | shared types, API, Docker, documentation | Bounded live jobs, container parity checks and end-to-end validation |

The shared types are in crates/core/src/model.rs. Staged interfaces:

- engine::Engine::new(practice: &[InputRow], lexicon: &serde_json::Value) -> Result<Self, String>
- Engine::predict(&self, rows: &[InputRow]) -> Vec<Prediction>
- io::read_csv(text: &str) -> Result<Vec<InputRow>, String>
- io::output_csv(predictions: &[Prediction], claims: &[Claim]) -> Result<String, String>
- claims::generate_claims(rows: &[InputRow], predictions: &[Prediction], lexicon: &serde_json::Value, limit: usize) -> Result<GenerationReport, String>

The API uses POST /api/runs {csv?: string, generate?: bool}; omitted CSV uses practice with every fifth label hidden. GET /api/runs/current returns a bounded job snapshot: id, status (idle/running/complete/error), progress 0..100, stage, logs [{time,message}], results [Prediction], generation GenerationReport, summary object, error optional string. GET /api/runs/current/output.csv downloads the finished contract CSV. GET /api/dataset returns source rows and summary. POST /api/runs performs actual CPU work in a blocking worker; progress changes only at completed processing stages.

Scores must be labelled model estimates. Practice demo includes familiar training rows and does not measure generalization. Page observation dates do not prove current truth. Organizer files remain unchanged. Runtime has no LLM or network dependency.
