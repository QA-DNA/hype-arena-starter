# Evidence adversarial review

- Task: `task_949e043dcd49`. This is a read-only adversarial review of the evidence-graph upgrade.
- Owner: Claude worker, dispatched by the root coordinator. The root owns all code changes.
- Date: 2026-10-29
- Scope: `contracts/`, `crates/core/src/{claims,engine}.rs` at `d0af169`, `data/practice.csv`,
  and the latest recorded 1,000-claim output
  `../mvp-docker-qa/artifacts/benchmark-20261028-181943/output/output.csv` (mvp-docker-qa `ba18538`).
- Not reviewed: `evidence-graph-runtime/crates/core/src/knowledge.rs` did not exist when this review ran.
  The rules below are acceptance criteria for that file.
- Not run: Cargo is not on this host's PATH, so I did not regenerate claims or run tests.
  The 1k audit used the recorded output and a throwaway Node script against `practice.csv`.

## Summary

None of the 1,000 recorded claims is demonstrably false against the practice evidence.
- All 4 `eq` compares rest on identical exact days.
- No compare uses a partial date.
- Every immutable date that a `fact` or `compare` claim uses was observed on or after its own value date. This rules out forecasts.

The most serious risks are latent rules that the graph upgrade must not loosen, plus one contract ambiguity that affects 22 recorded claims.

## Findings, by risk

### P1: must hold in `knowledge.rs`

1. **A true row can state a forecast.** The label means the sentence is true on its page date. That does not mean the dated event had already happened.
   - Practice examples, all labelled true:
     - `Hooly I/O 2026|date = 2026-03-24`, observed 2026-02-01
     - `Hooly Cloud Next 2026|date = 2026-06`, observed 2026-01-21
     - `Hooly I/O 2026|date = 2026`, observed 2026-03-24
   - Rule: a date-valued fact becomes an occurrence only if one of these holds:
     - it is an exact day no later than the page date, or
     - it is a partial date whose whole interval ends before the page day.
   - This is `immutable_observation` today. Keep it for every graph-derived `fact`, `compare` and `at_event`.
2. **False rows.**
   - A false row with one fact proves only `value != v` on that date. Here `v` means the stated value, including its `op`.
   - The negation may become a positive value only for a boolean fact on that same date.
   - Example: p-274's attribute is false on 2026-03-24. If a single-fact boolean row asserting it true were labelled false, that would imply false on that date and nothing else.
   - Example: `Hooly|founded = 2024-06-01`, false on 2026-10-26, proves only "not 2024-06-01". It must never vote for `2025-01-14`.
   - A false row with more than one fact proves a disjunction. A fact can be marked false only when every other fact of that row is independently proven true on the same page date by a labelled-true row with no conflict that day.
   - Record the eliminating row ids as provenance. A negative derived this way must not resolve another compound in turn. Cap the derivation depth at 1, or carry the chain and refuse cycles.
3. **No circularity.** Only these may license a claim or a graph node:
   - labelled-true rows
   - single-fact false rows
   - the depth-1 eliminations from item 2

   Forest predictions, `memory` matches and generated claims must never enter the graph as evidence. Today `insert` filters `label != "true"`, and predicted-true rows are excluded. Keep both guarantees.
4. **Extracted facts from rows with a known label.** `generate_claims` inserts `prediction.facts` for every runtime row whose label is `true` (`claims.rs:93`).
   - In the official run, every labelled universe row is a practice row. The CLI also prepends `practice` with oracle forms (`cli/src/main.rs:74`). The same sentence therefore enters twice: once as its form, once as a template extraction that may be wrong.
   - If ids match, a mis-extraction creates a same-day conflict. This only loses recall.
   - If the universe re-ids rows, the mis-extracted fact stands alone. It can then produce false `change`, `at_event` or `relation` claims.
   - Fix: when a row with the same normalized text and date has an oracle form, drop its extracted facts.

### P2: latent bugs that are cheap to fix

