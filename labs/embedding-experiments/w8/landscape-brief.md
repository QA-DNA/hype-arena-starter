# Embedder and NLI scouting brief, 2026-10-28 (free tools only, nothing written in the repo)

**Method.** MTEB(eng, v2) figures are Mean(Task) over 41 tasks, pulled today from the leaderboard's public JSON API [1] (349 rows). Backbones come from HF configs [2]. E = encoder, D = decoder-LLM-derived. zs = the leaderboard's zero-shot share (low zs means the model trained on many benchmark tasks, so its mean is inflated). Several listed models (all-mpnet-base-v2, MiniLM-L12, jina-v3, bge-m3, gte-base-en-v1.5, modernbert-embed-base) have incomplete rows, so I also computed **STS+PC**: the mean of the 9 STS/PairClassification tasks that all 49 compared models share. It fits your sentence-level tasks better than the 41-task mean.

## 1. Leaderboard snapshot (open weights, full 41 tasks)

| Tier | id | params | dim | ctx | Mean | type, licence |
|---|---|---|---|---|---|---|
| under 100M | prdev/mini-gte | 66M | 768 | 512 | 65.06 | E DistilBERT, Apache-2.0 |
| | avsolatorio/GIST-small-Embedding-v0 | 33M | 384 | 512 | 64.76 | E, MIT |
| | codefuse-ai/F2LLM-v2-80M | 80M | 320 | 40,960 | 64.55 | D pruned Qwen3, zs 43, Apache-2.0 |
| | bge-small-en-v1.5 (listed) | 33M | 384 | 512 | 64.30 | E, MIT |
| | MongoDB/mdbr-leaf-mt | 22.6M | 1024 | 512 | 63.97 | E MiniLM-L6, Apache-2.0 |
| | refs: all-MiniLM-L6-v2 59.03; potion-base-32M 54.63 | | | | | |
| 100-400M | jinaai/jina-embeddings-v5-text-nano | 212M | 768 | 8,192 | 71.11 | E EuroBERT-210m, custom code, CC-BY-NC-4.0 |
| | embeddinggemma-300m (listed) | 308M | 768 | 2,048 | 69.67 | D-derived (gemma3_text), Gemma terms |
| | Tarka-Embedding-350M-V1 / F2LLM-v2-330M | 354M / 334M | 1024 / 896 | 128k / 40,960 | 69.29 / 68.86 | D-derived (LFM2) / D Qwen3, zs 43 |
| | microsoft/harrier-oss-v1-270m | 268M | 640 | 32,768 | 67.72 | D Gemma3, MIT |
| | google/embeddinggemma-2 | 271M text (740M total) | 768 | 8,192 | 67.53 | D-derived, Apache-2.0 per card |
| | dmis-lab/UltraBERT-Embed-150M | 151M | 768 | 32,768 | 67.24 | E, Apache-2.0 |
| | WhereIsAI/UAE-Large-V1 | 335M | 1024 | 512 | 66.40 | E BERT-large, MIT |
| 400M-1B | infgrad/Jasper-Token-Compression-600M | 607M | 2048 | 32,768 | 74.75 | D Qwen3 adapter, custom code, zs 48, MIT |
| | IEITYuan/Yuan-embedding-2.0-en | 596M | 1024 | 2,048 | 71.74 | D Qwen3, Apache-2.0 |
| | KaLM-embedding-multilingual-mini-instruct-v2.5 | 494M | 896 | 512 | 71.29 | D Qwen2, zs 58 |
| | microsoft/harrier-oss-v1-0.6b | 596M | 1024 | 32,768 | 70.64 | D Qwen3, MIT |
| | Qwen3-Embedding-0.6B (listed) | 596M | 1024 | 32,768 | 70.47 | D, Apache-2.0 |
| | stella_en_400M_v5 (listed) | 435M | 4096 | 8,192 | 69.39 | E, custom code, zs 51, MIT |

