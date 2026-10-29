# KB temporal chain: verification record (29 Oct 2026)

Scope: how `crates/core/src/kb_chain.rs` (switch `VERIDYCT_KB_CHAIN=1`) was checked before the 11:00 freeze.
Design and port notes are in [../handoffs/kb-chain-port.md](../handoffs/kb-chain-port.md) and are not repeated here.
Points are the arena score per row (+1 right, -1 wrong, 0 unsure); accuracy is the share of correct labels.
All runs used a 256-core CPU development server and a local Mac. Anything not measured is marked "not verified".

## 1. Summary

- What ships: with the switch on, the temporal chain relabels target rows after the evidence engine has run.
  The switch is off by default; with it off, `output.csv` is byte-identical to the previous build (checked on P390 and dev).
- Empty-extraction rule (G1): a target row with no extracted fact is labelled `true`.
- Router: the chain runs only when the universe contains the canonical practice rows and both `true` and `false`
  labels are present. Otherwise the evidence engine labels everything. Exact practice-text matches keep the engine
  label. Explicit unknowns, incomplete clauses and over-budget keys also keep the engine label.
- FOREIGN rule: a target whose subject is an entity outside the lexicon and the practice rows is labelled `unsure`
  (a lowercase-anywhere vocabulary guard cuts false flags on common words). A NOEVID rule exists but is a constant OFF.
- Rounding: confidences are rounded to one decimal.
- Fail-safe: the engine's `output.csv` is written before the chain runs and replaced only if the chain succeeds;
  a panic or invalid chain output restores the engine labels.

## 2. Test sets and contamination

| Set | What it is | Contamination for the neural extractor |
|---|---|---|
| P80 | practice rows, 5 folds, 80% of anchors visible (n=1,897) | contaminated (extractor trained on practice) |
| P10 | practice rows, 10 seeds, 10% of anchors visible (n=15,276 on text tracks) | contaminated |
| P390 | 390 practice `p-` rows held out of the extractor training (1,507 rows) | tuned: checkpoint selected on these rows, so absolute numbers are optimistic |
| every-fifth | every fifth practice row hidden; the other rows embedded | contaminated: all 380 hidden rows are exact practice matches; plumbing check only |
| Suite cal, sealed, syn | three 20,000-row worlds from the suite (18,103 targets) | clean by id; 643, 647 and 855 normalized-text coincidences with the extractor's dev data |
| Suite dev | 18,103 targets | dirty: 8,088 targets are in the extractor's dev data; rescoring the other 10,015 gave 0.9862 accuracy vs 0.9749 |
| Suite diag, pilot, ext* | unsure-heavy or small worlds (334 to 4,103 targets) | clean by id |
| Fresh factory universes | generated fresh: dev (1,000 targets), 5,000 and 20,000 | clean by id |

Whether the extractor saw other wording families is not documented in its bundle (not verified).

## 3. Results

Production = the shipped CLI path with the switch off. Chain = production + chain (+G1). Format: points / accuracy.

### 3.1 Routed chain vs production (real binary, final sweep)

| Set | Production | Chain before router | Routed (final) |
|---|---|---|---|
| P390 | +0.7410 / 0.8692 | +0.7897 / 0.8949 | +0.7897 / 0.8949 |
| every-fifth | +1.0000 / 1.0000 | +0.8579 / 0.9289 | +1.0000 / 1.0000 |
| suite dev | +0.9117 / 0.9190 | +0.8961 / 0.9476 | +0.9117 / 0.9190 |
| suite cal | +0.8922 / 0.8978 | +0.8860 / 0.9413 | +0.8922 / 0.8978 |
| suite sealed | +0.8753 / 0.8832 | +0.8936 / 0.9453 | +0.8753 / 0.8832 |
| suite syn | +0.9207 / 0.9238 | +0.9111 / 0.9555 | +0.9207 / 0.9238 |
| diag | +0.9352 / 0.9383 | -0.0409 / 0.4097 | +0.9352 / 0.9383 |
| pilot | +0.3892 / 0.3892 | -0.1677 / 0.4132 | +0.3892 / 0.3892 |
| extdev / extcal / extsealed | +0.9311 / +0.9731 / +0.9042 | -0.2545 / -0.1078 / -0.2006 | equal to production |
| fresh-dev / 5000 / 20000 | +1.0000 / +0.8418 / +0.8347 | -0.3270 / -0.2604 / -0.2137 | equal to production |

- The router removes the collapse on worlds without the practice seed: all 12 foreign worlds report
  "evidence engine (canonical practice seed absent)" and their `output.csv` hashes equal the switch-off run.
  The cost: the chain's accuracy gain on the 20,000-row suite worlds (0.945 to 0.956) is also gone there.
