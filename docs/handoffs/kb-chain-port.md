# T3: Rust port of the knowledge-base chain (F2 temporal chain + G1 guard)

- Status: review (parity, G1, router, per-key budget and unknown guards done; enabling it in the competition image
  is a team decision)
- Human owner: unassigned
- Agent role, if used: worker T3 (implementation), dispatched by the KB campaign orchestrator
- Branch and checkout: `worktree-agent-aebb33382791bdb54`, isolated worktree; not pushed
- Base commit: `e6f687c`
- Authorized scope and paths: `crates/core/src/kb_chain.rs` (new), `crates/core/src/lib.rs`,
  `crates/core/src/engine.rs` (the exact practice lookup moved into `Engine::practice_match`, behavior unchanged),
  `crates/cli/src/main.rs` (switch only), `crates/core/tests/kb_chain_parity.rs` and `crates/core/tests/data/`,
  `labs/kb-campaign/F2/export_rust_fixture.py`, this handoff. No organizer file touched.
- Acceptance criteria: every practice label and every Sdev refit-track label identical to the Python reference and
  every confidence within 1e-9; OFF by default with byte-identical output when off; with the switch on, the engine's
  labels stay untouched unless the router picks the chain; no chain failure can empty `output.csv`;
  `cargo xtask check` and `cargo xtask test` pass.

## Delivered change

[kb_chain.rs](../../crates/core/src/kb_chain.rs) is a safe-Rust port of the winner of the
[knowledge base campaign](../research/kb-campaign.md): `F2/f2var.py:Chain {"d0":0.03,"engine":"viterbi",
"eps_a":0.0005,"mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}` with the `Std` defaults (isotonic fact map, product
over the row's facts, isotonic row map, arena rule). No new dependency; the isotonic fit is written out (sorting,
sklearn's `_make_unique` merge within 1e-15, the scipy PAVA block arithmetic, `np.interp`).

- **Facts and keys** follow `labs/kb-campaign/harness/world.py:Fact`, not `typed.rs`: subject resolved through the
  lexicon names and aliases (`truth.alias_map`, whitespace-free lowercase), attribute lowercased with runs of
  whitespace and hyphens turned into `_`, key = (subject, attribute, kind, unit dimension). Numbers are floats
  rounded to six decimals for state identity; the ten harness units (KB to TB, ms to week) fold into `data` / `time`,
  any other unit stays its own dimension; money keys carry (currency, per). Agreement is interval overlap with the
  harness's 1e-9 tolerance; dates are partial ISO intervals; names fold through the lexicon aliases; versions compare
  case-folded with a numeric order of their digit groups. An atom the harness would drop (unreadable value, unknown
  kind or operator) is dropped. `typed.rs` uses exact rationals and wider unit tables, so reusing it would break parity.
- **Chain**: per-kind hazard by maximum likelihood on consecutive true anchors (160-point grid, prior 1/200 per day),
  per-kind downward-switch weights with the Beta prior, Viterbi max-marginals with the fact's own page removed,
  margin clipped to [-60, 60]; keys seen on one page only give no score (NaN). Float operations keep numpy's order,
  including its pairwise summation.
- **Decision**: fact isotonic map (NaN score gets the smoothed no-evidence rate), product per row, row isotonic map,
  `|pc - 0.5| < band` unsure, else true at `pc >= 0.5`; confidence `max(0.5, (1 - u) p)`; rows without facts unsure.
  `kb_chain::run(rows, fallback)` fits on the labelled rows; when they are one-class it fits on `fallback` (practice,
  every row labelled) and applies that model, as `Std.fit` does.
- **Shipped labeller** `kb_chain::guarded` (the T2 G1 specification): the chain, then every unlabelled row with no
  parsed fact becomes true with confidence `max(0.5, rate)` (rate = true share of all labelled rows of the fitted
  world), then every decided confidence is multiplied by the practice-fitted constant `CONF_SCALE = 0.972343066499685`
  and clipped to [0.5, 1].
- **Pipeline switch**: `VERIDYCT_KB_CHAIN=1` (environment, like the other `VERIDYCT_*` options), read in
  [main.rs](../../crates/cli/src/main.rs). Off (unset or any other value) the code path is skipped. On,
  `kb_chain::relabel` runs after claim generation (claims are unchanged) and either keeps the engine's predictions or
  replaces label, confidence, probabilities and reason of the unlabelled ones. Facts: a labelled row's own form (the
  embedded practice gold form for practice texts, which the CLI already substitutes), otherwise `Prediction.facts`,
  the facts the engine used for that row (native/structured parser output when configured, otherwise the engine's
  template extraction; rows the parser marked recognized-empty have none and fall to G1). Pages are runs of
  consecutive input rows with the same date and labelled status. To enable it in the image, add
  `VERIDYCT_KB_CHAIN=1` to the `ENV` of `Dockerfile.competition` or pass `-e VERIDYCT_KB_CHAIN=1`.
