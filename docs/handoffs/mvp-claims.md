# MMR generation and arena runtime handoff

Task: live-mvp / claims-runtime. Agent owner: claims_runtime. Human owner unassigned.
Base: e79e83c; shared interface commit cherry-picked as 3a852e6.

Implemented core `claims::generate_claims`, `io::read_csv`, `io::output_csv`, and the real CLI `run` adapter. Root integrator adds module exports and resolves shared Cargo lock.

The generator trusts only explicitly true source observations and evidence carrying true source labels. It creates chronological changes without asserting change dates, immutable historical-date facts and unordered comparisons, event facts supported on the exact independently verified event day, and relations with same-day link/target evidence. Forecast-only dates and conflicting historical dates do not license immutable facts. Model-predicted truth is never accepted as generation evidence. MMR deterministically balances evidence confidence (0.78) and maximum token redundancy (0.22), with text/form deduplication and source references.

On practice data: 1,316 candidates; 1,000 selected = 673 compare, 233 change, 41 fact, 37 at_event, 16 relation. No reversed equivalent comparisons or fabricated padding. Scores are engineering estimates rather than independently calibrated truth probabilities. Immutable historical-date reasoning assumes confirmed past launch/join/founding/event dates remain historical facts; hidden-universe truth is not guaranteed by schema validation.

CLI `run` defaults to `/universe/universe.csv`, `/universe/lexicon.json`, `/output/output.csv`, supports `--input`, `--lexicon`, `--output`, checks `ARENA_DEADLINE` before work and after training, and atomically renames a complete CSV within the output directory. A short claim inventory is preserved as partial output and returns exit 2. The bundled practice dataset is allowed by the official contract; familiar-row performance is not generalization performance.

Validation performed in Docker `veridyct:dev` with an isolated Cargo harness: six semantic tests passed initially, including full practice inventory; Clippy all-targets with warnings denied passed after fixes. All 1,000 generated entries passed the organizer JSON entry/value schemas using Python jsonschema. A full-inventory regression is now also in the core test module. The CLI requires integrated Engine exports and still needs the integrator's full container/checker execution. Grammar validity is implemented from the published forms but no private referee was available.

Ignored artifacts under this checkout's artifacts/ include the independent harness, generated claims JSON and output CSV. Organizer files were not changed.