Above 70, jina-v5-text-nano is the only encoder; the rest are Qwen/Gemma derivatives, the class you flagged as legal risk. I excluded them from additions. gte-modernbert-base scores 66.26 (per the UltraBERT card [3]; its leaderboard row is incomplete). No NeoBERT-, Ettin- or other EuroBERT-based general English embedder exists on HF besides jina-v5-nano, and Sentence-T5/GTR sit at rank 232+ with no successor.

## (a) Recommended additions (encoder or static only, ranked)

| # | id | params | dim | type | licence | Mean | STS+PC | why |
|---|---|---|---|---|---|---|---|---|
| 1 | MongoDB/mdbr-leaf-mt [4] | 22.6M | 1024 | E | Apache-2.0 | 63.97 | 86.0 | MiniLM-L6 cost, +4.9 mean and +3.7 STS+PC over all-MiniLM-L6-v2 (59.03 / 82.3) |
| 2 | dmis-lab/UltraBERT-Embed-150M [3] | 151M | 768 | E | Apache-2.0 | 67.24 | 85.7 | card claims SOTA under 200M; 18 days old, 2.3k downloads, no replication; needs transformers 5.20+ and sentence-transformers 6+, else trust_remote_code |
| 3 | jinaai/jina-embeddings-v5-text-nano [5] | 212M | 768 | E | CC-BY-NC-4.0 | 71.11 | 90.9 | best STS+PC of all 49; run as a ceiling, then settle the NC licence and custom code |
| 4 | WhereIsAI/UAE-Large-V1 | 335M | 1024 | E | MIT | 66.40 | 87.5 | no remote code, ties mxbai-large; heaviest CPU cost here |
| 5 | prdev/mini-gte | 66M | 768 | E | Apache-2.0 | 65.06 | 84.7 | 6 layers, above bge-small and gte-small on mean |
| 6 | avsolatorio/GIST-small-Embedding-v0 | 33M | 384 | E | MIT | 64.76 | 85.6 | safe small BERT |
| 7 | jxm/cde-small-v2 [6] | 306M | 768 | E ModernBERT-base | MIT | partial only | 86.3 | conditions on a corpus sample, suits a closed company corpus; custom code, two-stage |
| 8 | hotchpotch/bekko-static-embedding-v1 [7] | 205M static | 1024 | static | MIT | 55.48 (40/41) | 78.7 | newest static model, see (e) |
| 9 | hotchpotch/bekko-embedding-v1-a8m [7] | 106M (7.7M active) | 384 | E ModernBERT arch | MIT | 60.80 | 79.9 | very fast 4-layer, below MiniLM-L12 on STS |
| 10 | lightonai/DenseOn | 149M | 768 | E ModernBERT | Apache-2.0 | retrieval-only | n/a | only for the same-key retrieval step |

STS+PC of listed models for calibration: Qwen3-0.6B 89.3, jina-v3 88.5, mxbai-large 87.5, stella 87.3, EmbeddingGemma 87.0, bge-large 86.1, bge-small 84.8, gte-modernbert 84.0, MiniLM-L6 82.3, arctic-s 80.7, granite-small-r2 79.3, potion-32M 77.7, static-retrieval 75.5. Retrieval-tuned arctic and granite are weak on sentence similarity. Checked, not worth adding: arctic-embed-m-v2.0 (62.57), granite-embedding-97m/311m-multilingual-r2 (ModernBERT, 2026-04; STS+PC 79.5 / 80.8), jina-v5-text-small.

## (b) NLI and zero-shot shortlist

