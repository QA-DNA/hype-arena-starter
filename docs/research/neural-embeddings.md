# Neural text layers: what embeddings, NLI and fine-tuning measured on practice

Status: MEASURED on 2026-10-28, evening, on `data/practice.csv` (1,897 rows, 291 pages) with the
shared harness in [`labs/embedding-experiments`](../../labs/embedding-experiments/README.md).
Raw worker reports and JSONL results live there. Nothing here is solver code.

The question (Eduard, 2026-10-28): can a large multi-level neural network over the sentence text
(embeddings, entities and attributes, relations, a three-valued true/false/unsure head) do the
labelling, how accurate would it be, how fast does it run inside the organizers' Docker, and which
models should we use. Training cost was declared irrelevant; only the 30-minute, 2-CPU, 6 GiB,
offline run matters, plus the rule that the system itself may not be an LLM.

## 1. Verdict in six lines

1. **Truth is not in the text.** Fifty embedders, five NLI cross-encoders and two fine-tuned
   encoders all fail to separate false rows from true ones from the sentence alone (AUC 0.55 to
   0.62 against 0.633 for plain TF-IDF), and none adds anything to the KB fact model V9 (paired
   deltas within ±0.005). A sentence does not know whether it lies; only the other pages do.
2. **The neural layer earns its place in extraction, not in judgment.** Mapping a sentence to its
   lexicon attribute goes from 0.873 (TF-IDF) to 0.931 with a 33M-parameter encoder, and from 0
   to 0.87 on attributes never seen in training. That is the entities-and-attributes layer of the
   idea, and it is the one that matters for a universe ten times bigger than practice.
3. **Values and subjects are solved without neural networks.** A typed-value grammar recovers
   every value in practice (recall 1.000, 0.990 before tuning). A page-context subject resolver
   with attribute compatibility reaches 0.913 on all rows. End to end, the full form
   (subject, attribute, value) is recovered exactly for 0.81 to 0.83 of single-fact rows.
4. **Embeddings matter for copies.** Dropping a row's own near-duplicate cluster (cosine ≥ 0.95)
   from its evidence restores the false recall that copied lies destroy (0.120 back to 0.448,
   clean 0.465). Exact text matching does the same on verbatim copies and fails on reworded ones.
5. **Small beats big.** MiniLM-L12 (33M, 127 MB) matches or beats every 300M to 600M encoder and
   both LLM-derived embedders; static models (potion-8M, 31 MB, 30,000 sentences per second) are
   within 0.02 to 0.03 of it everywhere. Nothing larger than 70M parameters is worth its CPU.
6. **It all fits in minutes, not 30.** The whole neural part costs under three minutes on two x86
   cores for 20,000 rows; a 20,000-pair NLI tie-breaker adds two to four minutes if we use it.

## 2. Protocol

- Data: `practice.csv`, 1,581 true, 277 false, 39 unsure; 2,402 facts; 1,467 single-fact rows.
  Pages are runs of consecutive ids sharing a date (291 pages, median 7 rows).
- Folds: `GroupKFold(5)` by page for every number. "Attribute folds" hold out whole attribute
  strings (leave-attribute-out) to simulate attributes that exist in the run's lexicon but not in
  practice. Classifier numbers use the gold subject unless stated.
- References to beat: TF-IDF (char 2-5 + word 1-2) with a linear model gives attribute accuracy
  0.873 restricted to the subject's lexicon attributes (0.961 with five or more training examples,
  0.883 with one to four, 0.000 unseen), false-vs-rest AUC 0.633, key retrieval recall@10 0.666.
  Always answering `true` scores 0.687 on the arena (+1 right, -1 wrong, 0 unsure).
- Models: 15 small encoders (w1), 13 large or new encoders (w2), 8 static and 3 LLM-derived
  embedders plus LSA and random projection (w3), 12 NLI or zero-shot cross-encoders (w4),
  7 new NLI models and 2 GLiClass classifiers (w10), 10 encoders from the HF/MTEB scan (w9),
  fine-tuning of bi- and cross-encoders (w5), fusion with V9 (w6), the typed-value grammar (w7),
  subject resolution (w11), x86 Docker timing (w12).
- Hardware for accuracy runs: Apple M5 Pro capped at 2 threads, fp32; speed there is noisy (load
  3 to 13). Quote x86 numbers from section 7.

## 3. Truth from text: measured zero

