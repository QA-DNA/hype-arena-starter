# Frontier sweep (2025-2026) and inexact values

Raw report from the 2026-10-28 knowledge base research, kept as written by the worker so nothing is lost. The curated version, with verdicts reconciled against the contract and the measured results, is [the knowledge base research](../knowledge-base.md).

- **Author:** W4, Claude Sonnet 5.5 research worker.
- **Scope:** frontier papers and repos, S4 inexact values and value-consistency rules.
- **Tools:** free tools only (WebSearch, WebFetch, GitHub, crates.io, arXiv); no paid research service.
- **Citations:** Citations the worker marked "not verified" were checked afterwards where possible; the verified URLs are listed in [the notes index](README.md#verified-citations).
- **Corrections:** three claims contradicted the contract; each is marked inline with "Correction (contract)".

## TLDR
- The web tools returned almost nothing from 2025-2026 on temporal truth discovery or LLM-free temporal fact verification. The newest relevant items I could verify are a 2026 TKDE paper (HMM truth discovery) and a 2025-12 conformal paper. Nothing found is a drop-in solution.
- The problem is classical: per-key timelines, source weights fitted by EM (CRH / TruthFinder / Dawid-Skene style) and typed-interval consistency. All of it is small enough to hand-write in Rust, and no crate is needed.
- For Part B, represent every proposition as an allowed interval of the true value, and treat "consistent" as a non-empty intersection. A ~150-line hand-rolled enum beats `inari`, `uom` and `measurements` here. `inari` is the only interval crate I verified, and I could not check how heavy its build is.
- For S6 calibration, use Platt or isotonic scaling plus abstention thresholds on the ~10% anchors. Conformal and selective-risk-control papers exist (2025-12, 2026-04) but are LLM-oriented. Take the idea only.
- Skip all neural, graph-neural and Python-only stacks (Snorkel, crowd-kit) at runtime. Use them only as lab references.

## Part A: entries
Search coverage was thin (about 8 queries), so absence from this list is not evidence that a technique doesn't exist.

### On the discovery of evolving truth (paper, KDD 2015)
- Link: https://cse.buffalo.edu/~jing/doc/kdd15_evolve.pdf (no code verified)
- What it does: incremental truth discovery where both the truth and source reliability evolve as data arrives.
- Steps: S1, S2, S3
- Pros / Cons:
  - Pro: it is the right model, with a truth per time slice and source weights updated online.
  - Con: it is old, and I found no code.
- Rust: port ~200 lines. Python: none verified.
- Fit here: our sentences arrive dated, so we can sweep in date order, keep the current value per key, and update page reliability from the anchors.
- Verdict: ADOPT (idea). Insanity 2

### Time-series truth discovery with SARIMA (paper, SDM 2018)
- Link: https://engineering.purdue.edu/~lusu/papers/SDM2018.pdf
- What it does: forecasts how truth evolves and jointly estimates source weights.
- Steps: S2, S3
- Pros / Cons:
  - Con: it assumes smooth numeric series, but our values jump (a price change, a version bump).
- Rust: n/a. Python: none verified.
- Fit here: prices and quantities are step functions.
- Verdict: IDEA-ONLY (use step persistence instead). Insanity 3

### Reliable truth discovery for dynamic and dependent sources (paper, IEEE TKDE vol. 38, 2026)
- Link: https://research.buaa.edu.cn/en/publications/reliable-truth-discovery-for-dynamic-and-dependent-sources/
- What it does: an HMM over time series that models source dependence (copying) and source reliability that changes over time. Not LLM-based.
- Steps: S2
- Pros / Cons:
  - Pro: it is the newest verified item.
  - Pro: lying pages and copying pages are both modelled.
  - Con: no code found, and I read only the abstract page.
- Rust: HMM forward pass ~100 lines.
- Fit here: "some pages lie" can be a two-state HMM per page (honest or lying). Page-level state is cheap to fit from the anchors.
- Verdict: TRY (page honest/liar latent state). Insanity 3

### Time-sensitive truth discovery in social sensing (paper, 2015)
- Link: https://experts.illinois.edu/en/publications/towards-time-sensitive-truth-discovery-in-social-sensing-applicat/
- What it does: maximum-likelihood estimation with claim lifespan and source responsiveness.
- Steps: S2, S3
- Pros / Cons:
  - Pro: claim lifespan maps to validity intervals.
  - Con: it is geared to social-media streams.
- Verdict: IDEA-ONLY. Insanity 2

### Temporal point processes for reliability (paper, arXiv 1610.07472, 2016)
- Link: https://ar5iv.arxiv.org/html/1610.07472
- What it does: models verification and refutation events over time.
- Steps: S2
- Verdict: REJECT. Weak fit and old. Insanity 4

### Survey on Truth Discovery (paper, 2015)
- Link: https://arxiv.org/pdf/1505.02463
- What it does: catalogues TruthFinder, AccuSim, CRH, CATD, GTM, ZenCrowd and others, including implication functions for similar values.
- Steps: S2, S4
- Pros / Cons:
  - Pro: it is the reference for value-similarity-aware voting.
- Rust: a CRH-style loop is ~60 lines (weights from loss, weighted vote, iterate).
- Fit here: categorical and typed values with a distance function map to CRH with a typed loss.
- Verdict: ADOPT (CRH or TruthFinder with implication). Insanity 2

### TruthFinder and AccuSim implication (algorithm, 2008 / 2009)
- Link: no URL verified; see the survey above for the formulas.
- What it does: a claim's confidence also receives support from similar claims (positive implication) and loses it to conflicting ones (negative implication). Source trust is the mean of its claims' confidences.
- Steps: S2, S4
- Pros / Cons:
  - Pro: it handles "gt 100" next to "eq 120" natively if the implication function is the interval rule from Part B.
  - Con: it is a heuristic with a damping parameter. It needs a sigmoid and a normalisation tweak.
- Rust: port ~80 lines.
- Fit here: this is exactly our situation, with implication = interval agreement.
- Verdict: ADOPT. Insanity 2

### Frustratingly Easy Truth Discovery (paper, 2019)
- Link: https://arxiv.org/pdf/1905.00629
- What it does: a simple baseline that is competitive with heavier methods.
- Steps: S2
- Verdict: TRY as the first baseline. Insanity 1

### Crowd-Kit (library, Toloka)
- Link: https://github.com/Toloka/crowd-kit (last push 2025-12-01, 255 stars)
- What it does: Python implementations of Dawid-Skene, GLAD, MACE, MajorityVote and more.
- Steps: S2, S6
- Rust: no Dawid-Skene crate found. crates.io search returned only unrelated results. Hand-port ~120 lines.
- Python: `crowd-kit` for lab cross-checks.
- Fit here: use it as the reference for validating the Rust EM.
- Verdict: TRY (lab only). Insanity 1

### Python `truthdiscovery` package (library)
- Link: https://truthdiscovery.readthedocs.io (code activity not verified)
- What it does: TruthFinder, Investment, Sums and similar algorithms.
- Verdict: IDEA-ONLY (lab reference). Insanity 1

### Snorkel (library, label model)
- Link: https://github.com/snorkel-team/snorkel (last push 2026-10-13, 6.0k stars)
- What it does: labelling functions combined by a generative label model. Not an LLM at runtime.
- Steps: S6
- Pros / Cons:
  - Pro: this is the right frame, with each rule or source as a labelling function.
  - Con: the library is heavy.
- Rust: none. Port the core, a matrix-completion or EM weighting, in ~100 lines.
- Verdict: IDEA-ONLY. Insanity 2

### FlyingSquid (library, weak supervision)
- Link: https://github.com/HazyResearch/flyingsquid (last push 2020-09-01)
- What it does: a closed-form label model.
- Verdict: IDEA-ONLY. Insanity 2

### TempTabQA (benchmark, EMNLP 2023)
- Link: https://arxiv.org/pdf/2311.08002
- Code: github.com/temptabqa/temptabqa (last push 2025-03-05, 7 stars). TEMPTABQA-C at github.com/CoRAL-ASU/TEMPTABQA-C (2025-07-28).
- What it does: 11,454 temporal QA pairs over 1,208 Wikipedia infobox tables.
- Steps: S1, S3
- Pros / Cons:
  - Pro: it shows which temporal operations matter (duration, ordering, as-of).
  - Con: the evaluation is LLM-oriented.
- Fit here: it motivates the S7 claim types, such as compare, change and at_event.
- Verdict: IDEA-ONLY. Insanity 1

### FEVEROUS (benchmark, NeurIPS 2021)
- Link: https://arxiv.org/pdf/2106.05707
- What it does: 87k claims verified against sentences and table cells.
- Steps: S1, S5
- Pros / Cons:
  - Con: its baseline reaches about 18% joint evidence and verdict accuracy, and it is not a temporal benchmark.
- Verdict: IDEA-ONLY. Insanity 1

### ChronoFact, TimeBench, TRAM, TimeQA, SituatedQA, TemporalWiki
- I could not verify any of these. See "Not found".

### Selective Conformal Risk Control (paper, 2025-12)
- Link: https://arxiv.org/abs/2512.12844
- What it does: a two-stage method. It first selects confident samples, then applies conformal risk control on the selected subset.
- Steps: S6
- Pros / Cons:
  - Pro: it is distribution-free, which suits our small anchor set.
  - Con: it assumes exchangeability, and our labelled anchors are not guaranteed to be representative of the unlabelled rows.
- Rust: split-conformal threshold ~30 lines.
- Fit here: use it to set the abstention (unsure) threshold on the ~2,000 anchors.
- Verdict: TRY. Insanity 2

### Adaptive conformal prediction for LLM factuality (paper, 2026-04)
- Link: https://www.alphaxiv.org/abs/2604.13991.md (I did not open the full text)
- What it does: filters unreliable claims through selective prediction.
- Verdict: IDEA-ONLY (LLM-based). Insanity 1

### Platt scaling and isotonic regression (algorithm)
- What it does: standard post-hoc probability calibration.
- Steps: S6
- Rust: `smartcore` 0.7.0 (587k downloads, updated 2026-10-26) and `linfa` 0.8.1 (2.0M downloads, 2025-12-23) have no verified isotonic. Hand-write pool-adjacent-violators, ~40 lines.
- Python: scikit-learn for labs.
- Verdict: ADOPT. Insanity 1

### SDM 2018 / HMM idea, combined with Allen relations for event ordering (algorithm)
- Allen interval algebra crates: `allen_interval_algebra` (4.9k downloads, 2023-06-02), `allen-intervals` (753 downloads, 2025-05-14), `interavl` (102k downloads, 2026-04-16, an interval tree).
- Steps: S1, S3
- Pros / Cons:
  - Con: none is mature.
- Rust: hand-write the 13 Allen relations, ~30 lines. For as-of lookup a sorted `Vec` plus `partition_point` is enough.
- Verdict: ADOPT hand-rolled. Insanity 1

### Rust date and calendar crates
- `jiff` 0.2.38 (247M downloads, 2026-10-06), `time` 0.3.55 (1.0B, 2026-08-01) and `iso8601` 0.6.6 (45M, 2026-09-10) all exist.
- Steps: S1, S4
- Fit here: `jiff` for day-precision arithmetic. Precision handling (year, month, day to interval) is trivial by hand.
- Verdict: ADOPT `jiff` (or `time`). Insanity 1

## Part B: tools and libraries
### `inari` (crate, interval arithmetic)
- Link: crates.io/crates/inari, v2.0.0, 66k downloads, last update 2024-08-07
- What it does: a rigorous f64 interval library.
- Steps: S4
- Pros / Cons:
  - Pro: correct rounding.
  - Con: stale (two years), and I could not verify its dependency or build cost (it may pull in `gmp-mpfr-sys`).
  - Con: it is overkill for comparing "gt 100" with "eq 120".
- Verdict: REJECT. Write `struct Iv { lo: f64, hi: f64, lo_open: bool, hi_open: bool }`. Insanity 1

### `uom` (crate, units of measure)
- Link: crates.io/crates/uom v0.38.0, 14.4M downloads, 2026-02-14
- What it does: compile-time dimensional analysis.
- Pros / Cons:
  - Con: it is static typing, but our units arrive at runtime as strings. It also has no "counted noun" concept.
- Verdict: REJECT. Use a runtime table: GB/MB by 1000 or 1024 (decide once, check the practice data), and h/min/day/week to seconds. Months and years stay as their own dimension. Insanity 1

### `measurements` (crate)
- Link: crates.io/crates/measurements v0.11.1, 5.3M downloads, 2025-10-18
- Verdict: REJECT, same reasoning as `uom`.

### `dimensioned` (crate)
- Link: crates.io/crates/dimensioned v0.8.0, 1.2M downloads, last update 2022-04-29
- Verdict: REJECT (stale).

### `rust_decimal` (crate)
- v1.43.0, 165M downloads, 2026-09-02
- What it does: exact decimal arithmetic.
- Fit here: only needed if f64 rounding at money boundaries bites.
- Verdict: IDEA-ONLY. `f64` plus an epsilon is enough.

### `semver` (crate)
- v1.0.28, 1.1B downloads, 2026-04-04
- Fit here: "versions compared as written" is not strict semver, because versions such as "2.4" or "v3" may not parse. Compare dot-separated integer tuples yourself and use `semver` only as a fallback.
- Verdict: IDEA-ONLY.

### `pint` (Python, labs)
- Not verified here. Use it in the lab for cross-checking the Rust unit table.

## Part B recommended value-consistency rules

Concrete Rust representation:

```rust
enum Val {
    Qty { v: f64, unit: Dim },
    Money { v: f64, cur: Cur, per: Option<Period> },
    Pct(f64),
    Date { y: i32, m: Option<u8>, d: Option<u8> },
    Dur { v: f64, unit: DurUnit },
    Ver(Vec<u32>),
    Name(String),
    Bool(bool),
}

struct Prop { val: Val, op: Op }

fn to_interval(&self) -> Iv; // for the ordered kinds
```

Op mapping for numeric kinds: eq to [v, v]; gt to (v, +inf); ge to [v, +inf); lt to (-inf, v); le to (-inf, v].

Rounding tolerance for approximate wording: widen eq by a relative epsilon, or by the written precision (half a unit in the last written digit).

> **Correction (contract):** there is no rounding tolerance. Values are exact, and approximate wording (about, around, roughly, `~` and the rest) makes a value read as nothing, so the entry is invalid ([value forms](../../../contracts/value-forms.md), "Approximate"). Do not widen `eq`.


| Value kind | Interval representation | Agree / contradict / unknown rule |
|---|---|---|
| Quantity (convertible units) | Convert to a base unit (bytes), then the op interval | Agree if intervals intersect and one is a point inside the other. Contradict if the intersection is empty. Unknown if the units are in different dimensions. |
| Counted noun | Count in "customers" etc., op interval | Same noun required. Different noun is unknown. |
| Money | Op interval, keyed by (currency, period) | Same currency and same period: numeric rule. Different currency: unknown (no FX table). Missing period vs. present period: unknown, not a contradiction. |
| Percent | Op interval on 0-100 | Numeric rule. |
| Date | Year gives [Jan 1, Dec 31], month gives the month, day gives a point. An op of lt/gt gives a half-line. | Agree if the intervals intersect (2025-11 vs 2025-11-04 agree). Contradict if disjoint. A year-only claim on the same year as a day-precise one is compatible, not "equal". |
| Duration | Seconds for h/min/day/week | Months and years stay in their own dimension and never convert to days. Cross-dimension is unknown. |
| Version | Integer tuple, compared lexicographically (as written) | Only eq, gt, ge, lt, le are comparable. A "2.4" vs "2.4.0" difference is a policy call; recommend padding with zeros. |

> **Correction (contract):** versions compare as written, so `2.3` is not `2.3.0`. Do not pad with zeros. Names resolve through the lexicon aliases, so the Name row's "aliases are not handled" does not hold either. The Date row's interval agreement (`2025-11` vs `2025-11-04`) is unconfirmed: the contract reads a date as precisely as it is written.

| Name | Normalised string (lowercase, trimmed) | eq matches or conflicts. Aliases are not handled. |
| Boolean | {true} or {false} | Differing values contradict. |

Edge cases to settle on the practice data:
- Two op-claims against each other: "gt 100" vs "lt 50" gives an empty intersection, so contradiction. "gt 100" vs "gt 50" intersect and agree.
- A truth that is a point checked against an inequality: eq 120 with gt 100 is true, and eq 100 with gt 100 is false (open bound).
- A row with several propositions is false if any one is false. For blame (S5), rank propositions by contradiction margin, with the most contradicted one as the culprit.
- Rounded wording ("1.2 million" vs 1,234,567): treat "1.2 million" as [1.15M, 1.25M). Agree if it falls inside, which 1,234,567 does.

> **Correction (contract):** `1.2 million` is exactly 1,200,000 and does not agree with 1,234,567.

- Check the practice labels to learn whether "unsure" corresponds to the "unknown" outcomes above.

## Not found / unverified
- No 2025 arXiv paper on temporal truth discovery turned up. The "2025-2026" truth-discovery papers I could find are the 2026 TKDE one and the repos listed above.
- I found nothing on ChronoFact, TimeBench, TRAM, TimeQA, SituatedQA or TemporalWiki as fact-verification datasets, so I cannot vouch for them.
- No Kaggle data-fusion or KDD Cup truth-discovery competition was found.
- `exa` via `mcporter` returned no output. `timeout` isn't available on this Mac's shell, so the loop only reported empty results. I did not retry.
- The arXiv API sorted by date returned unrelated October 2026 papers. Queries were OR-ed, so arXiv coverage is effectively nil.
- The GitHub repos from my search (SourceBridge, ModeSet, LIR-PPTD and others) have no stars and no description I checked. I did not read them.
- No Dawid-Skene crate was found on crates.io. The search results were unrelated.
- No Rust conformal or isotonic crate was verified.
- `inari`'s build dependencies and `uom` runtime unit parsing were not checked in code.
