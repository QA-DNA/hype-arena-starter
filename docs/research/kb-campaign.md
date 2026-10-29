# Knowledge base campaign: every KB variant measured (2026-10-29)

Run on the night of 2026-10-28 to 29. The goal was to build the best knowledge base from the official data only
(`data/practice.csv`, 1,897 labelled rows, and `data/lexicon.json`), try every variant documented in
[the knowledge base research](knowledge-base.md) and the rest of the repo plus every combination that makes sense, and
then test the result on everything in the teammate's synthetic evaluation suite. Code, per-family reports and every
result line: [labs/kb-campaign](../../labs/kb-campaign/README.md). Run log: [RUN-kb-campaign](../plans/RUN-kb-campaign.md).

## Verdict

- **Winner: the F2 per-key temporal chain, alone.** `F2/f2var.py:Chain {"engine":"viterbi","d0":0.03,"eps_a":0.0005,
  "mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}`. Selection 0.8085 arena points per row (P80 0.849, P10 0.768),
  against 0.742 for the previous best (V9-LR with an arena threshold) and 0.665 for always-true. ECE 0.011 / 0.037.
- **On the suite (tests, never used to choose):** 0.941 points on average over dev, cal, sealed and syn in transfer
  mode (fitted on practice only; always-true 0.667, V9 0.665), 0.929 refitted on each world's labels, accuracy 0.97,
  false precision and recall 0.95 / 0.95 on Sdev-jt. Extractor-B forms change it by under 0.01.
- **No combination beats it.** About 190 combinations of every family's components were scored. The best stack (the
  chain plus the F1 truth-discovery posterior and one F5 fingerprint column, through an out-of-fold LR) led by
  +0.006 on the harness splits, but on fresh practice splits it ties (-0.0004 +- 0.0044, page-cluster bootstrap) and
  it costs 0.018 on every transfer track, so on a tie the simpler configuration wins. The literal pre-registered rule
  (fold-paired SE) would have kept the stack; switching to the fresh-split decider is a disclosed deviation (see
  Review).
- **Runner-up: the F1 dynamic-world HMM** (selection 0.802; 0.938 refitted on the suite worlds, the best `r` numbers).
  It is a structurally different model and the natural fallback if the chain misbehaves on the real universe.
- **It fits the box by two orders of magnitude.** 1.2 to 1.5 s and under 200 MB per 20,000-row world with 2 threads,
  no learned layer beyond two isotonic maps, confidence in (0.5, 1] by construction.
- **What bounds it is not the KB.** With our practice-trained extractor's forms every variant, the chain included,
  falls to or below always-true on practice (chain 0.643, always-true 0.667). Normalization quality is now the
  bottleneck: the KB gain only materializes on correct facts.
- **Its known weakness is copied lies** (verbatim copies of a lie on new pages): the chain falls from 0.849 to 0.646
  on P80 under that attack, and exact-text dedup restores 0.847 at a small clean cost (-0.002 +- 0.001). Practice
  shows no copied-lie channel, so dedup is a documented switch, off by default.

## Setup

