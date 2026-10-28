# Embedding experiments (2026-10-28)

Raw record of one evening's benchmark of text embedders and neighbouring techniques on `data/practice.csv`
(1,897 rows, 291 pages, 1,467 single-fact rows): sentence embedders, NLI cross-encoders, fine-tuning, fusion
with the V9 knowledge-base model, a typed-value grammar, subject resolution and CPU timing (Apple M5 Pro and an
x86 Docker container). Twelve workers ran against one shared harness; each wrote its own results JSONL.
Curated findings and recommendations: `docs/research/neural-embeddings.md`.
This lab is evidence and a rerun kit. The Rust workspace does not build it and the submission does not ship it.

## Layout

| Path | Contents |
|---|---|
| `common/` | `harness.py` (data loading, folds, probes, kNN, retrieval, NLI and truth metrics, speed) and its `README.md` (API and semantics) |
| `results/` | `<worker>.jsonl`, one line per measured run (schema below). No `w8` file (landscape only); `w12.jsonl` appears once `w12/log_results.py` has run |
| `w1/` | 15 small sentence embedders (MiniLM, mpnet, bge, gte, e5, arctic, mxbai-xsmall, jina-v2-small): attribute probe, kNN, zero-shot, hybrid, key retrieval, truth probes, speed |
| `w2/` | 13 larger embedders (bge-large and m3, e5-large, gte-large, arctic-l-v2, stella-400m, mxbai-large, nomic-v1.5, ModernBERT-based, jina-v3, granite) |
| `w3/` | static and non-neural embedders (potion, static-similarity, GloVe, LSA, random projection), multilingual encoders, LLM embedders (Qwen3-Embedding-0.6B, nomic-v2-moe) |
| `w4/` | NLI cross-encoders on `nli_anchor`, `nli_conflict` and `nli_attr` (cross-encoder/nli-*, MoritzLaurer, tasksource, bart-large-mnli) |
| `w5/` | fine-tuning: bi-encoder (in-batch negatives), attribute cross-encoder, text-only truth classifier, anchor-pair truth cross-encoder |
| `w6/` | fusion of a neural text layer with the V9/V11 per-fact model: near-duplicate features, dedup, stress scenarios (see `w6/NOTE.md`) |
| `w7/` | deterministic typed-value extractor (`values.py`, regex plus small tables) and its measurements |
| `w8/` | model landscape from the HF Hub and MTEB leaderboard: `landscape-brief.md` and the raw scrapes behind it |
| `w9/` | second embedder wave (mdbr-leaf-mt, GIST-small, mini-gte, bekko, UltraBERT-Embed, UAE-Large, jina-v5-nano, cde-small-v2, DenseOn) |
| `w10/` | second NLI wave (finecat-nli, ModernBERT-nli, albert-vitaminc), GLiClass, hypothesis-template variants, speed rechecks |
| `w11/` | page-context subject resolution (`subjects.py`) and its measurements |
| `w12/` | x86 Docker timing under competition-style limits: `Dockerfile`, `bench.py`, raw `out1/` and `out2/` `bench.json` (1 and 2 CPUs) |

Each worker directory holds its scripts, a driver (`run_all.*`, `driver.sh`, `queue*.sh`, `chain*.sh`,
`scripts/sweep.sh`) and table builders. Read the driver first: it encodes the order and the thread budget.
Run logs stay out of git (repo rule: run outputs are not committed); they remain under `/tmp/veridyct-emb/<worker>/logs` on the Mac that ran them.
Not committed: virtualenvs, HF caches, weights, embedding arrays (`emb/`, `*.npy`, `scores/`), model cards (`cards/`),
downloaded papers and HTML, scratch `*.jsonl`, all `*.log` files, and two local copies of third-party model
code: `w3/nomic_code` (unreferenced, identical to the upstream snapshot) and `w9/cde_local` (used only by the failed
`bench.py --shim` route).

## Rerun

Scripts were executed from `/tmp/veridyct-emb/<worker>/` and hard-code that path, plus `/tmp/veridyct-bench` for the
interpreter and the HF cache, so copy the lab to `/tmp/veridyct-emb` or edit the paths. `harness.py` reads
`practice.csv` and `lexicon.json` from its own directory. They were byte-identical copies of `data/` (sha256 prefixes
`52743bef` and `d0fd5e9b`) and are not duplicated here.

    cp -R labs/embedding-experiments /tmp/veridyct-emb
    cp data/practice.csv data/lexicon.json /tmp/veridyct-emb/common/
    mkdir -p /tmp/veridyct-bench && cd /tmp/veridyct-bench          # shared venv, where the scripts expect it
    uv venv --python 3.12 .venv && uv pip install torch sentence-transformers transformers scikit-learn scipy model2vec einops sentencepiece datasets accelerate
    export HF_HOME=/tmp/veridyct-bench/hf                           # harness default; w9 and w10 set their own under their directory
    .venv/bin/python -I /tmp/veridyct-emb/common/harness.py         # self-test, about 5 s, prints the TF-IDF reference numbers

w1, w2, w9 and w10 used private venvs. w9 `.venv-cde` pins transformers 4.48.3 and sentence-transformers 3.4.1 because
the remote code of cde-small-v2 fails on the shared venv's 5.21 and 6.2 (its only result is a partial speed line); w10
adds `gliclass`. w12 runs on an x86 host: build the image with
`Dockerfile`, `bench.py`, `fetch_models.py` and `data/practice.csv` in the context, run it with the flags listed in
`log_results.py`, then `python log_results.py <image_MB> <unpacked_MB>` writes `results/w12.jsonl`.

## Results JSONL

One object per line, written by `ResultWriter.add` in `common/harness.py`:

    {"ts": ISO-UTC, "worker", "model", "task", "variant", "n", "notes", "metrics": {...}, ...extra}

NaN/inf become null and numpy becomes plain python. `metrics` is the dict the harness returned, unchanged; extra
facts (dims, secs, C, k) sit in the extra fields or in `notes`. Task names: `attr_probe` `attr_knn` `attr_zeroshot`
`attr_hybrid` `attr_unseen` `key_retrieval` `truth_false` `truth_three` `nli_anchor` `nli_conflict` `nli_attr` `speed`,
plus the prefixes `finetune_*` `fusion_*` `values_*`.

## Fold protocol

- A page is a run of consecutive ids (`p-N`) that share a date: 291 pages (`pages()` in the harness).
- `GroupKFold(5)` by page (`page_folds`): attribute tasks on the 1,467 single-fact rows, truth tasks on all 1,897 rows.
  The two row lists give different splits; fusing stages derives the single-fact folds from the all-row folds.
- `attr_unseen` uses leave-attribute-out folds (`attribute_folds`): every test attribute has zero training rows.
- Attribute predictions are restricted to the gold subject's lexicon attributes. Fold noise is about 0.01.
  Reference: TF-IDF + LinearSVC attribute accuracy 0.873, TF-IDF + LR false-vs-rest AUC 0.633.

## Speed numbers

Timings in `results/` (task `speed`, field `est_sec_20k_x86`) were taken on a shared Apple M5 Pro at load 3-13, with 2
threads and other workers running: indicative only. `est_sec_20k_x86` is a conversion (Mac time times 2, the midpoint
of an assumed 1.5x-3x slowdown), not a measurement. The x86 numbers to quote are the `w12` Docker runs (AMD Ryzen 7
3700X server, `--cpus 1` and `--cpus 2`, 6 GB, no network). The other CPU-count run and an unrelated Supabase stack
ran on the same host at the same time (noted in `log_results.py`), so these are not clean single-tenant timings either.