| id | params | licence | MNLI | ANLI r1/r2/r3 | notes |
|---|---|---|---|---|---|
| dleemiller/finecat-nli-v2-m [8] | 150M Ettin (ModernBERT arch) | Apache-2.0 | .895 mm | .704/.520/.498 | no custom code; own 45-set avg .797 vs .679 tasksource-base, .624 Moritz-base, .567 cross-encoder-base |
| dleemiller/finecat-nli-ultra-m [8] | 151M UltraBERT | Apache-2.0 | .888 mm | .736/.569/.524 | VitaminC .862 (training mix may include it, unconfirmed); custom code |
| dleemiller/finecat-nli-s (xs 32M, xxs 17M) [8] | 68M | not declared | .873 | .640/.466/.462 | 2.3k samples/s on the author's GPU vs 1.5k for v2-m (separate cards); the CPU-budget pick |
| tasksource/ModernBERT-base-nli / large [9] | 149M / 395M | Apache-2.0 | .87 / .89 | .66/.49/.44 / .72/.54/.55 | EQUATE .63 / .65, FEVER-NLI .78 (self-reported) |
| MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli [10] (listed) | 184M | MIT | .903 | anli-all .579, r3 .495 | FEVER-NLI .777 |
| cross-encoder/nli-deberta-v3-xsmall / small / base (listed) [11] | 71M / 142M / 184M | Apache-2.0 | mm .878 / .876 / .900 | base .434/.350/.341 | xsmall matches small; ANLI is weak |

Notes: all finecat numbers are author-run; ultra/v2 were distilled from a 27B LLM teacher (the deployed model is an encoder, but record that provenance per the repo rules). MoritzLaurer ModernBERT-base/large-zeroshot-v2.0 (Dec 2024) are binary entail/not-entail, so they cannot give a 3-class probe; the card says they trail DeBERTa-v3 slightly and run much faster [10]. Fact-verification: tals/albert-xlarge-vitaminc-mnli (59M params but ALBERT-xlarge compute, no licence, 2021 paper) and albert-base-vitaminc-mnli (11.7M, 119 downloads) [12]; VitaminC training gave +10% adversarial fact verification and +6% adversarial NLI in the paper. Yuu-Xie/fever-nli-modernbert-large (395M, Apache-2.0, 2026-04) reports FEVER-NLI accuracy .768, no better than the 184M Moritz model (.777).

## (c) Numeric awareness

- **Deng et al., "Revealing the Numeracy Gap" (EACL 2026 Findings) [13]:** 13 embedders on EmbedNum-1K (pick the answer that differs only in its number). Mean accuracy 0.54 against 0.50 chance; LLM-based 0.56 vs encoder-based 0.51; MiniLM-L6 sits at about 50 on every format. Decimals, 4-digit integers and comma-separated numbers are worst; accuracy falls with significant figures; models favour greater-than over less-than.
- **EQUATE [14]:** nine NLI models averaged no gain over a majority baseline on quantitative NLI; a symbolic quantity module gained +24.2% on numeric tests and lost 8.1% on verbal ones. The tasksource EQUATE scores above have no stated baseline.
- **Wallace et al. 2019 [15]:** magnitude is recoverable from token embeddings up to about 1,000; character-level methods beat subword ones (BERT). **NumGLUE [16]:** models trail humans by 46.4%.
- **Negation and antonyms [17]:** NLI-tuned models beat general sentence embedders (SemAntoNeg); Sentence Smith finds antonym swaps and polarity negation fool embedders.
- Inference, not a source: use embeddings only to find the same (subject, attribute) key; parse numbers, units and dates deterministically; use NLI as tie-breaker for text-valued conflicts.

## (d) Few-shot and unseen labels

- **SetFit [18], Table 2 (MPNet, mean of 5 datasets):** 8 shots 62.3 (plain fine-tune 43.0); 64 shots 75.3 (69.7); full-data fine-tune 84.8. Emotion (6 classes): 48.8, 76.2, 92.6 full. No 10-30 shot point is published; treat that range as interpolation. The edge over fine-tuning shrinks from +19.3 to +5.6.
- **Frozen embedder plus logistic regression [19]:** Banking77 (77 classes, full train set) bge-large 94.25%, MiniLM-L6 93.28% vs fine-tuned ModernBERT 93.99%. Single-author claim.
- **Unseen labels:** Yin et al. 2019 define label-fully-unseen evaluation with an entailment formulation [20]. EFL [21] turns classification into entailment with label descriptions: 8 examples, +12% over prior few-shot SOTA on 18 tasks. BLINK [22] retrieves with a bi-encoder and reranks with a cross-encoder for entities known only by descriptions (+6 points absolute). GLiClass [23] (Apache-2.0: knowledgator/gliclass-edge-v3.0 33M, gliclass-modern-base-v3.0 151M, gliclass-base-v3.0 187M) scores all labels in one pass. Its card (author-run, A6000, batch 1) shows DeBERTa-v3-base-zeroshot-v2.0 falling from 24.6 to 0.47 examples/s going from 1 to 128 labels while gliclass-base holds 40-58/s, and zero-shot Banking77 F1 of only .567 (DeBERTa-large) and .446 (base) [23b]. finecat's card self-reports 91.0% on 18 zero-shot tagging tasks [8].
- Implication: cross-encoder cost is rows x labels, so shortlist labels with a bi-encoder, rerank with NLI, and train a head (SetFit or LR) whenever labelled sentences exist. MoritzLaurer has published nothing newer than 2024-12-28.

