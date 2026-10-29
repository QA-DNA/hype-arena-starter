# Implementation plan: Hype or Truth (QA DNA, NEXXT AI Hackathon)

Sources: `README.md`, `contracts/README.md`, `contracts/claim-forms.md`, `contracts/value-forms.md`,
`contracts/entry.schema.json`, `scripts/check.sh`, `scripts/check_output.py`, <https://hype-arena.vercel.app>.
Dates: today is 28 Oct 2026; the sample drops 09:00 on 29 Oct; **freeze 11:00 on 29 Oct**.

## 1. Goal

One offline Docker system that reads `/universe/universe.csv` (~20k rows: `id,text,date,label`) and writes
`/output/output.csv` with (a) a label + confidence for every row whose `label` is empty (~18k) and (b) exactly
1,000 new true claims. Delivered as one PR from our fork. The required frontend (architecture diagram + live run) is built separately in Lovable and is out of scope here.

## 2. Hard rules (a violation disqualifies or zeroes us)

| Rule | Consequence for the design |
|---|---|
| The system may not be an LLM | Runtime is rules + classical ML only. LLMs only help write code / training material. Keep a log of where an LLM helped. |
| Offline run, 2 CPUs, 6 GiB, 30 min, 256 procs, read-only root | No model downloads at runtime. Bake everything into the image. `HOME`, caches -> `/tmp`. Write only `/tmp` (128 MB) and `/output`. |
| Image <= 3 GiB, `docker build --platform linux/amd64 .`, ends with `USER 10001` | Small base image; no torch/transformers. |
| SIGTERM at deadline (`ARENA_DEADLINE`), table on disk counts | Write a valid baseline table first, then write `output.tmp` and rename to `output.csv` atomically after each improvement. |
| Truth = what the universe says | Never use web or pretrained knowledge. |
| Exactly 1,000 claims; first 1,000 judged; invalid ones still occupy slots | Generate > 1,000 candidates, validate each, keep the best 1,000, all valid. |
| Claims must be true, new (not a row of the input), pass the referee (`claim-forms.md`, `value-forms.md`, `entry.schema.json`, lexicon names) | We must write our own referee: `check.sh` does **not** check claim text/form/names. |
| Fork, PR titled with team name, opened before 11:00; any push/close after 11:00 disqualifies | Last push at 10:00 at the latest; no "one more fix" after that. |
| Frontend shows an architecture diagram and runs the system live; video of it on `sample/sample.csv` | Built in Lovable (not in this plan). Our side only keeps `pipeline(rows) -> table` callable, so the frontend has something to run. |

## 3. What the data tells us (practice.csv, lexicon.json)

- 1,897 rows, 159 dates (2025-10-07 to 2026-10-28). Labels: 1,581 true, 277 false, 39 unsure (83/15/2%). The all-true baseline is ~83%.
- `form` = list of facts `{subject, attribute, value{kind,...}}`. 27% of rows state 2+ facts; the row is false if any fact is false.
- Lexicon: 62 subjects, 514 subject-attributes, 13 events. 8 value kinds: quantity, money, duration, name, percent, boolean, date, version (+ optional `op`).
- 252 of 502 observed facts take several values over time, so we need a timeline per (subject, attribute).
- Surface noise: "Nimbus" vs "Nimbus Cloud", `2026-01` vs `2026-01-12`, "over 100 customers" (`op: gt`).
- Rows lack context: "He begins with..." needs the previous rows (same date, sequential ids).
- The input has **no `form` column** and practice is ~10% of it. Text -> facts is the core problem.
- The image may contain `practice.csv` (with forms). So `check.sh` label counts are an upper bound (it knows the hidden labels). We need our own leak-free evaluation.

## 4. Architecture

```
universe.csv ──► [1 Parse] ──► facts (subject, attribute, value, date, row ctx)
                     │
practice.csv ──► [2 Truth timeline] ◄── [3 Consensus over unlabelled rows]
 (baked in)          │
                     ▼
              [4 Judge + features] ──► [5 Calibrate] ──► label, confidence ─┐
                     │                                                        ├─► output.csv
              [6 Claim generator] ──► [7 Referee (own validator)] ──► 1,000 ─┘
```

Modules (Python package `hype/`, stdlib + scikit-learn/numpy only):
`lexicon.py`, `values.py` (parse + render per value-forms), `parse.py` (subject/attribute/value), `timeline.py`,
`judge.py`, `calibrate.py`, `claims.py`, `referee.py`, `run.py` (entrypoint).

Key decisions:
1. **Truth by timeline, not by text similarity.** Each row becomes facts; each fact is compared with the value history of (subject, attribute) at the row's date.
2. **Calibration is first-class.** Scoring is confidence-weighted: confident-and-wrong is the expensive error. Output `unsure` when calibrated p is near 0.5 (the contract says unsure = no means to tell).
3. **Referee first, claims second.** Write the validator from the published rules and the repo's `examples/*/bad` and `good` files before generating claims.
4. **One `pipeline(rows) -> table` function**, used by `run.py` and callable by the Lovable frontend.
5. **Honest evaluation.** Grouped K-fold by date; truth and models built only from training folds; report accuracy, log-loss and a calibration table.

## 5. Dependency graph

