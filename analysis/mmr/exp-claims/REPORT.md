# Claim selection under correlated failures: top-k vs MMR vs caps (practice data)

Run from the repository root: `python analysis/mmr/exp-claims/claims_mmr.py` (numpy, pandas).
About 4 s, seed 20261029, 5,000 Monte Carlo draws, all strategies on the same draws. The script
writes `results.md` (every table), `results.csv`, `stress.csv` and `adversarial.csv` next to
itself. It asserts that each simulated mean matches sum(p) within 4 standard errors and that
every cap holds.

## Setup

- **Observations:** exact values from TRUE practice rows only, units converted so that equal
  values match: 1,964 assertions over 501 (subject, attribute) keys.
- **Candidate pool (forms only, no text rendering):** 7,017 candidates on 501 base keys and 62
  subjects.

  | Type | Candidates | Rule |
  |---|---|---|
  | fact | 501 | latest value per key |
  | compare | 4,464 | one orientation per comparable pair |
  | change | 324 | consecutive distinct values |
  | at_event | 1,701 | 6 dated events × keys |
  | relation | 27 | target value while the link named it |

- **p_key (uncalibrated proxy):** `p_val = (s+4)/(s+5+f+0.5u) × 1/(1+0.1(d−1))`, multiplied by
  a freshness factor `exp(−hΔ)`.
  - `s` = supporting true rows, `f` = false rows on the key, `u` = unsure rows on the key,
    `d` = number of distinct values.
  - `h = (changes+0.5)/(span_days+365)` is the change rate; `Δ` is the time to the as-of date
    (or to the event date, for at_event).
  - Candidate p = product over its base keys.
- **Similarity:** `sim = min(1, Jaccard(base keys) + 0.3·[same subject] + 0.1·[same type])`.
- **Strategies:**

  | Code | Strategy | Grid |
  |---|---|---|
  | S0 | top-k by p | |
  | S1 | MMR `λp − (1−λ)·max_sim` | λ ∈ {0.5, 0.7, 0.85, 0.95} |
  | S2 | per-key cap | C ∈ {3, 5, 10} |
  | S3 | equal type quota + MMR | |
  | S4 | coverage bonus | μ ∈ {0.1, 0.3} |
  | S5 | greedy DPP (Chen et al. 2018) | |
  | S6 | cap + MMR | C ∈ {5, 10} × λ ∈ {0.5, 0.7, 0.85} |
  | S7 | cap C=10 + penalty = mean of the 3 most similar selected | λ ∈ {0.7, 0.85} |

- **Stress tests:**
  - **lying-page:** keys with any false row get value-correctness 0.5;
  - **shrink30:** every key probability moved 30% toward 0.5;
  - **adversarial:** the 1 or 5 most-exposed keys are wrong.
