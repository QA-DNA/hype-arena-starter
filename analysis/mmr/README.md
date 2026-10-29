# MMR research material

Supporting files for [docs/research/mmr.md](../../docs/research/mmr.md). Exploratory, not
competition code. Nothing here reads anything but `data/`.

| Path | What |
| --- | --- |
| `research/r1-foundations.md` | MMR definition, theory, the diversity family, libraries, real-user threads, Rust crates |
| `research/r2-applications.md` | Fact verification, conflicting and temporal evidence, truth discovery, KG summarization, data selection |
| `research/r3-improvements.md` | Risk-aware and constrained selection, DPP, robust selection, untested ideas |
| `exp-claims/` | Claim-selection simulation: top-k vs MMR vs caps vs DPP under correlated failures |
| `exp-evidence/` | Evidence retrieval for labelling: top-k vs MMR variants, oracle verifier |

The research reports were written by Claude Sonnet workers using free web sources. Each one
marks which numbers it read from a source, which come from a search snippet, and which come
from memory.

## Run

Python 3.11+ with numpy, pandas and scikit-learn, from the repository root:

```sh
python analysis/mmr/exp-claims/claims_mmr.py      # ~4 s, writes results.md and CSVs beside it
python analysis/mmr/exp-evidence/evidence_mmr.py  # ~10 s, writes REPORT_body.md beside it
```

Both are deterministic (fixed seed). The claim probabilities are an uncalibrated proxy:
compare strategies with each other, not with the real score.