## (e) Static embeddings

- potion-base-32M [24]: MTEB(eng, v1) 52.13 vs MiniLM-L6 55.93 (93%). By task: classification 71.70 vs 69.25 (static wins), pair 78.17 vs 82.37, STS 73.93 vs 78.95, retrieval 32.67 vs 42.92. On v2: 54.63 vs 59.03; STS+PC 77.7 vs 82.3.
- Speed: authors claim about 500x over the bge-base teacher and about 70x over MiniLM on CPU [25]; static-retrieval-mrl-en-v1 is 87.4% of all-mpnet-base-v2 on NanoBEIR and 397x faster on CPU [26]. Tokenization dominates; model2vec-rs measured about 8,000 vs 4,650 embeddings/s single thread [25].
- 2026 successors: hotchpotch/bekko-static-embedding-v1 (2026-09-14, MIT, 205M, 1024-d Matryoshka, int8 ONNX; NanoBEIR-en 53.71 vs 50.35 for static-retrieval-mrl-en-v1, self-reported) [7]; RikkaBotan/stable-static-embedding-fast-retrieval-mrl-en-v2 (2026-05, 51.57). Minish has shipped no new English-only general potion since Jan 2025 (only multilingual-128M, potion-code-16M-v2 and ONNX exports).

## (f) Real-user notes

- **ORT thread pools ignore cgroup limits [27]:** issue #29510 (July 2026) says the intra-op pool is sized to host physical cores, so a CPU-limited container oversubscribes, worse with several sessions. Fixed by new `ORT_INTRA_OP_NUM_THREADS` / `ORT_INTER_OP_NUM_THREADS`; the `OMP_NUM_THREADS` fallback was dropped, so OMP does not bound ORT. Set `SessionOptions.intra_op_num_threads=2` explicitly. I could not confirm which release carries the fix.
- **Torch and OpenMP [28]:** sentence-transformers #2948 (open): a user could not cap encoding at 2 cores with `torch.set_num_threads` plus env vars. #3839 (2026-06, open): MiniLM under FastAPI/uvicorn deadlocked on macOS and starved threads on Linux until `OMP_NUM_THREADS`, `MKL_NUM_THREADS` and `TOKENIZERS_PARALLELISM=false` were set before importing torch. For a 2-vCPU batch job use 2, not 1 (my inference).
- **int8 [29]:** the sbert docs show `export_dynamic_quantized_onnx_model` (configs avx2/avx512/avx512_vnni/arm64) and report similar speedups across configs on the author's CPU; no accuracy loss is quoted. Pick `avx2` for an unknown amd64 host, then re-score.
- **HN and Reddit [25][30]:** a commenter saw 23x over their MiniLM ONNX search app after switching to potion; a Reddit post reports serialised requests behind FastAPI (only the original post was retrievable).
- **trust_remote_code in an offline container [31]:** gte-base-en-v1.5 #6 needed `configuration.py` and `modeling.py` copied from a second repo and the auto_map rewritten by hand. jina-v3 #123 (open): no obvious way to pin the revision of the separate flash-implementation code repo. jina-v3 #139: sentence-transformers 5.4 broke jina's custom module (duplicate `cache_dir`). stella_en_400M_v5 #17 and #18: CPU run fails with an xformers device error. Vendor the code and pin library versions, or pick native-architecture models (UltraBERT 5.20+, mdbr-leaf, mini-gte, UAE).