- **KB input.** Gold stated forms (`form` column of practice, the suite's gold forms). Normalization is a separate
  component; the stress battery measures how much worse things get with our extractor's forms.
- **Selection tracks (the only ones used to choose anything).** P80: 5-fold GroupKFold by page, 80% of pages labelled.
  P10: 10% of pages labelled, 10 seeds. Hidden rows keep their facts as unlabelled evidence. Pages are runs of
  consecutive rows with the same date and labelled status.
- **Selection rule, fixed before any result.** Mean arena points per row over P80 and P10 (+1 right, including unsure
  on unsure; -1 wrong true or false; 0 unsure on a decided row, exactly as the suite scorer). Tie-break lower ECE, then
  higher macro-F1. A gap under the paired standard error is a tie, and the simpler configuration wins the tie (made
  explicit at 02:08, before any combination result). At 02:27 the decider became a page-cluster bootstrap on fresh
  practice splits, because the leading combination came out of a large forward search (see Review). The points-optimal decision is
  argmax{2P(true) - 1, 2P(false) - 1, P(unsure)}.
- **Test tracks (reported, never used for a choice).** Every suite world (dev, cal, sealed, syn, diag, pilot, prac,
  extdev, extcal, extsealed) in four modes: `j` anchors re-dated to a random day of their interval with the "From X
  through Y," phrase removed (competition-like) or `n` intervals kept; `t` fitted once on practice and applied to the
  world, or `r` refitted on the world's public labels. The real run is closest to `jr`: about 20,000 rows of one
  universe whose only labels are the 1,897 practice rows. `X` tracks use the practice-trained extractor's forms.
- **Harness.** One Python harness scores every variant on every track with one metrics function; it reproduces every
  published baseline (always-true 0.8332 / 0.8335 accuracy, V5 0.7455 / 0.6990, V9-LR 0.8672 / 0.8173, interval engine
  1.0, point engine 0.9795, V9 on the suite 0.8410 / 0.8391 / 0.8385). Large grids ran on a borrowed remote CPU box.

## Results by family (best configuration per family)

Points per row. Sel = mean of P80 and P10. Suite columns are tests.

| Family | Best configuration | Sel | P80 | P10 | Sdev-jt / jr | Ssealed-jt / jr | 20k-row cost |
|---|---|---:|---:|---:|---|---|---|
| Always-true | | 0.665 | 0.667 | 0.662 | 0.667 / 0.667 | 0.667 / 0.667 | 0 |
| V9-LR, arena threshold (previous best) | `v9 {"select":"arena"}` | 0.742 | 0.809 | 0.674 | 0.664 / 0.876 | 0.668 / 0.669 | 2 s |
| F2 temporal | per-key Viterbi chain, learned per-kind monotone prior | **0.8085** | 0.849 | 0.768 | 0.942 / 0.915 | 0.941 / 0.923 | 4 to 6 s, 0.2 GB |
| F1 truth discovery | dynamic-world lifespan HMM over page claims | 0.8023 | 0.833 | 0.771 | 0.940 / 0.931 | 0.941 / 0.943 | 2 to 6 s, 0.4 GB |
| F3 fusion, calibration, abstention | the F2 chain wrapped, no recalibration, points threshold | 0.8003 | 0.833 | 0.767 | 0.942 / 0.942 | 0.941 / 0.934 | 1 to 5 s |
| F5 lie fingerprints | the chain plus one stale-with-votes column | 0.7998 | 0.834 | 0.766 | 0.922 / 0.925 | 0.918 / 0.939 | 5 s |
| F7 small neural (CPU) | MLP correction on top of the F1 posterior | 0.791 | 0.836 | 0.747 | 0.667 / 0.878 | 0.667 / 0.766 | 56 to 73 s, 1.4 GB, torch |
| F4 graph, semi-supervised, lexicon | MIL + graph-Laplacian LR | 0.772 | 0.838 | 0.707 | 0.599 / 0.881 | 0.649 / 0.894 | 6 to 28 s |

F3 and F5 used a chain configuration slightly below the F2 winner, so their rows compare with 0.797, not 0.8085.

## What each family established

- **Temporal resolution (F2, 1,305 configurations).** A per-key timeline over the distinct canonical values plus an
  "other" state, with hazard rates fitted per value kind, near-hard anchors and strong votes from unlabelled rows on
  other pages, and an exact leave-own-page-out posterior (brute-force checked), beats V9 by 0.067. Learning which kinds
  only go up (quantity 148 up, 4 down on practice anchors; version 28 up, 0 down) adds 0.011. Point resolvers, bracket
  tables, change-point segmentation and TeCoRe all score 0.71 to 0.77. Learned layers on top of the chain features
  overfit P10 and collapse on transfer; the chain transfers (0.94) because only a monotone isotonic map sits on its
  posterior. 104 configurations score at least 0.80, inside the P10 seed noise (0.012): the family is one choice.
- **Truth discovery (F1, about 2,300 jobs).** Modelling the world as changing wins: values ordered by the median date of
  their claims, a lifespan prior, and separate outdated and plainly false error rates per page. Classic methods (Accu,
  CRH, TruthFinder, Dawid-Skene, LTM, Sums) score 0.72 to 0.76: with about 4 observations per key, page reliability
  cannot be estimated. Under a copied-lie attack (every hidden false row copied verbatim onto 3 new pages) the HMM
  falls from 0.771 to 0.645 on P10; exact-text dedup holds it at 0.769 at no clean cost. AccuCopy gives no protection.
- **Calibration and abstention (F3).** On the chain, no calibrator and no abstention policy is significantly better
  than a plain threshold (paired P10 +0.003, se 0.004). Platt at 10% labels costs 0.048: with 23 to 31 false labels per
  seed its bias term moves the cutoff. Temperature is the only safe recalibration of a calibrated scorer. Every
  abstention policy (conformal, Mondrian, Venn-Abers width, no-evidence) is at or below the plain threshold.
- **Graph and semi-supervised (F4).** Multiple-instance blame for multi-fact false rows (+0.010) and a graph-Laplacian
  penalty over same-claim edges (+0.010 to 0.015) help V9; label propagation alone scores 0.725; a page-level
  latent-lie EM finds structure in-sample but has no held-out signal (AUC 0.48), matching the generator analysis;
  lexicon features overfit (40 link facts, 234 event-tied facts in practice).
- **Lie fingerprints (F5, null-controlled forward selection).** On top of the chain only one column adds signal on
  practice (stale value contradicted by later votes; paired P80 +0.003, P10 +0.004), and it costs 0.02 on transfer
  tracks. Ten pure-noise columns cost 0.007 / 0.005, so every candidate must beat a null control. Id-layout,
  round-number, text-voice and page-genre fingerprints are generator-specific (first-person rows: 43% in the suite,
  4% in practice).
- **Small neural models (F7).** DeepSets, a GNN and an MLP on V9 features tie or lose to V9-LR: 277 false rows are too
  few to learn the bracket logic, which the handcrafted features already encode.

## Combination phase

About 190 combinations on P80 + P10, built on the chain (`P3/p3.py:Stack`):

- **Stacked fact deciders:** the chain's fact logit plus any family plugin (truth-discovery posteriors and page
  reliability, graph propagation and blame, lie fingerprints, staleness, neural set and graph scores, pure-noise
  controls), fitted out of fold by page on labelled facts, as LR (C 0.03 to 10), LR with the chain as a fixed offset,
  or HGB. Excluded up front: fingerprints that read the id layout, a text cue designed on all practice rows, and a
  page feature that observes neighbours' labels.