| signal | best model | AUC (false) | arena |
|---|---|---|---|
| TF-IDF + LR, text only | char+word n-grams | 0.633 | below always-true |
| masked (digits and names removed) | same | 0.615 | |
| 50 frozen embedders + LR probe | jina-v2-small 0.613, bekko-a8m 0.612 | 0.55 to 0.615 | 0.09 to 0.29 |
| fine-tuned bge-small, 3-class head | | 0.547 | 0.608 |
| fine-tuned pair cross-encoder (anchor, row) | ms-marco MiniLM-L6 | 0.593 | |
| untrained cosine(anchor, row) | bge-small | 0.600 | |
| NLI contradiction vs nearest anchor | nli-deberta-v3-xsmall | 0.850 | |
| gold oracle "nearest anchor value differs" | none | 0.850 | |

The only textual tell is roundness: a multiple of five appears in 46.9% of false rows and 33.2% of
true ones. Hype words (only, still, everyone, "!") do not exist in the data. The NLI row is the
important one: raw NLI against the nearest anchor reaches exactly the gold oracle that the typed KB
already computes, and inside the subset where the value differs (wrong value versus legitimately
updated value) it drops to 0.56 to 0.66. The limit is temporal, not linguistic.

Fusion with V9 (w6, paired deltas over 5 folds / 10 seeds / 50 seeds): adding an out-of-fold
text-false probability from bge-small changes R80 accuracy by -0.001 ± 0.003 and R10 by
+0.002 ± 0.010; TF-IDF the same; copy-count features the same; an MLP head is worse everywhere
(R10 false recall -0.347). Abstention never helps: with calibrated probabilities the labelled-row
threshold was 0.5 in all 2,160 runs, so the system should always answer and keep `unsure` for rows
with no evidence at all.

## 4. Copies: the one place embeddings change the truth score

V9 and V11 collapse under copied lies (synthetic `hlie` scenario: false recall 0.465 to 0.120 and
0.204). Dedup variants (w6):

| variant | hlie false recall | hpara (reworded copies) | clean R80 acc delta |
|---|---|---|---|
| V9 undefended | 0.120 | 0.120 | |
| one vote per cluster (cos ≥ 0.95) | 0.201 | 0.199 | -0.003 |
| same key and value on the same day | 0.130 | 0.130 | -0.002 |
| **drop the row's own cluster (cos ≥ 0.95)** | **0.448** | **0.430** | -0.005 |
| drop own cluster, exact text match | 0.439 | 0.121 | -0.003 |

Arena score under copied lies: V9 0.674 and V11 0.636 fall below always-true (0.684); V9 with own-
cluster dedup stays at 0.692. The threshold is sharp: at 0.90 the cluster merges rows that share a
key but not a value ("€18 per TB" vs "€21 per TB" sit at cosine 0.965) and costs 0.19 false recall.

## 5. Attribute from text: the real neural win

Single-fact rows, gold subject, restricted to the subject's lexicon attributes.

| method | all | ≥5 examples | 1 to 4 | unseen (76 rows) | leave-attribute-out |
|---|---|---|---|---|---|
| TF-IDF + LinearSVC (reference) | 0.873 | 0.961 | 0.883 | 0.000 | 0.000 |
| attribute-name word overlap, no training | | | | | 0.757 |
| MiniLM-L12 probe, C=1000 | 0.892 | | | 0.000 | 0.000 |
| MiniLM-L12 zero-shot vs "subject attribute words" | 0.843 | | | 0.843 | 0.843 |
| **MiniLM-L12 hybrid probe + zero-shot** | **0.931** | 0.97 | | 0.605 (1:1) / 0.908 gated | 0.864 gated |
| MiniLM-L6 hybrid | 0.928 | | | | 0.862 gated |
| mxbai-embed-xsmall hybrid | 0.928 | | | | 0.858 gated |
| static-similarity-mrl (no transformer) hybrid | 0.913 | | | 0.658 | 0.806 zero-shot |
| potion-base-8M (static, 31 MB) hybrid | 0.902 | | | 0.605 | 0.835 zero-shot |
| bekko-static hybrid | 0.904 | | | 0.684 | 0.827 zero-shot |
| UltraBERT-Embed-150M hybrid | 0.926 | 0.979 | 0.916 | | 0.859 zero-shot |
| arctic-embed-l-v2.0 (568M) hybrid | 0.938 | | | 0.618 | 0.885 zero-shot, no prefix |
| stella-400M hybrid | 0.933 | 0.990 | | | 0.868 zero-shot |
| fine-tuned MiniLM-L6 bi-encoder (w5) | 0.902 | 0.912 | 0.890 | 0.921 | **0.873** |
| fine-tuned bge-small + attribute-word positives | | | | | 0.883 |
| fine-tuned cross-encoder (w5) | 0.909 | 0.929 | 0.887 | 0.934 | 0.868 |
| NLI zero-shot (ModernBERT-nli, best template) | 0.792 | | | | 0.792 |
| GLiClass modern-base, one pass | 0.744 | | | | 0.744 |