- **Router** (`kb_chain::relabel`): the chain is used only when the engine's canonical practice seed is present and
  the labelled rows hold both `true` and `false`. The seed signal is `Engine::canonical_seed_present`
  ([engine.rs](../../crates/core/src/engine.rs)): every practice example (normalized text and date) appears in the
  runtime rows with an empty label or the same label. The CLI computes it once, logs "Canonical seed present in
  runtime universe", and writes it as the field `canonical_seed` of the `VERIDYCT_DIAGNOSTICS=1` JSON. Otherwise the
  engine's predictions are kept unchanged, so `output.csv` is byte-identical to the switch off. Reason: end-to-end
  runs of the real binary showed the chain ahead on the practice-seeded world (0.790 against 0.741 points) and neutral
  on the 20k suite worlds, but far behind the engine on every world without the seed (-0.04 to -0.33 points against
  +0.83 to +1.00), where the anchors are one class, intervals are explicit and unknowns are stated. The engine is also
  kept when the chain returns no two-class fit, returns output of the wrong length or with a confidence outside
  [0.5, 1], or panics: the chain runs inside `catch_unwind`, predictions are written only after its whole output
  validates, and the CLI wraps the router in a second `catch_unwind` that restores the engine's predictions (the
  release profile does not set `panic = "abort"`). Before the router runs, the CLI writes the engine's `output.csv`
  atomically, then replaces it atomically with the routed result, so a kill, timeout or allocator abort inside the
  chain leaves a complete engine output on disk; with the switch off there is no extra write. One stderr line
  "Labeller: ..." names the labeller, the reason, the rows kept and the load (largest key state count, world sums of
  S*n and T*S^2), and the diagnostics JSON gets the same text as `labeller` when the switch is on.
- **Engine guards kept per row**: an unlabelled row the parser marked `explicit_unknown` keeps the engine's
  prediction (the engine abstains on it; G1 would have made an empty-fact unknown true), and a row marked
  `incomplete` keeps it when the chain would call it true (a parsed subset cannot prove the whole conjunction, as in
  the engine; a chain false or unsure stands). An unlabelled row whose normalized text and date equal a labelled
  embedded practice example keeps the engine prediction too: the engine answers it with that example's known label
  through the same lookup (`Engine::practice_match`, the CLI passes it to the router), so this is the gold label of
  the identical statement, not a fit to practice. Practice has no explicit-unknown phrase and the parity fixtures do
  not go through the router, so parity is unaffected.
- **Router-only rules** (in `kb_chain::relabel`; `run`, `guarded` and every parity fixture are unaffected):
  FOREIGN sets an unlabelled row unsure when its text has an unknown capitalized word and mentions no lexicon
  name. Names are every lexicon JSON string (keys included) that starts with an ASCII uppercase letter and has at
  least 3 characters; a capitalized word (`[A-Z][a-zA-Z]{2,}` as a whole word) is unknown when it is not a
  capitalized word of a labelled row or a name, and neither its lowercase form nor that form without one trailing
  `s` is a word of those texts; a mention is a lowercased name in the lowercased text with no word character on
  either side. Reason text: "KB: names an entity outside the lexicon and the labelled rows; the dataset gives no
  means to tell." Practice match and explicit unknown take precedence. NOEVID (`NOEVID_UNSURE`, one-line switch,
  currently true) sets an unlabelled row with facts but no fact evidenced from another page unsure. Every decided
  confidence the router writes is rounded to one decimal and clipped to [0.5, 1]. The "Labeller: ..." line counts
  the foreign rows.