- **Scoring hypotheses:**
  - **H1:** E[#correct]/k;
  - **H2:** distinct base-key sets with at least one correct claim / k;
  - **H3:** E[#correct]·√(distinct keys / k) / k, illustrative.
  - **Maximin:** min over H1-H3 of the strategy's value divided by the best of all 20
    strategies.

## Pool structure

- **Candidates per base key:** max 437, p90 57, mean 26.4, median 13.
- **Hubs are event dates:** Maps Day.date 437, Cloud Next.date 432, May 2026 outage.date 412,
  Made by Hooly.date 393, I/O 2026.date 304.
- **Mean candidate p by type:** fact 0.654, change 0.649, relation 0.635, compare 0.449,
  at_event 0.390.

## k=1000 (1,000 picks from 501 keys: maximum concentration pressure)

| Strategy | E | sd | p5 | p1 | Max exposure | Keys | Worst 1 / worst 5 keys lost | H1 | H2 | H3 | Maximin |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 top-k | 710.7 | 47.2 | 625 | 587 | 104 | 386 | 104 / 203 | .711 | .623 | .442 | 0.899 |
| S1 λ=0.5 | 691.5 | 44.9 | 610 | 573 | 97 | 501 | 97 / 195 | .691 | .691 | .489 | 0.973 |
| S1 λ=0.7 | 697.5 | 43.2 | 618 | 584 | 97 | 494 | 97 / 187 | .697 | .668 | .490 | 0.966 |
| S1 λ=0.95 | 710.5 | 47.2 | 625 | 586 | 104 | 397 | n/a | .711 | .632 | .448 | n/a |
| S2 C=5 | 664.2 | 24.7 | 623 | 606 | 5 | 490 | 5 / 25 | .664 | .507 | .465 | n/a |
| S2 C=10 | 689.6 | 30.9 | 638 | 616 | 10 | 440 | 10 / 47 | .690 | .571 | .457 | 0.826 |
| S3 quota+MMR | 699.6 | 60.1 | 591 | 526 | 155 | 462 | 155 / 310 | .700 | .648 | .476 | 0.938 |
| S4 μ=0.1 | 706.5 | 45.9 | 617 | 581 | 119 | 469 | n/a | .706 | .627 | .484 | n/a |
| S5 DPP | 693.7 | 37.5 | 626 | 594 | 85 | 501 | 85 / 155 | .694 | .598 | .491 | 0.865 |
| S6 C=10 λ=0.5 | 672.7 | 32.8 | 619 | 598 | 10 | 501 | 10 / 47 | .673 | .647 | .476 | 0.935 |
| S6 C=10 λ=0.7 | 683.2 | 30.8 | 631 | 612 | 10 | 500 | 10 / 47 | .683 | .609 | .483 | 0.880 |
| S6 C=10 λ=0.85 | 687.0 | 30.1 | 636 | 615 | 10 | 486 | 10 / 47 | .687 | .589 | .479 | 0.851 |
| S7 C=10 λ=0.7 | 683.6 | 28.0 | 636 | 617 | 10 | 500 | 10 / 46 | .684 | .555 | .483 | 0.802 |

"n/a" marks a value the run did not report for that row. Stress tables are in `results.md`.

## k=100 (the realistic pool-to-k ratio: the real run has ~10x the rows)

- **Top-k is already diverse:** max exposure 3, 96 distinct keys, E 83.25, sd 3.90.
- **Caps C ≥ 3 never bind,** so every capped strategy equals its uncapped twin.
- **MMR λ=0.95:** E −0.08, sd 3.68, exposure 1.
- **Maximin leaders, all within 0.90-0.94:** S4 μ=0.1 (0.936), S1 λ=0.95 (0.928), S7 λ=0.85
  (0.926).

## Takeaways

1. **The `max` penalty saturates.** The median max-sim of the unselected pool is 0.30 at pick
   50 and 0.80 at pick 500. Plain MMR widens key coverage (386 → 501) but leaves maximum
   exposure at 97-104.
2. **A per-key cap is what controls tail risk.** C=10 cuts sd by 35% and worst-key loss from
   104 to 10, for −3% E.
3. **No dominant strategy.** The Pareto front of maximin vs p1 runs S1 λ=0.5 → S1 λ=0.7 → S6
   C=10 λ=0.5 → λ=0.7 → λ=0.85 → S2 C=10 → S7. S0, S5 and S3 are dominated.
4. **The S6 C=10 λ=0.5 hybrid is the best compromise:** maximin 0.935, p1 +11 against S0,
   sd −31%, worst loss 10.
5. **C=5 is too tight at this pool size.**
6. **Equal type quotas are the worst on risk:** at_event claims pile onto the event-date hubs.
7. **Caps lose on H2** because they push picks into fact and change claims on the same key,
   which share a base-key set. A cap on the base-key set as well as on the key is the next test
   (untested).

## Limitations

- **p_key is a hand-set proxy.** Only relative comparisons mean anything; absolute levels are
  pessimistic.
- **Lying pages are excluded by construction,** because observations come from TRUE rows. Only
  the lying-page stress test approximates the unlabelled run.
- **Keys fail independently.** A page lying on several keys would link their failures, which
  would favour spreading across subjects more than shown here.
- **No text rendering or referee validation.** Some candidates may be invalid, for example
  boolean at_event claims, which need the attribute words, or date `eq` compares.
- **Compare uses a single orientation.** Emitting both would double compare exposure.
