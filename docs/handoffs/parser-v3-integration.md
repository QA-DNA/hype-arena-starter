# Parser V3 integration

- Status: active, 29 October 2026.
- Human owner: unassigned. Coordinator: Codex, Run `run_f81fd1639515`.
- Authorization: Teodor requested implementing a cleaner, substantially better
  parser, investigating failures, and using parallel isolated agents as needed.
- Base: `22fa97b6fe27fcfa8d0bab7ae2e85c10c5386148`.
- Integration branch: `teodorbalan/parser-v3-integration`.
- Integration paths: core context/program exports and exact evaluation, CLI
  routing, runtime research adapters, integration tests and documentation.
- Binder worker: `parser-v3-binding`, `structured.rs` and its isolated tests.
- Program worker: `parser-v3-program`, new `claim_program.rs` and isolated tests.
- Independent evaluator: `parser-v3-evaluation`, challenge factory/scoring and
  adversarial review only. No production parser imports in its oracle.

## Acceptance and data boundary

Preserve organizer files, offline CPU operation and the frozen selected-v2 model.
Keep parsing independent of evidence truth, labels and private target fields.
Preserve logical structure rather than flattening disjunction/negation into a
conjunction. Resolve ownership through wording, legal attributes and explicit
document context; ambiguous references stay unresolved. Context must not cross
documents or become trusted factual evidence. Bound input size, memory and depth.

Compare against the original parser on released development examples and public
practice, retaining regressions. Keep new final challenge wording/gold separated
until implementation freeze; report parser structure/status independently from
truth classification. Prior 87.58% and million-pool scores remain historical
measurements and cannot be silently reused as fresh scores for this version.

The coordinator records final interfaces, measured improvements, validation and
remaining limits here after all worker deliveries and independent checks settle.