- **Chain modulation** (per-fact reliability scaling the votes), **dedup inside the chain**, **posterior ensembles**
  (chain, F1 HMM, F2 HMM logits), every **calibrator and abstention policy**.
- **Search:** forward selection with null controls, then backward elimination. Step 1: the F1 posterior +0.001;
  every other single plugin ties or loses; HGB 0.795. Step 2: adding the stale-with-votes column gives 0.8144.
  Step 3: nothing improves.

| Candidate vs the chain | Harness splits (fold-paired) | Fresh splits (page-cluster bootstrap) | Transfer tracks |
|---|---|---|---|
| + F1 posterior | +0.0012 +- 0.0028 | -0.0008 +- 0.0028 | -0.0002 |
| + F1 posterior + stale-with-votes | +0.0062 +- 0.0032 | -0.0004 +- 0.0044 | -0.0163 |
| same + dedup | +0.0043 +- 0.0045 | -0.0003 +- 0.0045 | -0.0178 |
| + stale-with-votes | -0.0019 +- 0.0033 | +0.0019 +- 0.0024 | -0.0191 |
| + dedup | -0.0036 +- 0.0014 | -0.0020 +- 0.0009 | -0.0033 |

Fresh splits: 15 permuted P80 folds and P10 seeds 10 to 29 over the 291 practice pages, B = 2,000 page-cluster
bootstrap resamples. The harness-split lead of the best stack came out of the search itself (its fingerprint column
was also chosen by F5 on the same data): a winner's-curse gain, as the fresh splits show. Transfer column = mean
change in points over Sdev, Scal, Ssealed and Ssyn in `jt` mode.

