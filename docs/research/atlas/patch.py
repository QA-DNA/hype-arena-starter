import json
p='catalogue.json'; E=json.load(open(p)); by={e['name']:e for e in E}
# ponytail: one-off, already applied on 2026-10-28; it appends entries, so refuse a second run
if 'Self-training on unlabelled rows' in by: raise SystemExit('patch already applied to catalogue.json')
def up(name, **kw):
    e=by[name]
    m=kw.pop('measured',None)
    if m: e['fit']='Measured: '+m+' '+e['fit']
    e.update(kw)
up('Time-windowed majority vote', measured='exact-value vote (V1) scores 0.756 accuracy (R80) against 0.833 for always-true; it catches only half the false rows.')
up('ACCU / AccuSim / AccuCopy (source accuracy and copy detection)', verdict='TRY',
   measured='page-reliability reweighting (V4) moved nothing (0.737 vs 0.737 R80; 0.697 vs 0.697 R10), even though lies cluster (186 of 277 false rows sit on pages with 2+ false rows). The harness cannot simulate the real run\'s 10x unlabelled votes, where it may matter.',
   why='Keep page reliability as one feature of the fact model, not as the decider, until it measures better with many votes.')
up('Truth discovery in a dynamic world (value lifespans, CEF)', measured='reading evidence after the date is the largest rule-level gain: latest-anchor V2 to V2b (+next anchor) is +8.3 points (R80), forward-only to symmetric window is +4.1. 150 true single-fact rows are a new value confirmed only later.')
up('Per-key HMM over candidate values (Viterbi + forward-backward)', verdict='TRY',
   why='Not measured. The bracket-feature fact model already captures change-then-confirmation; try the HMM if errors cluster on keys with 3+ values.')
up('Staleness hazard (how far an observation can be trusted)', verdict='IDEA-ONLY',
   measured='a gap-based unsure rule was rejected by inner selection in every split; 29 of 39 unsure rows have their nearest same-key observation 90+ days away, but so do 204 true rows.',
   why='Keep distance only as a feature of the fact model.')
up('Typed value enum with to_interval() (hand-rolled)', measured='intervals (V5) add +0.9 accuracy points over the vote rule and +0.7 over V2b (fixes "2026" vs "2026-03-24", p-168).')
up('Noisy-OR blame with one EM step', measured='row P(true) = product of fact P(true) is what the best model (V9/V11) uses. An explicit blame pass (V6) was neutral (-0.5 points) and marking every fact of a false row as weak negative evidence hurt (-1.5 points).',
   why='Keep the product for rows; skip the blame pass until the fact model is trained on soft blame labels.')
up('Logistic regression stacker over evidence features', measured='per-fact LR over bracket features (V9) reaches 0.902 accuracy, 0.553 macro-F1, false precision 0.763, Brier 0.077 (R80, optimistic); with one round of self-training (V11) 0.907. In the sparse 10%-labelled regime row-level LR (V8) is the best model at 0.851. LR beat or matched gradient boosting in every regime.')
up('Gradient boosting (perpetual, lightgbm3)', measured='HGB trails LR: 0.876 vs 0.902 (V9, R80), 0.840 vs 0.851 (V8, R10).',
   why='Measured below logistic regression; not worth the dependency.')
up('Isotonic regression (PAV) and histogram binning', verdict='ADOPT',
   measured='isotonic fitted on leave-one-page-out scores cuts ECE from about 0.16 to 0.04 on every rule and model (V7: 0.167 to 0.044 R80, 0.158 to 0.050 R10).',
   why='Measured to work at our data size when fitted out-of-fold by page.')
up('Platt scaling (and temperature scaling)', verdict='TRY', why='Not measured; the fallback if isotonic plateaus cause ties or the shift to unseen subjects hurts.')
up('Score-to-confidence mapping and the unsure band', measured='no variant predicts unsure usefully: the 39 unsure rows match anchors as often as true rows (p-1032, p-1519). Predicting unsure on low confidence lowered macro-F1 in inner selection.')
up('Greedy claim selection with type quotas and a root-fact cap', measured='carrying the latest anchor forward is unsafe for as-of claims: hiding the last 20% of dates, the latest earlier anchor matches the final true value for only 53.4% of keys (coverage 75.5%).')
E.append({"name":"Bracket evidence features (before, same day, after)","kind":"feature design","steps":["S3","S6","S2"],"verdict":"ADOPT","insanity":2,
 "what":"For each fact: does it match the nearest labelled anchor before its date, on the same day, after it; day gaps to each; stale flag (matches an older value only); premature flag (matches only a later value); kernel-weighted vote support; magnitude ratios to neighbouring values.",
 "fit":"Measured: the biggest single lever. Rules reach about 0.75 accuracy (R80); a per-fact logistic model over these features reaches 0.90 to 0.91 with false precision 0.76 to 0.79 and Brier 0.073. Pattern table: a fact matching anchors on both sides is 275 true / 0 false; mismatching both sides is 30 true / 68 false; new value confirmed later is 150 true / 18 false.",
 "pros":["Turns 'change versus lie' into features the model can weigh","Each feature is a sentence in the explanation"],
 "cons":["V9 features were designed after reading R80 errors, so 0.90 is optimistic","The change moment between two bracketing anchors stays unobservable (p-499, p-985)","Power-of-ten feature misfires on later restatements (p-466, p-455)"],
 "rust":"std, about 150 lines over the timeline index","python":"labs/kb-experiments/v9.py",
 "why":"The measured core of the labeller.","links":[]})
E.append({"name":"Self-training on unlabelled rows","kind":"algorithm","steps":["S6","S2"],"verdict":"REJECT","insanity":2,
 "what":"Label the unlabelled rows with the model, add the confident ones as pseudo-anchors, refit.",
 "fit":"Measured: one round (V11) gives +0.5 points in R80 (0.902 to 0.907) and -0.7 in R10 (0.816 to 0.809).",
 "pros":["Uses the 90% unlabelled rows"],"cons":["Confirms its own mistakes when labels are scarce"],
 "rust":"std","python":"labs/kb-experiments/v9.py",
 "why":"Gain too small and negative in the sparse regime.","links":[]})
json.dump(E,open(p,'w'),ensure_ascii=False,indent=1)
print(len(E))
