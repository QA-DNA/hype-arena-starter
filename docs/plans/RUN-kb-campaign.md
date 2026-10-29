# RUN: knowledge base variant campaign (2026-10-29)

- Owner: Edi (mogaeduard). Orchestrator: Claude Opus 5.5 session; workers via the Agent tool.
- Requested 2026-10-29 01:15: test every viable KB variant documented in
  `docs/research/knowledge-base.md` and anything else in the repo, and every combination that makes
  sense. Build the solution from the original data only (practice + lexicon), then test it on
  everything in Mihai's synthetic suite. Store every benchmark.
- Hard stop: results and report by about 06:30, so the team keeps time for the Rust port and the
  submission before the 11:00 freeze. Compressed at 02:08 at the owner's request: results within the hour.

## Frame

- **Goal.** Rank KB variants (timeline resolvers, truth discovery, learned fusion, calibration,
  abstention, graph and semi-supervised methods, lie fingerprints, small neural models) and their
  combinations; pick a winner with evidence.
- **KB input = gold stated forms.** Normalization is a separate component; a robustness track uses
  the extractor-B forms to show how each finalist degrades with real extraction errors.
- **Non-goals.** No Rust, no solver in the image, no claim generator, no changes to organizer files,
  `contracts/`, `data/`, `scripts/`, or other labs. No LLM in any variant.
- **Compute.** Code and quick checks on the Mac; large grids on a borrowed remote CPU box, cleaned
  completely afterwards (footprint manifest kept outside the repo).
- **Acceptance.** Every variant scored by one harness on every track, results in JSONL, the
  harness reproducing the published baselines, a pre-registered selection on practice only, test
  results on every suite world, an adversarial leakage review, a report with the winner and the
  runners-up.

## Tracks

| Track | Data | Labelled | Scored | Role |
| --- | --- | --- | --- | --- |
| P80 | `data/practice.csv`, gold `form` | 4 of 5 page folds | the 5th fold | selection |
| P10 | same | 10% of pages, 10 seeds | the rest | selection |
| S<world>-j | every suite world (dev, cal, sealed, diag, synth, pilot, prac, ext*), anchors as point statements on a fixed random day of their interval | the world's public labels | targets | test |
| S<world>-n | same worlds, intervals kept | public labels | targets | test (sanity: ceiling 1.0 for the interval engine) |
| X | extractor-B forms on the suite worlds | public labels | targets | test, robustness |