- P390 routed: 387 rows relabelled, 3 kept by the guards (all gold `true`, labelled `true`); 0 label differences
  from the unrouted chain. The final sha sweep matches the previous one on 13 of 14 sets (every-fifth differs by design).
- Cost on P390: 7 s and 111 MB; dev 74 s and 453 MB; fresh-20000 124 s and 741 MB, equal to production.
- The official format checker passes on chain output (every-fifth: 380 hidden rows labelled, 1000 claims).

### 3.2 Chain on extracted forms (Python reference, 390 rows and practice folds)

| Set (forms) | Always-true | Production engine | Chain + G1 | Gold-forms ceiling |
|---|---|---|---|---|
| P80 (template) | +0.667 / 0.833 | +0.697 / 0.848 | +0.715 / 0.858 | +0.849 / 0.924 |
| P10 (template) | +0.662 / 0.831 | +0.634 / 0.799 | +0.671 / 0.835 | +0.767 / 0.879 |
| P390 (neural, raw) | +0.600 / 0.800 | +0.621 / 0.810 | +0.831 / 0.915 | +0.849 / 0.923 |
| P390 (production forms) | +0.600 / 0.800 | +0.741 / 0.869 | +0.795 / 0.897 | +0.849 / 0.923 |
| Suite cal / dev / sealed / syn (production forms) | +0.667 / 0.833 | +0.892 / +0.912 / +0.875 / +0.921 | +0.897 / +0.921 / +0.902 / +0.926 | +0.944 / +0.942 / +0.941 / +0.938 |

Paired differences: G1 minus engine on P80 +0.0185 (SE 0.0093); on P10 +0.0371 (seed-level SE 0.0107);
P390 production forms +0.054 (SE 0.026); P390 frozen neural forms +0.090 (SE 0.029).
G1 was pre-registered and chosen on P80 and P10 only (G1 0.6931 on the mean; the raw chain scored 0.2681).
Alternative guards (margin, cited-evidence, re-read, fitted margin) did not beat it on P390.

### 3.3 Parser context and row order (P390, final build, switch on / off)

| Context | Row order | Off | On | Row-exact extraction |
|---|---|---|---|---|
| none | document or shuffled | +0.7410 / 0.8692 | +0.7897 / 0.8949 | 314 of 390 |
| previous3text | document | +0.7667 / 0.8821 | +0.8256 / 0.9128 | 338 of 390 |
| previous3text | shuffled | +0.7128 / 0.8538 | +0.7590 / 0.8795 | 296 of 390 |

`none` is exactly order-independent. Chain row-order sensitivity with `none` (earlier build, before the router):
P390 labels unchanged after shuffling; dev and syn changed 41 and 32 of 18,103 labels (net +0.0014 and +0.0013 points).
The reason for the small effect was not investigated.

### 3.4 Unsure policies (local Python, rows scored on practice tracks and suites)

P0 = G1 only. P1 = P0 + FOREIGN. P2 = P1 + NOEVID. P3 = P2 + empty extraction to `unsure`.
Delta in points per row against P0, FOREIGN without and with the lowercase guard:

| Set | P1 unguarded | P1 guarded | P2 unguarded | P3 unguarded |
|---|---|---|---|---|
| P80 (n=1,897) | -0.0127 (28 rows flagged) | -0.0084 (16 flagged) | -0.0142 | -0.3226 |
| P10 (n=15,276) | -0.0601 (1,267 flagged) | -0.0223 (449 flagged) | -0.0604 | -0.5294 |
| P390 production | -0.0128 (5 flagged) | -0.0103 (4 flagged) | -0.0410 | -0.0949 |
| P390 neural raw | -0.0128 | -0.0103 | -0.0385 | -0.0718 |
| Suite cal / dev / sealed / syn | 0 | 0 | -0.0001 on cal and sealed, else 0 | -0.0088 / -0.0115 / -0.0145 / -0.0067 |

- Every flagged practice row is gold `true` or `false` (P390: 4 of 4 `true`), so FOREIGN can only lose points there.
  On P390 the 4 flagged rows are common-word false flags.
- Rounding to one decimal leaves points unchanged. ECE10 on P390 production moved 0.0141 to 0.0336.
- NOEVID (P390: 11 flagged, all gold `true`) and empty-to-unsure cost points everywhere, so NOEVID is off.
- Sample of 20 new rows supplied on the day (aggregate only): 10 name entities outside practice and lexicon;
  7 of those had no extracted fact (G1 gives `true`); 3 were bound onto Hooly subjects. FOREIGN flags 9 of the 20 rows
  and no row that names a Hooly entity. The orchestrator's own verdicts on the 20 rows are opinions, not gold labels.
  Before FOREIGN, the labels with the switch off and on differed on 1 of 20; FOREIGN turns 9 more into `unsure`.
  The 5 rows the orchestrator judged with high confidence from practice evidence are right in every variant.