5. **A partial-date `eq` claims the same day.** `compare` emits `eq` "is on the same day as" whenever `a.len() == b.len()` (`claims.rs:228-234`).
   - Two year-only values `2025` and `2025` would therefore be claimed as the same day. That is unproven and likely false.
   - Fix: allow `eq` only when both values have length 10.
   - `lt`/`gt` between equal-length partial dates is sound, because the intervals are disjoint.
   - For mixed precision, compare interval ends. `2025-11` vs `2025-12-01` gives `lt`. For `2025-11` vs `2025-11-18`, emit nothing.
6. **Inequality values are bounds, never values.**
   - `exact_value` correctly drops `op != eq`.
   - In the graph, a true `over 100 customers` row or a false single-fact `over 10,000 customers` row should only constrain or veto candidates. For example, it can reject a change whose `to` value violates a same-day bound. It must never be rendered as a value.
   - A date bound (`before March 2026`) may prove a `compare` between two *immutable past* dates only if the intervals are disjoint.
7. **Unit equality.**
   - `numeric_value` keys `month` and `year` as separate dimensions. The contract says `12 months` reads as 1 year, while months and years do not convert to days.
   - `same_value` therefore misses 12 month = 1 year. This is safe today, because `compatible` also fails and the change is skipped.
   - If the graph merges by `same_value`, add month↔year (×12) and keep both apart from days.
   - Compare scaled floats with a relative tolerance (1e-9) instead of `==`. That stops `1.2 GB` → `1,200 MB` ever becoming a non-change.

### P3: contract ambiguity and rendering

8. **Boolean changes.** There are 22 recorded claims of the form `Hooly had major outage changed from not to yes.`
   - The contract reads yes/no "from each side of a change phrase". The negation rule, however, also scopes over "the rest of the clauses it is in", and both sides share one clause.
   - A strict referee could read both sides as no, which would make the claim invalid.
   - Fix: lower their confidence below the compare/fact tier so MMR fills with them last, or drop them if the candidate pool exceeds 1,000 without them.
9. **Rendering.**
   - `render_value` groups thousands for quantities only. Money and durations in 1900–2099 (`EUR 2000`, `2000 ms`) risk being read as a year. Apply `group_number` to every numeric kind.
   - A non-percent value with exactly three decimals (`1.250 s`) reads as nothing. None appears in the recorded output.
10. **`at_event` boundary.** The referee gives the *new* value on a change day. A page dated on the event day may state the old value.
    - The `has_day_conflict` check covers this only when both values appear that day.
    - Fix: also refuse a candidate when a labelled-false single-fact row on that date states the same value.
11. **Hindsight is allowed.** Using a later page to judge an earlier row's *immutable* date is not leakage: a later page can be "the dataset's means to tell". The engine's `e.date <= row.date` filter forgoes this. It is a recall opportunity for labelling, not a correctness bug.

## 1k audit

| Type | Count | Result |
| --- | --- | --- |
| compare | 674 | No partial-precision values. The 4 `eq` claims are exact identical days. One example is Hooly founded = Hooly Berlin Office opened = 2025-01-14. A false row says Berlin opened 2025-02-03, which is consistent with that row being false. |
| change | 233 | 22 boolean changes have the ambiguity in item 8. |
| fact | 40 | Immutable exact dates, each observed after its value date. |
| at_event | 37 | Page date equals the event date. One correct negation-polarity example: `Hooly Meet cloud recording was not cloud recording at Hooly I/O 2026.` |
| relation | 16 | Link and target are observed on the same page date. |

Separately, the 674 compares make 67% of the output a single type. If novelty or diversity is judged, rebalance MMR by type before adding more date compares.

## Regression fixtures

`artifacts/evidence-adversarial-fixtures.json` is ignored by Git. It holds minimal cases for items 1, 2, 5, 6 and 7, each with its expected outcome.

## Next steps (root)

1. Encode items 1–5 as tests in `knowledge.rs`/`claims.rs`.
2. Re-run `cargo xtask test` and regenerate the 1k claims.
3. Re-audit the new output against this list.