## (g) Could NOT find

- Official Mean(Task) for all-mpnet-base-v2, MiniLM-L12, jina-v3, bge-m3, gte-base-en-v1.5, modernbert-embed-base (rows incomplete).
- Any 2 vCPU throughput benchmark, or int8 accuracy loss, for these models.
- Independent replication of UltraBERT-Embed, finecat or mdbr-leaf claims (all author-reported).
- A numeric-aware sentence embedder; only diagnoses exist. NumEval (SemEval-2024 Task 7) was not retrieved.
- Reddit thread bodies (direct fetch blocked); HN had no ONNX/2-vCPU thread.
- A 10-30 shot SetFit curve.
- EuroBERT licence terms for jina-v5-nano (not checked).

## Sources

[1] https://mteb-leaderboard-backend.hf.space/v1/benchmarks/MTEB(eng,%20v2)/scores (UI https://huggingface.co/spaces/mteb/leaderboard) [2] https://huggingface.co/api/models/<id> [3] https://huggingface.co/dmis-lab/UltraBERT-Embed-150M, paper https://arxiv.org/abs/2610.15028 [4] https://huggingface.co/MongoDB/mdbr-leaf-mt [5] https://huggingface.co/jinaai/jina-embeddings-v5-text-nano [6] https://huggingface.co/jxm/cde-small-v2 [7] https://huggingface.co/hotchpotch/bekko-static-embedding-v1, https://huggingface.co/hotchpotch/bekko-embedding-v1-a8m [8] https://huggingface.co/dleemiller/finecat-nli-ultra-m, https://huggingface.co/dleemiller/finecat-nli-v2-m, https://huggingface.co/dleemiller/finecat-nli-s [9] https://huggingface.co/tasksource/ModernBERT-base-nli, https://huggingface.co/tasksource/ModernBERT-large-nli [10] https://huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli, https://huggingface.co/MoritzLaurer/ModernBERT-large-zeroshot-v2.0 [11] https://huggingface.co/cross-encoder/nli-deberta-v3-base [12] https://huggingface.co/tals/albert-xlarge-vitaminc-mnli, https://huggingface.co/tals/albert-base-vitaminc-mnli [13] https://arxiv.org/abs/2509.05691 [14] https://arxiv.org/abs/1901.03735 [15] https://arxiv.org/abs/1909.07940 [16] https://arxiv.org/abs/2204.05660 [17] https://aclanthology.org/2022.blackboxnlp-1.20, https://arxiv.org/abs/2502.14734 [18] https://arxiv.org/abs/2209.11055 [19] https://news.ycombinator.com/item?id=49858795 [20] https://arxiv.org/abs/1909.00161 [21] https://arxiv.org/abs/2104.14690 [22] https://arxiv.org/abs/1911.03814 [23] https://arxiv.org/abs/2508.07662 [23b] https://huggingface.co/knowledgator/gliclass-modern-large-v3.0 [24] https://huggingface.co/minishlab/potion-base-32M [25] https://news.ycombinator.com/item?id=44021883, https://news.ycombinator.com/item?id=42164071 [26] https://huggingface.co/blog/static-embeddings [27] https://github.com/microsoft/onnxruntime/issues/29510 [28] https://github.com/huggingface/sentence-transformers/issues/2948, https://github.com/huggingface/sentence-transformers/issues/3839 [29] https://sbert.net/docs/sentence_transformer/usage/efficiency.html [30] https://www.reddit.com/r/LocalLLaMA/comments/1j0mi30/best_practice_for_scaling_embeddings/ [31] https://huggingface.co/Alibaba-NLP/gte-base-en-v1.5/discussions/6, https://huggingface.co/jinaai/jina-embeddings-v3/discussions/123, https://huggingface.co/jinaai/jina-embeddings-v3/discussions/139, https://huggingface.co/NovaSearch/stella_en_400M_v5/discussions/17
