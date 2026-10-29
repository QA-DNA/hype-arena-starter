# Todo: Hype or Truth

Freeze: **11:00, 29 Oct 2026** (last push by 10:00). Plan: `tasks/plan.md`.

## Phase 0 — Walking skeleton
- [ ] **T1** Fork + clone; `hype/` package, `requirements.txt`, Dockerfile (`USER 10001`, `HOME=/tmp`)
  - AC: `docker build --platform linux/amd64 .` succeeds; image runs as 10001
- [ ] **T2** Baseline `run.py` (all blank rows `true` at prior, 1,000 claim rows, atomic `output.tmp` -> `output.csv`)
  - AC: `scripts/check.sh` exits 0, no problems printed
  - Verify: `MINUTES=5 scripts/check.sh`
- [ ] **T3** `scripts/eval.py`: grouped-by-date K-fold, leak-free; accuracy, log-loss, calibration table
  - AC: baseline numbers saved in `tasks/results.md`
- [ ] **Checkpoint A**

## Phase 1 — Rows to facts
- [ ] **T4** `values.py`: parse 8 value kinds + ops + rejections per `value-forms.md`
  - AC: every example table in `value-forms.md` passes as a unit test
- [ ] **T5** Subject linker (aliases, longest match, neighbour-row context)
  - AC: subject recall on practice gold forms reported (target >= 95%)
- [ ] **T6** Attribute model constrained by subject attributes + value kind
  - AC: top-1 attribute accuracy on grouped CV reported (target >= 85%)
- [ ] **T7** First judge: parsed fact vs timeline -> label, wired into `run.py`
  - AC: CV accuracy > baseline; `check.sh` still green
- [ ] **Checkpoint B**

## Phase 2 — Truth and confidence
- [ ] **T8** Timeline builder (intervals, aliases, date precision, `op`)
  - AC: lookup (subject, attribute, date) returns value or none; unit tests on known changing facts (e.g. Holdan `team_size`)
- [ ] **T9** Consensus truth discovery over unlabelled rows
  - AC: CV accuracy improves on rows whose fact is absent from training truth
- [ ] **T10** Features + isotonic calibration + true/false/unsure thresholds
  - AC: calibration table near-diagonal; unsure rate small; log-loss < baseline
- [ ] **Checkpoint C**

## Phase 3 — Claims
- [ ] **T11** `referee.py` (schema, lexicon names/attributes, claim-forms, value-forms)
  - AC: all `contracts/examples/entry/good` pass, all `bad` fail; doc-table examples agree
- [ ] **T12** Value renderer + `fact` and `change` claims
  - AC: >= 300 validated claims of these types, zero referee failures
- [ ] **T13** `at_event`, `relation`, `compare` claims
  - AC: >= 100 validated claims of each type
- [ ] **T14** Select exactly 1,000 (type mix, dedupe, not equal to any input row, confidence from stability)
  - AC: 1,000/1,000 pass referee; originality check vs `universe.csv` passes
- [ ] **Checkpoint D**

## Phase 4 — Hardening
- [ ] **T17** Harden: synthetic ~20k rows, time/memory, SIGTERM, image < 3 GiB
  - AC: `MINUTES=30 scripts/check.sh` green, run finishes well under 30 min
- [ ] **Checkpoint E**

## Phase 5 — Submission
- [ ] **T18** 29 Oct 09:00: pull `sample/sample.csv`, run `pipeline` on it, hand output to the Lovable frontend owner
- [ ] **T19** Judge README (LLM-use log); PR named after team opened by 10:00; **no pushes after 11:00**

## Open questions
- [ ] Team size / names
- [ ] Team name + fork URL
- [ ] Docker installed locally?
