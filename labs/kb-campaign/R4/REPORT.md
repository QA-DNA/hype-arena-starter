# R4 report: adversarial review (leakage, reproduction, selection hygiene)

Saved by the orchestrator from R4's final message (02:58). Verdict: the harness and the winner are honest, the numbers reproduce, and choosing the chain alone is justified on practice-only evidence and agrees with the transfer tests. The choice departs from the literal pre-registered rule (see section 4).

## 1. Harness leakage

- VERIFIED: no fold world carries hidden gold. Copies of the data with every scored row's gold changed (true -> false, false -> unsure, unsure -> true): `practice.csv` per P80 fold and P10 seed, and a dev `gold/labeled.csv`, loaded through `KBC_PRACTICE_DIR`, `KBC_SUITE_DIR` and a fresh `KBC_ROOT`. Fold worlds byte-identical (`probe.py attrs`): P80 folds 0 and 3, P10 seeds 0 and 7, Sdev-jt, Sdev-jr. Every prediction identical, labels and confidence on all rows (`cmp.py`): leader 17/17, P3 candidate 17/17, P3 Stack#1 17/17, best Wrap 9/9, best OnChain 9/9, best F1 variant 9/9.
- VERIFIED: shuffled training labels collapse to always-true (leader P80 0.6668, P10 0.6613; candidate 0.6668, 0.6623; always-true 0.667, 0.662).
- VERIFIED: `metrics.compute` matches A/score.py exactly; vendored `score.py` and `truth.py` byte-identical to the originals; `A/score.py --world dev` on dumped predictions gives the harness numbers for leader and candidate (points, ECE, macro-F1 to 1e-12); an independent scorer matches P80 pooled and the P10 seed mean.
- VERIFIED: selection splits honest. Every fold mask covers whole pages; P80 trains on 232 or 233 pages per fold; P10 has 29 labelled pages per seed; every fold has at least 21 labelled false rows, so no one-class fallback can fire on a selection track (none of the 9,558 selection lines records one).
- VERIFIED: transfer fits once on practice (`run_variant` calls `fit(train)` then `predict`; Chain and Stack reuse the practice hazard, FactMap and RowCal; changing the suite gold leaves predictions unchanged).
- VERIFIED: suite inputs carry nothing extra (forms records hold only id, assertions, interval; value dicts only kind, value, unit, currency, per, op; no hidden row has an interval in dev, cal, sealed, synth, diag; `-j` stripped the interval phrase everywhere except one natural-prose hit in cal; Sprac is a different world from practice, 2 of 1,897 texts shared).
- Data caveat, not a leak: 95% of suite anchor intervals are one of the global epochs (2025-10-01, 2026-02-01, 2026-07-01, 2026-10-30), so a jittered day still identifies its interval; `-j` results come from a world with a coarse shared change grid. No variant uses `sha1(id)` or row position.
- Hazards, not leaks: a variant can import `world.practice_full` or `suite_gold` or read `cache/practice-*.pkl` (only code review keeps that out; the only uses are one-class fallbacks); `World.with_labels` shallow-copies `__dict__`, so label-dependent caches without a label key (F2 `_f2_keys`, `_f2_hz`, `_f2_feat`, `_f2_cells`) are inherited by inner OOF copies (the current Wrap, F1 `_oof` and Stack flows read none); `leaderboard.py` crashes on `F5-paired.jsonl` lines (no `variant` key).

## 2. The winner, F2 Chain

- VERIFIED by reading `f2var.py` and `f2core.py` end to end: labels read only through `world.labelled` and `world.label`; each fact's own page left out exactly (with hazard and mono weights fixed, flipping that page's labels moves its own facts by 9e-16, `plugaudit.py R4/fixchain.py:vit`); the own label still reaches the fit through the in-sample global hazard and mono weights (up to 2.2 in margin), training side only.
- Reproduced through `run.py --worker R4`: P80 0.8492 (recorded 0.8492), P10 0.7673 (recorded remotely 0.7678; three identical Mac runs with the same src_hash, so the gap is host-dependent), Sdev-jt 0.9419, Sdev-jr 0.9148. Mac selection 0.8083 vs 0.8085 recorded. src_hash covers `f2var.py` only, not `f2core.py`.
- VERIFIED: `P3/p3.py:Stack {"oofmap": false}` is output-identical to the Chain on 17 of 17 folds (P80 x5, P10 x10, Sdev-jt, Sdev-jr).
- VERIFIED: none of the 68,248 decided rows has confidence outside 0.5 to 1.