## 4. Safety review

Reviewers: a fresh Opus agent (round 1) and Codex at xhigh (rounds 1 to 3), read-only. Probes for round 1 ran on the server.

| Round | Reviewer | Verdict | Defects |
|---|---|---|---|
| 1 | Opus | SHIP-WITH-FIXES | no reachable panic found; a panic would lose `output.csv`; one key with 5,000 distinct values took 243 s and 1.1 GB; "Sdev parity" is the refit path; page rule depends on input order |
| 1 | Codex | DO-NOT-SHIP | blocker: high-cardinality key (about 7.24 GiB for 18,001 states) before `output.csv` exists; major: explicit unknowns relabelled `true` |
| 2 | Codex | DO-NOT-SHIP | per-key caps do not bound the total (200 keys x 1,023 states, about 153 billion Viterbi steps); no output on kill |
| 3 | Codex | SHIP | no blocker, major or minor on the range from the round-2 build to the final commit |
| 4 | Codex | DO-NOT-SHIP | two Unicode false-flag cases in FOREIGN: lexicon mentions are matched without NFKC normalization (e.g. a fullwidth slash in `I/O`), and words with non-ASCII letters are left out of the lowercase vocabulary; no contract, rounding or performance defect. Open (see section 5) |

Fixes made: per-key state and allocation budget; explicit unknowns and incomplete clauses keep the engine label;
panic and invalid-output fallback with length and confidence checks; world budgets sum(S*n) <= 2^25 and
sum(T*S^2) <= 2^33 with cheapest-first admission (real worlds sit at least 200x and 10,000x under); engine
`output.csv` pre-written and replaced atomically; exact practice matches keep the engine through `Engine::practice_match`
(P390 hash unchanged by this change, every-fifth now 380 of 380). `cargo xtask test` passed 94 tests and `check` passed on the last local build.

## 5. Known limits and open bets

- 95% is not reachable on practice-like rows even with gold forms: ceiling 0.923 accuracy on P390 (0.924 on P80).
  Chain + G1 reaches 0.915 on P390 with frozen neural forms and 0.895 through the shipped CLI.
- FOREIGN is a bet that entities outside lexicon and practice are designed as "no means to tell". Break-even is
  about 27% gold `unsure` among flagged rows. Measured cost is about -0.01 on P390 (4 common-word false flags) and -0.0084 on P80.
  Practice itself has 2.1% `unsure` rows, so the bet pays only if hidden rows differ from practice.
- The binder maps some unknown entities onto Hooly subjects, so the chain can label them from unrelated evidence;
  FOREIGN covers part of this, not all.
- previous3text helps only if the input keeps document order (+0.036 points on, -0.031 against `none` when shuffled).
  The default is `none`. The order of the organizer's file is not verified.
- The chain loses to the engine on unsure-heavy worlds (diag, ext*, pilot); the router avoids this only through the
  practice-seed test. A hidden universe with about one third `unsure` targets would make the chain a net loss.
- P390 absolute numbers are optimistic for the neural extractor (checkpoint chosen on these rows).
- The chain's page rule assumes consecutive rows with one date; adversarial ordering is not covered (not verified).
- "Sdev parity" in the port notes is the refit path, which is the one the competition takes (labelled rows hold both classes).
- The real binary with the neural extractor ran on P390 with FOREIGN before the lowercase guard (without NOEVID or rounding):
  +0.7769 / 0.8821, 5 rows flagged, all gold `true`. It was not re-run after the guard, NOEVID off and rounding;
  the Python policy measurements and the Rust tests cover those changes (not verified end to end).
- The competition Docker image was not built or run with the switch on (not verified).
- Open from review round 4: FOREIGN can wrongly abstain on rows whose lexicon mention uses compatibility Unicode
  (fullwidth punctuation) or whose words contain non-ASCII letters. Practice texts contain no non-ASCII letters
  (only the euro sign and curly quotes), so this was not fixed before the freeze. Fix: apply the project's NFKC and
  case-folding normalization in `mentions()` and admit Unicode alphabetic tokens in the vocabulary.
- Extraction, measured on the million V2 pool on the same day: the shipped `context none` gives 310 of 390 row-exact
  neural extractions on P390; noise asides break 5 to 6% of otherwise correct bare clauses. Two binder guards
  (attribute kind, unit dimension) flagged 249 and 65 facts with none correct; they are not implemented.
