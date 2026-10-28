# w6 note: the `kb/` working copy

`fusion.py` and `report.py` import the V9/V11/V12 models from a working copy of `labs/kb-experiments` placed at
`w6/kb/` and put on `sys.path`. The copy is not committed because it would duplicate that lab. Recreate it with
`cp -R labs/kb-experiments w6/kb` and apply the two edits below. Compared with `labs/kb-experiments` as of commit
`c3d908b`, every file of the copy was byte-identical except `exp.py` and `v9.py` (the copy also lacked
`requirements.txt`). Both edits are commented in the code as leaving the numbers unchanged.

1. `exp.py`: `DATA` points at `/tmp/veridyct-emb/common/` (the organizer data, a byte-identical copy of `data/`; see
   the lab README for putting `practice.csv` there) instead of the repo's `data/` directory.
2. `v9.py`: `_v9_rest` always stores the calibrated row probabilities in `LAST`, including the training-row ones
   (`prow_tr`), instead of only the test-row `prow` when `keep` is set. `fusion.py` reads `LAST['prow_tr']` to pick the
   abstention threshold on labelled rows.

```diff
--- a/exp.py
+++ b/exp.py
@@ -7,7 +7,7 @@
 from sklearn.isotonic import IsotonicRegression
 from sklearn.model_selection import GroupKFold
 
-DATA = str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'data') + '/'
+DATA = '/tmp/veridyct-emb/common/'  # w6 copy: organizer data, cmp-identical to VERIDYCT/data
 LABELS = ['true', 'false', 'unsure']
 INF = float('inf')
 
--- a/v9.py
+++ b/v9.py
@@ -239,7 +239,7 @@
                     if best is None or sc > best[0]: best = (sc, t, band, G)
         CHOSEN.append(best[1:])
         out = decide(prow, best[1], best[2]); out[(GAP > best[3]) & (out == 'true')] = 'unsure'
-        if keep: LAST['prow'] = prow
+        LAST['prow'], LAST['prow_tr'] = prow, prow_tr  # w6: always stash calibrated row P(true) (hidden, train-OOF); no numeric change
         conf = np.where(out == 'true', prow, 1 - prow)
         return out, conf
 
```