Suite modes: `t` transfer (fitted once on all of practice, applied to the world, whose public labels
act only as evidence) and `r` refit (fitted on the world's public labels). The real run is about
20,000 rows with only the 1,897 practice rows labelled (UPSTREAM.md); P80 and P10 are sparse, the
suite worlds have that density.

## Selection (pre-registered)

- Primary: mean arena points per row (+1 right, -1 wrong, 0 unsure, as `A/score.py`) over P80 and
  P10. Tie-break: lower ECE, then higher macro-F1.
- Suite results are tests: reported for every variant, never used to choose parameters.

## Phases

| Phase | Who | State |
| --- | --- | --- |
| 0 Frame, tracks, selection | orchestrator | done 01:25, revised 01:45 (practice-only selection) |
| 1 Harness + baseline ports + reproduction gates | W0, Opus | done 01:45 |
| 1b Remote CPU backend, runner, footprint manifest | B0, Sonnet | done 01:40 |
| 2 Families in parallel: F1 truth discovery, F2 temporal, F3 learned fusion and calibration, F4 graph and semi-supervised, F5 lie fingerprints, F6 stress tracks, F7 small neural models (CPU) | Opus workers | done 02:11 to 02:24 |
| 3 Combinations and final selection | Opus worker | done 02:53: the F2 chain alone wins |
| 4 Adversarial review (leakage, independent reproduction) | fresh Opus | done 02:58: honest, reproduces, deviation disclosed |
| 5 Report, commit, push | orchestrator + Sonnet | done 03:05 |

## Paths

- Working dir (outside the repo, one subdirectory per worker): session scratchpad `kbc/`.
- Python: `kbc/.venv` (3.12, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1).
- Suite: `~/Downloads/evaluation-data/realistic-v1/`, `realistic-synthetic-20000/`.
- Prior tools reused: `/tmp/veridyct-evalsuite/A/` (scorer, interval and point engines),
  `/tmp/veridyct-evalsuite/forms/` (gold, gold-nointerval, B, C forms), `labs/kb-experiments/`.
- Results and report land in `labs/kb-campaign/` and `docs/research/kb-campaign.md` at the end.

## Log

- 01:25 frame written; W0 dispatched.
- 01:35 remote CPU box authorized for tonight; B0 dispatched to set it up.
- 01:45 owner: build on practice + lexicon only, test on all of the suite; CPU only on the remote
  box, which must be left exactly as found. Selection moved to P80 + P10.
- 01:38 F1-F7 dispatched (Opus), common brief in `kbc/BRIEF-COMMON.md`.
- 01:40 remote backend ready (CPU venv identical to the Mac, cross-machine determinism check:
  identical output). Two GPU touches happened before the CPU-only rule reached the worker; logged
  in the local footprint manifest. No GPU since.
- 01:45 harness READY. Every gate reproduces (always-true 0.8332 / 0.8335, V5 0.7455 / 0.6990,
  V9-LR fixed 0.8672 / 0.8173 and points 0.777 / 0.639, interval engine 1.0, point 0.9795,
  point-jitter 0.7395 / 0.7246 / 0.7571, V9 on suite 0.8410 / 0.8391 / 0.8385). Leak check clean.
  Finding: V9-LR trained on practice and applied to Sdev-jt scores at always-true level
  (0.664 points vs 0.667); refit on the world's labels gives 0.929 accuracy; V12mmr-replace
  transfers better (0.829 points). Open item for the final system: V9 confidences can fall below
  0.5 when the threshold is under 0.5; the contract needs 0.5 to 1.
- 01:49 remote launches deadlocked from 01:43 (the runner's tmux server inherited the launch
  lock; found by F4). Fixed (new lock file, fd closed for tmux), 7 stuck waiters killed, workers
  told to relaunch. About 6 minutes of remote throughput lost.
- 01:51 subagents cannot write report files: reports come back as final messages (orchestrator
  saves them), plugins are published as code in `kbc/<FAMILY>/plugins.py`.
- 01:53 scoring fix (found by F5): arena points give +1 to a correct unsure (A/score.py), so the
  expected-points rule is argmax{2P(true)-1, 2P(false)-1, P(unsure)}. Harness v9 got
  `select='arena'`; v9 arena: P80 0.809, P10 0.674 points (always-true 0.667 / 0.662). Broadcast.
- 01:57 remote runs now execute from a hardlinked code snapshot per run (`runs/<tag>/` on the box),
  so a sync by one worker never changes another worker's running grid (hazard found by F2).
- 01:57 early signal (F2, not final): per-key Viterbi chain `F2/f2var.py:Chain`
  {"engine":"viterbi","eps_a":0.002,"pi_o":2,"vote_lr":12}: P80 0.814, P10 0.736 points
  (v9 arena 0.809 / 0.674); test-only Sdev-jt 0.945, Sdev-jr 0.930. Shared with F1, F3-F7.
- 02:08 owner asked for most results within the hour. Schedule compressed: families stop exploring
  at 02:25 and report by 02:35; Phase 3 (combinations, Opus) dispatched at 02:12 to build on the
  published plugins in parallel, search 02:35 to 02:55 on P80 + P10 only, test finalists on every
  suite world, X and the F6 battery by 03:10; Phase 4 (adversarial review, fresh Opus) dispatched at
  02:12 to audit the harness and the F2 leader now and reproduce the Phase 3 winner at about 03:05.
  Tie rule made explicit before any combination result: a gap under the paired SE is a tie, and the
  simpler config wins the tie.
- 02:11 F4 final: MIL + graph-Laplacian LR (`F4/f4models.py:Variant`) sel 0.772 (v9 arena 0.742);
  propagation as a labeller 0.725; page latent-lie EM has no held-out signal (AUC 0.48); lexicon
  features overfit. Plain transfer of every V9-family config is at or below always-true.
- 02:12 F2 final: per-key Viterbi chain with a learned per-kind monotone prior sel 0.8085 (P80 0.849,
  P10 0.768 +- 0.012), test Sdev-jt 0.942, Ssealed-jt 0.941, X tracks within 0.01. 1305 configs;
  104 at >= 0.80, so the mono-fit chain family counts as one choice. Learned layers on top of chain
  features overfit P10 and collapse on transfer. diag, pilot and ext* worlds have about one third
  unsure target gold (practice 1.4%): every variant is negative there (label-prior shift).
- 02:16 F5 final: only one fingerprint column (stale-with-votes, `w_nds`) adds to a chain on practice
  (paired P80 +0.0026, P10 +0.0037), and it costs about 0.02 on transfer tracks. Ten null columns cost
  P80 -0.007, P10 -0.005, so every extra column must beat a null control. Id-layout, round-number,
  text-voice and page-genre fingerprints are generator-specific; the id-layout one and the text cue
  tuned on all practice rows are excluded from the final system.
- 02:17 F1 final: a dynamic-world lifespan HMM over page claims (`F1/f1var.py:Variant` dynworld) sel
  0.8023 (P80 0.833, P10 0.771), test Sdev-jt 0.940, Ssealed-jr 0.943. Classic truth discovery
  (Accu, CRH, TruthFinder, Dawid-Skene, LTM, Sums) 0.72 to 0.76: page reliability cannot be
  estimated at about 4 observations per key. Copied-lie stress: exact-text dedup holds P10 at 0.769
  while the plain HMM drops to 0.645; AccuCopy gives no protection.
- 02:20 F6 final: a 407-cell stress battery per variant (density, label ratio, copied lies, page order,
  extracted forms, fact noise, unseen keys), gates reproduce the published numbers. With the
  practice-trained extractor's forms every baseline falls to or below always-true on P80 (chain
  0.655 vs 0.667): normalization quality bounds the KB. Copied lies: the chain calls almost every
  copied lie true (-0.96 on that subset). The chain beats always-true at every label ratio
  (0.712 at 5% of pages labelled) and never emits confidence below 0.5; V9 variants do.