- **Budgets**, checked before any dense matrix is built: a key holds S states (distinct equality values plus "other")
  over n facts and T dates; its S x n agreement matrix lives until the world is scored, scoring it briefly needs about
  3Sn + 3ST more floats, and its Viterbi passes cost 2TS^2 steps. Per key: S > `MAX_KEY_STATES` (1,024, counted with
  an early exit), S(n + T) > `MAX_KEY_CELLS` (2^22) or TS^2 > `MAX_KEY_STEPS` (2^30) skips the key. Per world, keys
  are admitted cheapest first (by TS^2, then Sn, then first appearance) while the running sums stay within
  `WORLD_CELLS` (2^25 cells of S x n, 256 MiB) and `WORLD_STEPS` (2^33 steps of TS^2, under 30 s at the 2 to 3.2 ns
  per step implied by the Opus single-key timings below); the rest are skipped, so many keys each just under the
  per-key caps cannot add up to a blowup and a few huge keys cannot crowd out ordinary ones. A skipped key's rows
  are `over_budget`, `guarded` returns None for them and the router keeps their engine predictions. Measured world
  sums (S*n, T*S^2): practice folds at most 8,165 and 28,055; P390 with the production parser 8,264 and 29,673;
  Sdev refit world 157,551 and 811,021; suite worlds with the engine's own extraction (seed check bypassed in a measurement build only) at most 38,219 and 251,108 (calibration-20000; development-20000 32,230 and 187,066, sealed-20000 24,941 and 141,722, diagnostic-6000 3,561 and 13,936). Cells stay at least 200 times and steps at least 10,000 times under the
  budgets. Measured maximum S: 7 on the practice folds, 18 on the Sdev refit world (gold
  forms) and 18 on the suite worlds with the pipeline's own extraction (development-20000 15, calibration-20000 18, sealed-20000 16, diagnostic-6000 8, the three external worlds 10 to 15; measured with the seed check bypassed in a measurement build only). The cap is 57 times that maximum. Opus measured 1,000 states at 4.5 s, 2,500 at 49.5 s and 5,000 at 243 s and 1.1 GB. Without the cap, 18,000 distinct values on one key need about 7 GiB.
- **Extension point**: `ChainOutput` exposes per fact the chain score (NaN without other-page evidence), the most
  likely value of the key at the row's date with the own page removed (`best_values`), the row product and an
  `evidence` flag, so further guards (re-read, no-evidence) can be added after `guarded` without touching the chain.

## Verification

Compiled and run on a Linux x86-64 CPU box (AMD EPYC 7742), Rust 1.90.0, release profile for the parity runs.