## 3. Family plugins (flip one labelled page's labels on P10 seed 0, measure its own facts, `plugaudit.py`)

- Own-page change 0: F1 all 5 plugins; F4 `lex_*`; F5 the other 15 fp plugins including `w_nds`; F7 deepsets `features`, `features_mil`, gnn `features`; F2 `tecore`, `bracket`.
- Small change through global parameters only (code read): F5 `prior` (0.057) and `src_idblock` (0.038) via the global base-rate prior (both exclude the own page); F2 f2feat `hmm`, `viterbi`, `stale`, `seg`, `core` and F3 `chain_vit`, `chain_hmm` via the fitted hazard; F4 prop and blame features (0.035).
- REJECTED as a feature (not a leak of scored rows): F4 `page_lie_lab` uses its own page's labels (change 3.92); its best config ranks 2,058.
- REJECTED as a feature (generator-specific): F5 `src_idblock` exploits blocks in practice id order; best config ranks 381.
- VERIFIED by code read: F3 `fusion.py:Wrap`, F5 `onf2.py:OnChain`, `P3/p3.py` (every stacked layer fit on labelled facts or rows only, OOF by page; RowCal on OOF row probabilities; `td_post` inner-OOF; `w_nds` leaves out the own page and uses labels only to drop labelled-false rows).

## 4. Selection hygiene and winner's curse

- VERIFIED: no traceable parameter was chosen on suite numbers. F2's engine, `eps_a`, `vote_lr`, `pi_o` were scored on P80 before F2's first suite lines; mono-fit is justified by practice anchors (148 rises, 4 falls); F5's forward search runs on P80+P10 with null controls; F3's `tmask` was validated on a practice-only transfer check; the P3 candidate was scored on P80 and P10 before P3's first suite run; F1 stage 2 and P3 `sel.py` rank by P80+P10 only; no selection script references a suite track.
- Protocol deviation to disclose: the final pick departs from the literal pre-registered rule, which would pick candidate c (0.8144 on the harness splits, gap 0.0062 above its fold-paired SE 0.0032). The fresh-split decider is practice-only and more conservative, but it was run after c's suite numbers were known.
- Winner's curse on the harness splits (page-cluster bootstrap over 291 pages, B = 2000, top 80 configs re-run on the Mac, `boot.py`): c minus the Chain +0.0062, SE 0.0042, 95% CI [-0.0018, +0.0148], P(<= 0) 0.067 (the split SE understates it because P10 seeds share most scored rows); c is the bootstrap argmax in only 29% of replicates; selection optimism of the argmax +0.0024; the top sits 0.0062 above the median of the top 80.
- Fresh splits, independently checked: rebuilt (P80R1-3 x 5 folds, P10 seeds 10 to 29); recorded scored pages equal the complement of the masks and are whole pages; no P10 seed equals a harness seed; no fresh P80 fold has more than 31% of its pages in any single harness fold. Re-running a, c and dedup on four splits reproduces the recorded per-row points exactly (12 of 12). Own bootstrap (seed 7) vs the chain: c -0.0004 (SE 0.0044, CI [-0.0093, +0.0081]); b -0.0008 (0.0029); f +0.0019 (0.0024); dedup -0.0020 (0.0009, CI [-0.0038, -0.0002]). Agrees with P3.

## 5. Winner vs runner-up on test tracks (not used for selection)

c's +0.006 shrinks to about +0.004 after the optimism correction (CI includes 0) and vanishes on fresh splits. On transfer it loses to the chain on 14 of 16 tracks, by 0.0095 on average (Sdev-jt 0.9419 vs 0.9240, Scal-jt 0.9437 vs 0.9270, Ssealed-jt 0.9406 vs 0.9214); on refit it gains 0.0021 on average, better on 10 of 16 (Sdev-jr 0.9148 vs 0.9211). c reproduces through `run.py --worker R4`: P80 0.8508, P10 0.7780, selection 0.8144.

## Unverified

- F3's calibrators beyond Wrap not probed.
- Why P10 differs by 0.0005 between hosts, beyond ruling out run-to-run randomness.
- The page-cluster bootstrap does not resample the training splits.

Probe code in `R4/`, results in `results/R4.jsonl`.