## Robustness (stress battery, 407 cells per variant)

- **Extracted forms bound the KB.** With the practice-trained extractor's forms every variant falls to or below
  always-true on P80 (winning chain 0.643, best stack 0.654, V9-LR 0.647, always-true 0.667), and rows whose own form is exact also lose points
  because other rows' wrong facts spoil the evidence. The suite's own extracted forms are 99.8% exact, so the X tracks
  move every variant by under 0.01 and are not a robustness test.
- **Copied lies.** Without dedup every evidence-pooling variant calls almost every copied lie true (-0.96 on that
  subset of P10); the winning chain falls to 0.646 / 0.640 on P80 / P10, and 0.847 / 0.763 with dedup. Copying true
  rows changes nothing.
- **Label ratio.** The chain beats always-true at every ratio (0.712 at 5% of pages labelled); V9 needs 20% or more.
- **Noise.** The chain is the most sensitive strong variant to wrong values (-0.28) and dropped facts (-0.15); V9-LR
  loses about 0.02 on dropped facts.
- **Contract.** The chain never emits confidence below 0.5; V9 variants do (about 2,000 predictions for the arena V9).

## Worlds where every variant is negative

diag, pilot and the ext worlds score below zero for every KB variant and every family. Their target gold is about one
third unsure (diag: 1,367 true, 1,368 false, 1,368 unsure) while practice has 1.4% unsure, and the chain predicts
unsure on 30 of 4,103 diag targets. This is a label-prior shift plus an answerability problem: deciding that a claim
cannot be decided needs the interval engine (0.344 on Sdiag-jt with jittered anchors, 0.9985 with intervals), not a
better fact scorer. Nothing selected on practice can learn it, and the competition's practice file shows no such mix.

## Review

A fresh reviewer audited the harness, the winner, every family's plugins and the selection, and reproduced the numbers
independently.

- **No leak of scored or hidden gold.** Replacing every scored row's gold label in copies of the data leaves the fold
  worlds byte-identical and every prediction identical (17 of 17 folds for the winner, the best stack and the best
  wrapped chain; 9 of 9 for the best F1, F3 and F5 variants). Shuffling the training labels collapses the winner to
  always-true (0.667 / 0.661). The harness metrics match the suite scorer to 1e-12. Folds cover whole pages and no
  selection fold can fall back to a one-class fit.
- **The winner reproduces:** P80 0.8492, P10 0.7673 on Apple silicon (0.7678 recorded on the x86 box, a deterministic
  host difference), Sdev-jt 0.9419, Sdev-jr 0.9148. Each fact's own page is left out exactly (flipping that page's labels
  moves its facts by 9e-16 with the fitted rates fixed); the own label reaches only the global per-kind rates, on the
  training side. None of 68,248 decided rows has confidence outside [0.5, 1].
- **Plugins:** every plugin leaves the own page out, except one F4 comparison feature that reads its own page's labels
  (rejected; its best configuration ranks 2,058th) and one F5 feature that reads the practice id layout (rejected as
  generator-specific; ranks 381st).
- **Selection hygiene:** no traceable parameter was chosen on suite numbers.
- **Winner's curse:** on the harness splits the best stack's lead is +0.0062 with a page-cluster bootstrap SE of 0.0042
  (95% CI [-0.0018, +0.0148]); it is the bootstrap argmax in only 29% of resamples and the argmax optimism is +0.0024.
  The reviewer rebuilt the fresh splits (whole pages, no seed shared with the harness splits), reproduced their per-row
  points exactly and got the same ties.
- **Protocol deviation, disclosed.** The literal pre-registered rule (a tie is a gap under the fold-paired SE) would
  have picked the best stack: its harness-split lead of 0.0062 exceeds that SE (0.0032). The orchestrator replaced the
  decider with the fresh-split page-cluster bootstrap at 02:27, after seeing the stack's harness-split numbers and before
  seeing its suite numbers, because the stack came out of a forward search over about 210 configurations; the fresh-split
  check ran after the suite numbers were known. The new decider uses practice only and is more conservative, and the
  transfer tests agree with it (the stack loses on 14 of 16 transfer tracks), but the switch is a departure from the
  pre-registration. On refit tracks the stack gains 0.002 on average (10 of 16): if the port team wants the
  extra column, it is a measured, small, uncertain option, not a free win.
