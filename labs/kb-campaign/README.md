# KB campaign lab

Python lab behind [the knowledge base campaign](../../docs/research/kb-campaign.md) (2026-10-29): one harness that scores
every knowledge-base variant on the practice selection tracks and on every suite world, the code of the seven
variant families and the combination phase, their reports, and every result line. It is not solver code and is not
part of the competition image. The winner to port is `F2/f2var.py:Chain` (core in `F2/f2core.py`).

| Path | What |
|---|---|
| `harness/` | `world.py` (practice and suite worlds, P80 / P10 / suite tracks, point-jitter), `api.py` (variant and plugin API), `metrics.py` (arena points, ECE, macro-F1, matching the suite scorer), `run.py` (grid runner), `leaderboard.py`, `check_leak.py`, `variants/` (always-true, V5, V9, V11, V12mmr, interval and point engines), `vendor_a/` (the suite scorer and truth engine, unchanged); `API.md`, `GATES.md` |
| `F1/` | truth discovery: Accu, AccuCopy, CRH, TruthFinder, Dawid-Skene, LTM, Sums, SLiMFast, the dynamic-world HMM (`td.py`, `f1var.py`), copied-lie stress (`stress.py`), OOF self-check |
| `F2/` | temporal resolution: point resolvers, bracket tables, TeCoRe, segmentation, per-key HMM and Viterbi chains (`f2core.py`, `f2var.py`), brute-force LOPO test (`test_f2.py`), staleness analysis |
| `F3/` | learned fusion (`fusion.py`), calibrators and abstention policies (`calib.py`), paired tests |
| `F4/` | graph propagation, MIL, graph-Laplacian LR, co-training, lexicon features (`f4graph.py`, `f4models.py`, `f4lex.py`) |
| `F5/` | lie fingerprints, unsure cues, source priors (`fp.py`, `rules.py`, `f5v.py`, `onf2.py`), null-controlled forward selection logs |
| `F6/` | stress battery, 407 cells per variant (`stress.py`, `selfcheck.py`), `SUMMARY.md` |
| `F7/` | MLP, DeepSets and GNN on CPU (torch) |
| `P3/` | combinations (`p3.py:Stack`), fresh-split page-cluster bootstrap (`boot.py`), 20k-row timing |
| `R4/` | adversarial review probes |
| `*/REPORT.md` | each worker's report: everything tried, results tables, top configurations, caveats |
| `results/*.jsonl.gz` | every result line (one per variant, params, track): `ts worker variant params track n_scored metrics` plus run time, RSS and the source hash; `*-remote` files ran on a borrowed CPU box |

## Run

The practice tracks need only the repo's `data/`. Suite tracks also need the teammate's evaluation data and the shared
forms written by [labs/evaluation-suite-runs](../evaluation-suite-runs/README.md) (`A/gold_forms.py` for gold forms,
`B/extract.py` for the extractor-B forms).

```sh
uv venv --python 3.12 .venv-kbc
uv pip install --python .venv-kbc/bin/python numpy scipy scikit-learn   # torch only for F7
export KBC_ROOT=$PWD/labs/kb-campaign KBC_PRACTICE_DIR=$PWD/data KBC_RESULTS_DIR=/tmp/kbc-results
export KBC_SUITE_DIR=<evaluation-data dir> KBC_EVALSUITE_DIR=<dir holding forms/gold, forms/B>
PY=".venv-kbc/bin/python -I"
# the winner on the selection tracks (P80 0.8492, P10 0.7673 on Apple silicon, 0.7678 on x86)
$PY $KBC_ROOT/harness/run.py --variant 'F2/f2var.py:Chain={"d0":0.03,"engine":"viterbi","eps_a":0.0005,"mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}' \
    --tracks P80,P10 --jobs 2 --worker ME
# the same on suite tests (Sdev-jt 0.9419, Sdev-jr 0.9148)
$PY $KBC_ROOT/harness/run.py --variant 'F2/f2var.py:Chain={...}' --tracks Sdev-jt,Sdev-jr,Ssealed-jt,Ssealed-jr --jobs 2 --worker ME
$PY $KBC_ROOT/harness/leaderboard.py --tracks Sdev-jt,Sdev-jr
$PY $KBC_ROOT/F6/stress.py run --variant '<module:Class>=[{...}]' --stress copies,xforms --base P80,P10 --jobs 2 --worker ME
```

To read the recorded results, `gunzip -k results/*.jsonl.gz` and point `KBC_RESULTS_DIR` at that directory. Some
lines (F5 paired runs, F6 stress cells) carry extra fields; `leaderboard.py` expects `variant` and `params` keys.

Caches (`cache/`), predictions, remote launch scripts and logs are not in git.

Known issues: `F1/plugins.py` puts `F1/` first on `sys.path`, so `F1/timeit.py` shadows the standard library module
and breaks scikit-learn imports in the same process (`P3/p3.py` imports the real `timeit` first). The harness
`src_hash` covers only the variant's own file, not the modules it imports (F2 bumps `F2_VERSION` by hand).
`leaderboard.py` stops on result lines without `variant` and `params` keys (some F5 paired and F6 stress lines).