```
T1 repo+Docker skeleton ─► T2 baseline run (check.sh green) ─► T3 eval harness
                                   │                                  │
          T4 lexicon+values parser ┴─► T5 subject linker ─► T6 attribute model ─► T7 first judge (labels beat baseline)
                                                                                      │
                                                         T8 timeline ─► T9 consensus ─► T10 calibrate+unsure
T11 referee (needs T4 values) ─► T12 fact+change claims ─► T13 event/relation/compare ─► T14 select 1,000
T17 harden+scale test ─► T18 sample run ─► T19 freeze
```

T4/T11 (values) and T8 (timeline) can run in parallel with different people after T3.

## 6. Phases and checkpoints

### Phase 0 — Walking skeleton (valid output end to end)
- **T1** Fork, clone, layout, `requirements.txt`, Dockerfile (`USER 10001`, `HOME=/tmp`).
- **T2** Baseline `run.py`: label every blank row `true` at the practice prior, plus 1,000 claim rows (simple, may be partly invalid), atomic write. `scripts/check.sh` passes.
- **T3** `scripts/eval.py`: grouped-by-date K-fold, leak-free; prints accuracy, log-loss, calibration bins; records baseline.
- **Checkpoint A:** `check.sh` exit 0, no problems; baseline numbers written to `tasks/results.md`.

### Phase 1 — Understand text (rows -> facts)
- **T4** `values.py`: parse the 8 value kinds per `value-forms.md` (units, scales, ops, approximations, negation, ranges, dates) and normalise for comparison. Test with every example table in the doc.
- **T5** Subject linker: alias matching (longest, whole word, "Hooly AI Pro" is not "Hooly"), plus context from neighbouring rows for pronouns.
- **T6** Attribute model: TF-IDF + logistic regression restricted to the subject's lexicon attributes and the value kind.
- **T7** First judge: parsed fact vs timeline built from training labels -> label. Wire into `run.py`.
- **Checkpoint B:** on grouped CV, accuracy > baseline by a clear margin; parse recall on gold forms reported. If attribute accuracy < ~80%, spend more time here before moving on.

### Phase 2 — Truth and confidence
- **T8** Timeline: per (subject, attribute) intervals from true rows; handle name aliases, date precision, `op` values.
- **T9** Consensus: truth discovery over unlabelled rows to cover facts practice never mentions (repeated values across pages = likely true; outliers = likely false/stale).
- **T10** Features -> calibrated p(true) (isotonic) -> true/false/unsure thresholds tuned on CV.
- **Checkpoint C:** log-loss better than baseline, calibration table roughly diagonal, unsure rate small (practice has 2%).

### Phase 3 — Claims
- **T11** `referee.py`: checks form against `entry.schema.json`, names/attributes against lexicon, text against `claim-forms.md` and `value-forms.md` (one value/date, no negation/time words/approximation, subject named in the sentence, "Hooly" vs "Hooly AI Pro"). Tests use `contracts/examples/entry/{good,bad}` and the doc tables.
- **T12** Value renderer + `fact` and `change` claims (vertical slice: generate -> referee -> output).
- **T13** `at_event`, `relation`, `compare` claims (events from the lexicon; links such as `cto`).
- **T14** Select exactly 1,000 from validated candidates: balanced types, distinct subjects/attributes, dedupe against input texts, confidence from timeline stability (value unchanged and corroborated recently).
- **Checkpoint D:** 1,000/1,000 pass our referee; zero equal to any input row; mix by type reported.

### Phase 4 — Hardening
- **T17** Harden: synthetic ~20k rows, time/memory, SIGTERM, image < 3 GiB.
- **Checkpoint E:** `MINUTES=30 scripts/check.sh` green with margin (target < 10 min).

### Phase 5 — Submission (29 Oct)
- **T18** 09:00 pull `sample/sample.csv`, run `pipeline` on it and hand the output to whoever records the Lovable video.
- **T19** README for judges (LLM-use log), open PR named after the team by 10:00, final push, then **stop pushing**.

## 7. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Practice covers only part of the universe | Timeline has gaps for most rows | T9 consensus; `unsure` fallback with calibrated low confidence |
| Attribute classification errors | Wrong fact compared | Restrict to subject attributes and value kind; abstain when top-2 are close |
| Over-confident wrong labels | Heavy score penalty | Isotonic calibration, cap confidence (e.g. 0.95) unless several sources agree |
| Claim text rejected by referee | Slot lost (invalid claims still count) | Own referee, generate 2-3x candidates, only emit validated ones |
| Attribute words contain time words (`uptime_last_quarter`, `joined`) | Fact text invalid | Referee checks; renderer falls back to a neutral phrasing |
| Claim true on 29 Oct but the fact changes later | Not an issue: judged on the as-of date | Prefer facts unchanged in recent pages |
| `check.sh` over-reports (image holds practice labels) | False confidence | Rely on T3 grouped CV, not on check.sh counts |
| Late-night scope creep | Missing the freeze | Phase 0 first; every checkpoint leaves a submittable repo |

## 8. Open questions (need answers, none block Phase 0)

1. Team size and names (decides the parallel split of T4/T8/T11).
2. Team name for the PR title; the fork's URL.
3. Is Docker installed locally (needed for `scripts/check.sh`)?
4. Python version preference (default: 3.12-slim).