What the numbers say:

- The probe alone never beats TF-IDF on rare attributes; the gain comes from fusing it with the
  zero-shot cosine to the attribute description ("Hooly Cloud reliability lead"). At the harness
  default C=10 the probe under-fits unit-norm embeddings; C in the hundreds fixes it.
- On a truly new attribute the 1:1 fusion hurts (0.44 to 0.62) because the probe pulls toward
  attributes it has seen. Giving unseen candidates the best seen probe score ("gated") restores
  0.86 to 0.88, which also lifts the 76 unseen page-fold rows to about 0.91.
- Fine-tuning a bi-encoder on (text, "subject attribute words") pairs is the cleanest way to serve
  unseen attributes: 0.873 (MiniLM-L6) and 0.883 (bge-small with attribute-word positives) under
  leave-attribute-out, in about a minute of CPU training per fold set, 92 MB on disk, 1,600
  sentences per second. Cross-encoders gain nothing on unseen labels once tuned and cost 9 to 17
  times more per row. Hard negatives must come only from attributes that also have positives.
- Larger encoders buy 0.01 to 0.04 on zero-shot at 20 times the CPU. Static models lose 0.02 to
  0.03 and cost nothing. The best attribute system is a hybrid: the linear classifier for attributes
  with training rows, the tuned description matcher for the rest.
- NLI and GLiClass zero-shot attribute mapping is not competitive (0.70 to 0.79).

## 6. Forms end to end: values, subjects, multi-fact rows

Typed-value grammar (w7, `values.py`, pure regex and small tables, portable to Rust):

| kind | n | recall | candidate precision |
|---|---|---|---|
| quantity | 1,028 | 1.000 (unit exact 1.000) | 0.964 |
| money | 268 | 1.000 | 1.000 |
| duration | 229 | 1.000 | 0.987 |
| percent | 201 | 1.000 | 1.000 |
| date | 165 | 1.000 | 0.971 |
| version | 128 | 1.000 | 1.000 |
| name | 209 | 1.000 (0.909 unflagged) | 0.090 |
| boolean | 174 | 1.000 (0.856 unflagged) | 0.087 |

Blind first pass was 0.990; 25 misses were fixed with general rules (hyphenated names, "A 1.6 GB"
read as a version, years inside event names, "per terabyte each month"). Gold uses `inch` where the
contract table says `in`. With the right attribute, the right value is picked 0.997 of the time.

Single-fact rows, full form exact (subject, attribute, value):

| subject source | subject | attribute | exact form |
|---|---|---|---|
| lexicon matcher only | 0.622 | 0.550 | 0.548 |
| carry the previous subject on the page | 0.806 | 0.710 | 0.704 |
| page candidates chosen with attribute compatibility + collective fallback (w11, X4) | 0.909 | 0.827 | 0.807 |
| same, classifier trained on all rows | 0.922 | 0.868 | 0.834 |
| gold subject given | 1.000 | 0.873 | 0.870 |

Only 0.657 of rows name all their subjects; 34% are headlines ("Cycle: 4 weeks"), pronouns or label
fragments. The gold subject is named somewhere on the same page for 0.910 of rows, which is the
ceiling for any page-local method; 3.7% are never named. Pronoun typing adds nothing (the pronoun
usually refers to a person who is not the fact's subject). Remaining errors are siblings (Pixel 9
vs 10, Cloud vs Cloud Next), partial aliases ("Lisbon", "the hall") and multi-subject rows.
Multi-fact rows (430) pair values to attributes only by count: the numeric candidate count equals
the fact count in 0.985 of all-numeric rows, but the attribute classifier is single-label, so
assigning each value its attribute is open work.

## 7. Conflict detection between two sentences

