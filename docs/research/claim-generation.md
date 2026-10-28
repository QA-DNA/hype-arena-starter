# Claim generation research

Status: research for the team, 2026-10-28, split out of [the knowledge base research](knowledge-base.md)
so the generator stays a separate component. Owner: Edi (mogaeduard). Scope: turning knowledge base
answers into exactly 1,000 true claims. The generator reads the KB and never stores or decides facts.
Diversity in the selection is covered by [the MMR research](mmr.md).

## What the generator asks the KB

| KB query | Returns | Claim types it feeds |
| --- | --- | --- |
| `value_at(key, date)` | value, P(true), support (independent pages, anchors) | `fact`, `compare` |
| `transitions(key)` | change date, old value, new value, P(true) | `change` |
| `value_at_event(key, event)` | value on the event date, P(true) | `at_event` |
| `linked(subject, link, date)` | linked entity, interval the link held, P(true) | `relation` |
| `witnesses(key, date)` | supporting and contradicting rows | explanation of each claim |

Anything else the generator needs is a new KB query, agreed first, not a lookup into KB internals.

## Pipeline

1. **Candidates.** `change` between two labelled true values; `at_event` where the event date
   falls between two anchors of the same value; `relation` while the link held; `fact` and
   `compare` only from values confirmed at the latest dates.
2. **Score.** The product of the fact P(true) values the KB returned for the claim.
3. **Filter.** Require two independent pages or an anchor behind every fact a claim uses.
4. **Select 1,000.** Greedy by score with type quotas and a cap per root fact, so one wrong fact
   cannot sink many claims; diversity per [the MMR research](mmr.md).
5. **Render.** Text and `form` in the claim grammar (`contracts/claim-forms.md`), values written
   as `contracts/value-forms.md` writes them.
6. **Self-check.** Run every claim through a mirror of the referee rules and replace each failure
   with the next candidate.
7. **Confidence.** The calibrated score, from 0.5 to 1.

Insanity 2 to 3 overall.

## Measured facts the generator must respect

From the KB experiments on `data/practice.csv` ([lab](../../labs/kb-experiments/README.md)):

- **As-of values are the riskiest.** Hiding the last 20% of dates (cut 2026-09-03), the latest
  earlier anchor equals the final value for only 53% of keys (75.5% coverage). Build most claims
  from `change`, `at_event` and `relation` anchored on labelled true facts.
- **Conformal selection is weakened by shared facts.** Benjamini-Hochberg assumes near-independent
  p-values; claims that reuse one fact are correlated, so cap claims per root fact first.
- **A lie on the last page of a key** is the most dangerous case for a `fact` claim, hence the
  two-source filter.

## Contract details for the generator

From `contracts/README.md`:

- Exactly 1,000 claims. Claims after the 1,000th are not judged; an invalid claim and a row that
  is not CSV still take their place in the 1,000, and a missing claim scores nothing.
- Every claim must be true (`label` is `true` or empty) and new (its text is not an input row).
- A claim's value is exact and carries no `op`; "more than" between two facts is a `compare`.
- On the day a value changes, it already holds the new one (claim-forms, Compare section).

## Catalogue

### Greedy claim selection with type quotas and a root-fact cap

- **Kind:** design · **Verdict:** ADOPT · **Insanity:** 2/5
- **What:** Generate far more than 1,000 candidates, score each by the product of P(true) of the facts it rests on, cap how many claims may share one fact, fill per-type quotas greedily by score.
- **Fit here:** Measured: carrying the latest anchor forward is unsafe for as-of claims: hiding the last 20% of dates, the latest earlier anchor matches the final true value for only 53.4% of keys (coverage 75.5%). One wrong fact would otherwise sink many claims at once; the cap bounds that correlated loss and enforces diversity across fact, compare, change, at_event and relation.
- **Pros:** About 30 lines; Exactly enough for knapsack-with-quotas
- **Cons:** Quotas trade a little precision for diversity
- **Rust:** std (good_lp + microlp only if pairwise constraints are added)
- **Python (labs):** numpy
- **Why this verdict:** Precision-at-k with correlated risk, solved simply.
- **Sources:** not verified

### Referee-mirror self-check for generated claims

- **Kind:** design · **Verdict:** ADOPT · **Insanity:** 2/5
- **What:** Before writing output.csv, re-parse every generated claim text with our own implementation of claim-forms.md and value-forms.md (one sentence, subject named, no second value or date, no negation, no time words) and re-label its form with our own labeller at the claim's date.
- **Fit here:** The referee is deterministic and published; an invalid claim still takes one of the 1,000 slots, so a mirror check removes a whole class of losses. Also check 'new': the text must not equal an input row.
- **Pros:** Catches invalid claims before submission; Doubles as a test suite from the contract's examples
- **Cons:** The mirror must be kept faithful to the contract
- **Rust:** about 200 to 300 lines with the contract examples as tests
- **Python (labs):** prototype in labs
- **Why this verdict:** Cheapest large reduction of claim risk.
- **Sources:** not verified

### Conformal selection with Benjamini-Hochberg (FDR control)

- **Kind:** paper · **Verdict:** TRY · **Insanity:** 3/5
- **What:** Conformal p-values per candidate plus BH so the expected false discovery rate among selected claims is at most alpha (Jin and Candes 2023; e-variable follow-up 2026).
- **Fit here:** Gives a principled 'expected wrong claims at most X' statement. It controls expected FDR, not 'all 1,000 true', and correlated claims weaken it.
- **Pros:** The principled answer to picking items that are all true
- **Cons:** Needs exchangeable calibration claims; About 10 expected errors at 1% FDR
- **Rust:** about 40 lines
- **Python (labs):** numpy
- **Why this verdict:** Framing on top of greedy; modest accuracy gain.
- **Sources:** <https://arxiv.org/abs/2210.01408> · <https://arxiv.org/abs/2604.11305>

### Temporal QA and fact-verification benchmarks (TempTabQA, FEVEROUS, ChronoFact)

- **Kind:** benchmark · **Verdict:** IDEA-ONLY · **Insanity:** 1/5
- **What:** TempTabQA: temporal QA over infobox tables (EMNLP 2023). FEVEROUS: verification against sentences and table cells (2021). ChronoFact: timeline-based temporal fact verification (IJCAI 2025).
- **Fit here:** ChronoFact's idea (order the claim's events and the evidence's events on timelines, then judge each claim event) is our pipeline in neural form; the others motivate which temporal operations matter.
- **Pros:** Validates the timeline framing
- **Cons:** All neural or LLM-oriented evaluation
- **Rust:** n/a
- **Python (labs):** n/a
- **Why this verdict:** Context and vocabulary only.
- **Sources:** <https://arxiv.org/abs/2311.08002> · <https://arxiv.org/abs/2106.05707> · <https://arxiv.org/abs/2410.14964>