- 02:20 F3 final: calibration and abstention add nothing significant on the chain (paired P10
  +0.003, se 0.004); Platt at 10% labels costs 0.048 (23 to 31 false labels per seed move its
  cutoff); learned LR fusion over chain scores loses 0.008 / 0.021 (paired); every abstention policy
  is at or below a plain 0.5 threshold. Temperature is the only safe recalibration of a calibrated
  scorer. Transfer masking (`tmask`) rescues raw-feature scorers on practice-only transfer
  (0.601 -> 0.701) but chains do not need it.
- 02:24 F7 final: DeepSets, GNN and MLP on V9 features tie or lose to V9-LR (277 false rows are too
  few to learn the bracket logic); an MLP correction on top of the F1 posterior reaches 0.791,
  below F1 and F2 alone, collapses on transfer and needs torch for refit. All seven families done;
  leftover remote grids stopped (ours only), so Phase 3 has the box.
- 02:27 Phase 3 first numbers: chain + F1 dynworld posterior + F5 stale-with-votes column, combined
  by an out-of-fold fact-level LR, sel 0.8144 (P80 0.851, P10 0.778) vs chain 0.8085, from a forward
  search over about 210 configs. Decider set: a fresh-split paired check on a fixed candidate list.
- 02:34 Review interim: no leak (scored-gold derangement leaves world pickles byte-identical and
  17/17 fold predictions identical; shuffled training labels collapse to always-true); metrics match
  the suite scorer to 1e-12; leader and candidate reproduce exactly. Page-cluster bootstrap over the
  291 practice pages: candidate minus chain +0.0062, SE 0.0042, 95% CI [-0.0018, +0.0148]; the
  candidate loses about 0.018 on every transfer test track and gains 0.006 on Sdev-jr. Data caveat:
  95% of suite anchor intervals sit on 3 or 4 global epoch dates, so the jittered suite tracks are
  easier than the competition.
- 02:53 Phase 3 final: about 190 combinations (stacked out-of-fold deciders over every family's
  plugins with null controls, chain modulation, dedup, posterior ensembles, every calibrator and
  policy). On fresh splits (15 permuted P80 folds, P10 seeds 10 to 29, page-cluster bootstrap)
  every combination ties the chain (best stack -0.0004 +- 0.0044), so by the tie rule the winner is
  the F2 chain alone. Chain + dedup costs -0.0020 +- 0.0009 on clean splits and gains about 0.20
  under copied lies.
- 02:55 Orchestrator decision on dedup: off by default. Practice has 16 verbatim-repeated texts
  (34 rows: 28 true, 4 false, 2 unsure, 4 groups with mixed labels across dates), i.e. restatements,
  not a copied-lie channel (the generator analysis lists only 4 false rows sharing text with another
  row: two stale repeats and one identical pair), and the clean cost is measurable. Dedup stays a documented switch for the port.
- 02:58 Review final: no leak; the winner reproduces (P80 0.8492, P10 0.7673 on the Mac vs 0.7678 on
  the box, Sdev-jt 0.9419, Sdev-jr 0.9148); fresh splits rebuilt and reproduced, same ties. Disclosed
  deviation: the literal rule would have picked the best stack (lead 0.0062 > fold-paired SE 0.0032);
  the decider was switched to the fresh-split bootstrap at 02:27 after its harness-split numbers and
  before its suite numbers. Two plugins rejected (one reads its own page's labels, one reads the id
  layout); neither is near the top.
- 03:05 Report `docs/research/kb-campaign.md`, lab `labs/kb-campaign/` (harness, family, combination and
  review code, every report, every result line gzipped, sanitized: no remote-box identifiers, no
  local paths, no data copies), docs index updated; committed and pushed to main.