If the grammar cannot compare two values (names, booleans, odd phrasings), a small NLI cross-encoder
can. Same-key pairs from different pages, target "values differ" (2,649 pairs):

| model | params | AUC | per kind (qty / money / pct / date / name / bool / dur / ver) | pairs/s Mac 2 threads |
|---|---|---|---|---|
| finecat-nli-v2-m (LLM-distilled) | 150M | 0.971 (0.979 both directions) | .985 .950 .984 .942 .952 .958 .975 .941 | 61 |
| finecat-nli-s | 68M | 0.955 | .971 .954 .968 .937 .940 .939 .953 .910 | 134 |
| finecat-nli-xs | 32M | 0.948 | .965 .967 .958 .929 .927 .941 .917 .920 | 368 |
| finecat-nli-xxs | 17M | 0.926 | .950 .931 .917 .933 .889 .926 .916 .825 | 970 |
| nli-deberta-v3-xsmall | 71M | 0.949 | .956 .917 .990 .918 .933 .939 .940 .916 | 155 to 202 |
| DeBERTa-v3-base mnli-fever-anli | 184M | 0.958 | | 64 |
| albert-xlarge-vitaminc | 59M | 0.947 | best on money .986 | 5 |

Binary zero-shot models (MoritzLaurer *-zeroshot-v2.0) are useless here (0.77 to 0.88) because
"not entailment" also fires on neutral pairs. Use the contradiction probability, never 1 minus
entailment. About 49 "differ" pairs differ only by operator or date granularity, so the ceiling is
below 1. Key retrieval by embedding is marginal over TF-IDF (recall@10 0.684 vs 0.666; LSA-300
0.702), so evidence lookup stays keyed by (subject, attribute), not by similarity.

## 8. Cost: speed, storage, the organizers' box

Mac numbers vary 3.5x with machine load; the x86 numbers are the ones to plan with.

| model | role | params | disk (fp32) | Mac, 2 threads | x86 measured or estimated |
|---|---|---|---|---|---|
| potion-base-8M (static) | attribute zero-shot, copies | 7.6M | 31 MB | 56,000 sent/s | under 2 s per 20k |
| static-similarity-mrl-multilingual | same | 108M (tables) | 436 MB | 29,000 sent/s | under 2 s |
| all-MiniLM-L6-v2 | attribute matcher, copies | 22.7M | 87 to 92 MB | 530 to 1,660 sent/s | 40 to 80 s per 20k |
| all-MiniLM-L12-v2 | attribute matcher | 33M | 127 MB | 270 to 520 sent/s | 80 to 150 s |
| mxbai-embed-xsmall-v1 | alternative | 24M | 46 MB (fp16 on Hub; cast to fp32) | 570 to 690 sent/s | 60 to 80 s |
| finecat-nli-xs | conflict tie-breaker | 32M | 122 MB | 368 pairs/s | 110 to 220 s per 20k pairs |
| nli-deberta-v3-xsmall | conflict tie-breaker | 71M | 283 MB | 155 to 202 pairs/s | 91 pairs/s measured on a Ryzen 3700X: 220 s per 20k pairs |
| ms-marco-MiniLM-L-6-v2 cross-encoder | fine-tune base | 22.7M | 91 MB | 700 to 960 pairs/s | 268 pairs/s measured: 75 s per 20k pairs |
| bge-large / e5-large / mxbai-large | not recommended | 335M | 670 to 1,341 MB | 24 to 36 sent/s | 19 to 28 min per 20k |
| arctic-l-v2 / stella-400M / bge-m3 | not recommended | 435 to 568M | 1.8 to 2.3 GB | 24 to 27 sent/s | 27 min per 20k |
| Qwen3-Embedding-0.6B (LLM-derived) | ceiling only | 596M | 1.2 GB | 9 to 11 sent/s | 60 to 75 min per 20k |

Engineering facts that bit tonight: transformers 5.x breaks remote-code models (gte-base-en-v1.5,
jina-v2/v3, nomic-v1.5, cde) and needs 4.46 to 4.57 for them; sentence-transformers 6 loads fp16 or
bf16 checkpoints as such on CPU (6 to 8x slower) unless cast to fp32; ALBERT and other
SentencePiece pair models need `return_token_type_ids=True` under transformers 5; int8 ONNX gives
no speedup on an AVX2-only CPU and flips 5 to 31% of NLI labels, so ship fp32; batch 32 beats 128
and length sorting is worth 25 to 45%; ONNX Runtime sizes its thread pool from host cores, so set
`intra_op_num_threads=2` explicitly; set `OMP_NUM_THREADS`, `MKL_NUM_THREADS` and
`TOKENIZERS_PARALLELISM=false` before importing torch.