- **Data caveat:** 95% of suite anchor intervals sit on four global epoch dates, so a jittered day still identifies its
  interval; the suite's `j` tracks are easier than the competition and its numbers are an upper bound.

## Recommendation for the Rust port

Port the chain (`labs/kb-campaign/F2/f2core.py`, about 580 lines of Python, plus the `Std` pipeline in `f2var.py`):

1. **Keys.** One timeline per (subject, attribute) observation key; states are the key's distinct canonical values
   plus an "other" state (prior `pi_o` = 1). A fact with no evidence from another page gets the smoothed
   no-evidence rate of the fact map instead of a chain score.
2. **Hazard.** Per value kind, `lam` by maximum likelihood on consecutive true-anchor pairs (prior 1/200 per day,
   weight 2); transitions `T(g) = e^(-lam g) I + (1 - e^(-lam g)) W`. Per ordered kind, a downward-switch weight
   learned from anchor pairs with a Beta prior (mean `d0` = 0.03, strength `mono_a` = 10); practice gives quantity
   0.027, version 0.01, date 0.012, percent 0.167, money 0.518, duration 0.978.
3. **Emissions.** True anchor `log(eps_a + (1 - eps_a) A)` with `eps_a` = 0.0005; single-fact false row
   `log(1 - (1 - eps_f) A)` with `eps_f` = 0.2; multi-fact false rows ignored (`wm` = 0); an unlabelled fact on another
   page is a vote with likelihood ratio 48.
4. **Inference.** Max-product (Viterbi) over each key's dated observations; a fact's score is the max-marginal margin
   of agreeing over disagreeing states at its date, computed exactly with its own page removed (one forward-backward
   pass, `page_local`).
5. **Decision.** Isotonic map from fact score to P(fact true) fitted on labelled facts (pool-adjacent-violators),
   product over the row's facts, a second isotonic map on rows, then the arena rule with the labelled unsure rate `u`:
   P(true) = (1 - u) p, P(false) = (1 - u)(1 - p), P(unsure) = u, argmax of {2P(true) - 1, 2P(false) - 1, P(unsure)},
   confidence = the chosen probability (always above 0.5).
6. **Options to keep behind flags:** exact-text dedup (a verbatim copy casts no vote), the HMM engine (F2 #2, a true
   posterior, within 0.002), and the F1 dynamic-world HMM as the fallback model.

The port needs no learned model beyond two isotonic maps and per-kind rates, no ML dependency and no GPU. Check it
against `labs/kb-campaign` on P80 (0.8492) and Sdev-jt (0.9419) before wiring it to the extractor.

## Reproduce

Everything is in [labs/kb-campaign](../../labs/kb-campaign/README.md): the harness, every family's code and report,
the combination and review code, and every result line (gzipped JSONL, one line per variant, parameters and track).
The practice tracks need only `data/`; the suite tracks also need the teammate's evaluation data and the forms written
by [labs/evaluation-suite-runs](../../labs/evaluation-suite-runs/README.md).

```sh
export KBC_ROOT=$PWD/labs/kb-campaign KBC_PRACTICE_DIR=$PWD/data KBC_RESULTS_DIR=/tmp/kbc-results
.venv-kbc/bin/python -I $KBC_ROOT/harness/run.py \
  --variant 'F2/f2var.py:Chain={"d0":0.03,"engine":"viterbi","eps_a":0.0005,"mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}' \
  --tracks P80,P10 --jobs 2 --worker ME      # P80 0.8492, P10 0.7673 (Apple silicon) / 0.7678 (x86)
```

Python 3.12, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1 (torch 2.15.0 CPU only for F7). Large grids ran niced on a
borrowed 256-core CPU box; the box and the Mac give identical outputs except a 0.0005 P10 difference for the chain,
so every paired comparison uses Mac runs only.