| Check | Command | Result |
| --- | --- | --- |
| Practice parity | `cargo test -p veridyct-core --release --test kb_chain_parity -- --nocapture` | P80 folds 0-4 and P10 seeds 0-2: 7,021/7,021 labels identical, max confidence difference 2.2e-16 |
| Rust points | same | P80 pooled 0.8492; P10 mean 0.7678 over seeds 0-9 |
| Sdev refit-track parity (local suite data) | same, `VERIDYCT_KB_CHAIN_SDEV=<export>` | chain fitted on that world's own labels (the campaign's refit track, not the practice-transfer track): 18,103/18,103 labels identical, max difference 2.2e-16; 0.05 s for 20,000 rows; max key states 18 |
| G1 specification | `guarded_labeller_matches_spec_g1` | 390/390 P390 rows: label and scaled confidence equal to 4 decimals |
| One-class fallback | `one_class_world_uses_the_practice_fit` | none without fallback; practice rate and confidences in [0.5, 1] with it |
| Router | `kb_chain::router_tests` | chain on practice with the seed (every target relabelled); engine unchanged without the seed and on a one-class world; engine unchanged when the chain panics, returns None, a confidence of 0.3 or the wrong length |
| Engine guards | `explicit_unknowns_and_incomplete_rows_keep_the_engine` | an empty-fact explicit unknown (true under G1 without hints) and an incomplete row the chain calls true keep the engine prediction |
| Explicit-unknown repro, real binary | practice plus `x,"Holdan team size is explicitly unknown.",2026-10-29,` with the image's parser settings (native extractor, structured parser, exact-length batching) | parser marks `x` explicit unknown; engine `unsure`; switch on: "kept 1 engine rows" and `x` stays `unsure` |
| Per-key budget | `a_high_cardinality_key_keeps_the_engine_and_finishes_fast` | practice plus 18,000 rows with distinct values on one key: those rows keep the engine, the rest is relabelled, under 0.4 s in release |
| World budgets | `world_budgets_skip_the_later_of_many_large_keys` | 200 keys of 1,024 states over 365 dates (each within the per-key caps): the first 22 are admitted, the other 178 skipped, an ordinary key that appears last is still admitted, both sums within budget |
| Practice matches | `exact_practice_matches_keep_the_engine` | every target an exact practice match: nothing relabelled, predictions unchanged |
| Every-fifth, real binary | practice with every fifth label hidden, embedded practice intact, production parser and verifier, switch on | "kept 380 engine rows"; 380/380 correct, as production |
| P390, real binary | T1's P390 build (embedded practice = the 1,507 training rows), production parser and verifier, switch on | relabels 387, keeps 3 (explicit unknown or incomplete; none of the 390 is an exact match); `output.csv` sha256 `e348c8576faed95836e25250e8316e82b99600905686f98ff0e4a545536197e3`, identical to the `3369ee7` build |
| FOREIGN | `foreign_rows_are_names_outside_the_lexicon_and_the_labelled_rows`, `foreign_unlabelled_rows_become_unsure` | 20 sample texts: the 9 naming entities outside practice and the lexicon flagged, the 11 others not; 0 practice rows flagged with practice as the labelled set; a flagged target becomes unsure with no confidence |
| NOEVID and rounding | `rows_without_other_page_evidence_become_unsure`, `router_uses_the_chain_with_the_seed_and_two_classes` | a fact on a key no other row has (NaN score) gives unsure; router confidences are multiples of 0.1 in [0.5, 1] |
| FOREIGN, real binary (before NOEVID and rounding) | production parser and verifier, switch on | practice plus the 20 sample rows: 9 foreign rows unsure, the 11 others labelled; P390: 5 of the 390 flagged (all gold true), points 0.7769 and accuracy 0.8821 against 0.7897 and 0.8949 without the rule; every-fifth: `check_output.py` 380 of 380 labelled, 373 right, 0 wrong, 7 unsure, format checks pass |
| Workspace | `cargo xtask check`, `cargo xtask test` | both pass on Apple silicon with Rust 1.90.0 (94 tests, 0 failed) |

The practice fixture [kb-chain-practice.txt](../../crates/core/tests/data/kb-chain-practice.txt) (labelled-page
masks for P80 folds 0-4 and P10 seeds 0-9, expected predictions as f64 bits for the folds above, 204 KB) is
regenerated by [export_rust_fixture.py](../../labs/kb-campaign/F2/export_rust_fixture.py) with the lab's Python 3.12,
numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1 on Apple silicon. The Sdev refit-track export holds suite data and
stays out of Git (`--sdev OUT`). [kb-chain-g1-p390.jsonl](../../crates/core/tests/data/kb-chain-g1-p390.jsonl) is the T2
specification table trimmed to id, extracted form and expected outputs; its forms come from the practice-trained
neural extractor run on the practice texts (T2 `spec_dump.py`).