x86 Docker timing with the contract's flags (w12): see the addendum at the end of this document.

## 9. The rule: "the system itself may not be an LLM"

No definition exists. The organizer's only words (starter issue #2) are "you cannot call anything
external in your final solution"; the question whether a bundled fine-tuned MiniLM counts is still
unanswered. Risk tiers used tonight:

- SAFE: TF-IDF, LSA, static embeddings (potion, static-similarity-mrl, bekko-static, GloVe), the
  grammar, the resolver, V9. Everything in the recommended pipeline has a SAFE fallback that costs
  at most 0.03 on attribute accuracy.
- GREY: BERT-family encoders shipped in the image (MiniLM, bge-small, mxbai-xsmall, DeBERTa NLI).
  Encoder-only, no generation, 17M to 71M parameters, three to four orders of magnitude below any
  published LLM threshold. Pretrained world knowledge is not used as evidence; they only compare
  in-universe text.
- RISKY: decoder-LLM-derived embedders (Qwen3-Embedding, EmbeddingGemma, F2LLM) and NLI models
  distilled from a 27B teacher (finecat-nli-v2-m, ultra-m). Measured only as ceilings; they gave no
  gain, so nothing is lost by excluding them.

## 10. What we use

Each layer of the original idea, with the component that measured best and its SAFE fallback:

1. **Mentions and subjects**: lexicon alias matcher plus the page-context resolver with attribute
   compatibility and the collective page fallback (w11, 0.913). No neural network.
2. **Attribute**: TF-IDF linear classifier for attributes with training rows, fused with a
   description matcher for the rest, gated so unseen candidates are not suppressed. Matcher:
   all-MiniLM-L12-v2 or the fine-tuned all-MiniLM-L6-v2 (0.93 overall, 0.87 unseen). Fallback:
   potion-base-8M (0.90 overall, 0.84 unseen).
3. **Value**: the typed grammar (w7), ported to Rust or shipped as is. Recall 1.000.
4. **Knowledge base and truth**: V9 per-fact bracket features with logistic regression and isotonic
   calibration, unchanged, plus own-cluster dedup at cosine 0.95 (MiniLM or static embedding;
   exact text as the fallback). Always answer; `unsure` only with no evidence. Confidence = the
   calibrated max(p, 1-p) clipped to [0.5, 1].
5. **Conflict tie-breaker** (optional, bounded): finecat-nli-xs or nli-deberta-v3-xsmall on the
   pairs whose values the grammar could not compare, capped at 20,000 pairs. Skip it if the
   organizer rules against encoders; the arena score does not depend on it.
6. **Claims**: unchanged from [the claim generation research](claim-generation.md), fed by the same KB.

Run budget on two x86 cores for 20,000 rows: subject and value layers in seconds, attribute
matcher 40 to 150 s, dedup embeddings 40 to 80 s (or 2 s static), V9 in seconds, optional NLI
220 s. Image growth: 90 to 130 MB for one MiniLM plus 120 to 280 MB for an NLI model, all fp32.

What not to build: a truth head on text, a fine-tuned truth classifier, an NLI judge, GNN or MLP
fusion over V9, abstention bands, encoders above 70M parameters, LLM-derived embedders, int8 on an
unknown CPU, embedding-based evidence retrieval.

## 11. Open items

- End-to-end accuracy with extracted forms is still unmeasured: every V-series number assumes the
  gold `form`; tonight's layers recover the exact form for 0.81 to 0.83 of single-fact rows, so the
  KB at run time will be noisier than in the experiments. Measure V9 on w7+w11 forms next.
- Multi-fact rows (23% of rows): value-to-attribute pairing inside a sentence.
- Sibling subjects and partial aliases ("Lisbon", "the hall").
- The run's id format and page order are unknown until `sample/sample.csv` lands at 09:00; the
  resolver assumes consecutive ids keep page order.
- The organizer's ruling on bundled encoders (issue #2). Ask directly.
- A fine-tuned matcher must be trained on all practice rows before the freeze and its provenance
  recorded (practice forms only; no LLM-generated text was used tonight).