The P10 mean differs from the campaign's Apple-silicon number (0.7673) and equals its x86 number (0.7678). Against
the Python reference run on the same x86 box (all ten P10 seeds, exported with the lab venv), the Rust build gives
16,950/16,950 identical labels and a maximum confidence difference of exactly 0. Against the Apple-silicon reference,
seeds 0-7 and 9 match (differences up to 9e-16) and seed 8 differs on 14 rows near the decision point: the reference
itself changes between hosts (libm and fused multiply-add rounding move a tie in an isotonic fit), not the port.

Pipeline runs on the suite's 20,000-row development universe (1,897 labelled, 18,103 targets), release build,
`taskset` to 2 cores, `/usr/bin/time -v`, no native extractor configured (engine template extraction):

| Run | Wall | Peak RSS | Output |
| --- | ---: | ---: | --- |
| base `e6f687c`, switch unset | 9.82 s | 65.7 MB | sha256 `d565e862361abdab0c19887805c74952117b742ad9524ef807e3ffbfb1ce60f5` |
| this branch, switch unset | 9.89 s | 65.9 MB | byte-identical to base (`cmp`, same sha256) |
| this branch before the router, `VERIDYCT_KB_CHAIN=1` | 9.83 s | 74.0 MB | chain relabelled 18,103 rows in 0.045 s |
| this branch with the router, `VERIDYCT_KB_CHAIN=1` | 9.98 s | 81.6 MB | "Labeller: evidence engine (canonical practice seed absent)" (the extra RSS is the copy of the engine predictions kept to restore them on a panic); byte-identical to the switch off (`cmp`, same sha256) |

All runs end with the existing "fewer than 1,000 evidenced claims" error on this non-canonical world (101
claims), unchanged by the switch; the CSV is written before it. Scored against that world's gold (a test, never used
for a choice): engine 0.060 points / 6.7% accuracy (17,137 unsure), chain + G1 before the router 0.705 points / 85.1%
accuracy. These forms are the engine's template extraction, not the competition image's neural parser. The world
has no canonical seed, so the router now keeps the engine there; the earlier chain result on this world is not a
reason to bypass the router, because the same rule loses on every other seedless world measured end to end.

## Known differences from the Python reference

Only inputs that do not occur in practice or the suite worlds: ISO week dates (`2024-W01-1`) are dropped instead of
parsed; strings with underscores (`"1_000"`) are not read as numbers; a string value with a unit factor other than 1
is dropped (Python repeats the string); version digit groups are ASCII only; case folding covers the common
differences from lowercase (sharp s, final sigma, long s, micro) rather than the full Unicode table; Python's
`isspace` and Rust's whitespace differ on a few control characters; non-string lexicon events are ignored; values
Python cannot hash (lists, objects) are dropped where the harness would raise. Outputs on every fixture are identical.

## Known limitations

- With the switch on, the organizer checker's score is inflated: its hidden practice rows get their gold forms
  through the CLI's exact-text match, so the chain reads the answer key's facts for them. Use worlds the practice
  file does not contain for an honest estimate.
- Pages are runs of consecutive input rows (same date, same labelled status). A shuffled `universe.csv` breaks those
  runs into single rows and weakens own-page exclusion. Measured separately; `pages_of` is unchanged here.

## Open questions and next step

- The fresh-universe case (every anchor true) uses the practice fit as `Std.fit` does; the sample check covers its
  contract, not its accuracy.
- The P10 difference between Apple silicon and x86 is a host property of the reference, not of the port: the Rust
  build on x86 reproduces the x86 reference bit for bit on all ten seeds. The committed fixture is the Apple-silicon
  export of the requested folds (P80 0-4, P10 0-2), which the x86 build also matches.
- Timing was measured without the native extractor, so the wall time is the engine's, not the image's; the chain's
  own share is under 0.05 s and about 8 MB.
- Next: the team decides whether to set `VERIDYCT_KB_CHAIN=1` in the competition image, then rebuilds and reruns the
  organizer checker on the image.
