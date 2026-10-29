# F5 report: lie fingerprints, unsure cues and priors

Saved by the orchestrator from F5's final message (02:16). Every number is out of fold on P80 and P10, or a suite test track, from a line in `results/F5.jsonl`, `results/F5-remote.jsonl` or `results/F5-paired.jsonl`. Selection used P80 and P10 only.

## Headline

1. F2's Chain dominates; only one F5 column adds to it on practice: `lie_stale.W_nds`, +0.0026 mean points, confirmed by the paired test on both tracks.
2. That gain does not transfer: on `t` suite tracks W_nds costs about 0.02 points (Sdev-jt 0.9414 -> 0.9221, Ssealed-jt 0.9409 -> 0.9182); neutral on `r` tracks.
3. On top of V9 the fingerprints mostly help P10 and leave P80 flat or worse. Exception: `src_idblock` helps both but is generator-specific.

## Top 3 (mean points over P80 and P10)

| # | Config | P80 | P10 | ECE P80 / P10 | Sdev-jt / jr | Ssealed-jt / jr |
|---|---|---|---|---|---|---|
| 1 | `F5/onf2.py:OnChain {"fC": 10.0, "fact": ["lie_stale.W_nds"]}` | 0.8339 | 0.7656 | 0.0106 / 0.0395 | 0.9221 / 0.9251 | 0.9182 / 0.9386 |
| 2 | `F5/onf2.py:OnChain {"fC": 10.0, "fact": ["lie_stale.W_nds", "src_pagelie.pg_other_swap"]}` | 0.8387 | 0.7645 | 0.0123 / 0.0403 | 0.9248 / 0.9244 | 0.9229 / 0.9384 |
| 3 | `F5/f5v.py:Variant {"model": "lrC0.1", "scorer_pts": true, "extra_features": ["F2/f2feat.py:all"], "plugins": ["src_idblock"]}` | 0.8324 | 0.7083 | 0.0223 / 0.0577 | 0.6399 / 0.9376 | 0.6630 / 0.8530 |
| ref | `F5/onf2.py:OnChain {}` (= F2 Chain viterbi, eps_a 0.0005, lam_scale 0.7, mono 0.1, pi_o 1, vote_lr 48) | 0.8313 | 0.7632 | 0.0117 / 0.0389 | 0.9414 / 0.9247 | 0.9409 / 0.9389 |

- #1 is the only config that passes F5's pre-registered rule (gain >= max(0.002, best null + 0.002), no track losing more than 0.002) and the paired check. Paired vs Chain: P80 +0.0026 (se 0.0010, wins 19/8, n=40), P10 +0.0037 (se 0.0024, wins 20/7, n=30). Mean 0.7998; accuracy 0.9162 / 0.8773; P80 false P/R 0.820 / 0.726.
- #2 has the highest raw mean (0.8016) but the rule rejected it (+0.0018 with P10 -0.0011 at that step). Paired: P80 +0.0049 (se 0.0010, wins 28/5), P10 -0.0026 (se 0.0029, wins 12/17). Tuned for P80.
- #3 is the best V9-family config but generator-specific (`src_idblock`); transfer near always-true (Sdev-jt 0.64). Best V9-only: `f5v {"model": "lrC0.1", "scorer_pts": true, "plugins": ["lie_stale", "lie_mult", "src_idblock"]}` 0.8155 / 0.7025; paired vs C0.1 base P80 +0.0037, P10 +0.0165 (se 0.0063, wins 23/7); suite Sdev-jt 0.6685, Sdev-jr 0.8754, Ssealed-jt 0.6687, Ssealed-jr 0.6894.
- Confidence in [0.5, 1] for all three (OnChain via F2 RowCal and the arena rule; f5v clips).

## Runtime on a 20k-row world (Sdev / Ssealed, 18,103 scored rows, remote box)

| Config | Time | Peak RSS |
|---|---|---|
| OnChain {} | 1.9 to 3.4 s | about 185 MB |
| #1 | 4.5 to 5.5 s | about 221 MB |
| #2 | 5.4 to 6.1 s | about 222 MB |
| f5v base | 8 to 10 s | about 210 MB |
| f5v + 3 plugins | 12 to 14 s | about 245 MB |
| f5v all12 | 17 to 19 s | about 300 MB |

All F5 plugins together about 6 s (lie_stale 1.9 s, src_text 1.3 s).

## Baselines (practice, out of fold)

| Config | P80 | P10 | Mean |
|---|---|---|---|
| v9 {} (select mf1) | 0.777 | 0.639 | |
| v9 arena C0.5 = f5v {} (reproduced exactly) | 0.8092 | 0.6739 | 0.7416 |
| f5v lrC0.1 scorer_pts | 0.8155 | 0.6868 | 0.7512 |
| F2 Chain best (as used by F5) | 0.8313 | 0.7632 | 0.7972 |

f5v lrC0.1 ECE 0.0246 / 0.0595.

## Rules (precision / recall, P80 | P10)

- Lies: stale_A 0.881/0.188 | 0.884/0.021; stale_W 0.667/0.238 | 0.448/0.304; stale_W2 0.735/0.130 | 0.687/0.173; premature_A 0.900/0.065 | 0.700/0.004; premature_W 0.750/0.097; both_sides_mismatch_A 0.552/0.209; mult_bucket_A 0.518/0.155; pow10_any 0.833/0.018; round_up_A 0.710/0.159 | 0.530/0.084; up_A 0.359/0.415; digit_change_A 0.340/0.184; sig1_value 0.179/0.357; swap_subj_A 0.333/0.043; swap_attr_A 0.750/0.011; swap_any_W 0.463/0.069; bool_flip_A 0.312/0.036; bool_false_value 0.240/0.065; date_after_row precision 0.111; date_shift_A 0.444/0.043.
- Source priors: row_social 0.250/0.079; page_social 0.250/0.282; page_social_major 0.337/0.105; last_on_page 0.192/0.181; page_has_detected_lie 0.154/0.570; idblock > 0.25: 0.411/0.209 | 0.169/0.039.
- Unsure: no_anchor_before 0.049/0.769 | 0.027/0.959; joke_tail_tuned 0.160/0.308; undercut_tuned 0.103/0.179; tail_boast 0.046/0.077; subj_not_named 0.020/0.333; no_anchor_before AND joke_tuned 0.303/0.256 | 0.201/0.319; no_anchor_before AND social_page 0.117/0.282.
- Restatement: restate_event_later P80 67 true / 20 false / 1 unsure of 88 rows (precision 0.761). p-466 and p-455 (true restatements) still predicted false at 0.887 by the C0.1 V9 base.

## What worked and what did not

### On top of F2 Chain (`F5/onf2.py`)

- Controls: fact-level LR with no F5 column costs P10 -0.018 at C0.1, -0.0048 at C1, -0.0025 at C10; row-level LR with no column -0.0025. Paired, the controls are about 0.
- Fact-layer column forward (fC 10, 110 candidates including 10 nulls, `log_colforward_chain_fact.txt`): step 1 accepted W_nds at +0.0026 (best null -0.0008); step 2 stopped (pg_other_swap +0.0018 with P10 -0.0011; best null +0.0001).
- Stack-layer column forward (sC 1, `log_colforward_chain_stack.txt`) stopped at [] (best A_stale +0.0010: P80 +0.0042, P10 -0.0023).
- Whole plugin blocks hurt: lie_mult block 0.8192 / 0.7349; round_up fact column 0.8266 / 0.7524 at fC 0.1 and 0.8276 / 0.7602 at fC 1.

### On top of V9 (paired, C0.1 base, n = 40 P80, 30 P10)

| Plugin / set | P80 delta (se) | P10 delta (se) | Note |
|---|---|---|---|
| src_idblock | +0.0082 (0.0018), wins 27/8 | +0.0057 (0.0027) | generator-specific |
| lie_mult | -0.0025 | +0.0119 (0.0059) | |
| lie_stale | -0.0008 | +0.0079 (0.0038) | |
| stack_gen | +0.0017 | +0.0096 (0.0060) | generic |
| stale_mult_idb | +0.0037 | +0.0165 | |
| round_up | +0.0003 | +0.0041 | dBrier -0.0024 |
| restate2 | -0.0008 | +0.0028 | |
| lie_swap | +0.0004 | +0.0034 | |
| unsure 'ev' | -0.0009 | -0.0001 | |
| 10 null columns | -0.0072 | -0.0052 | every extra noise column costs points |
| all12 | -0.0122 | +0.0057 | |
| generic set | -0.0048 | +0.0060 | |
| prior | -0.0075 | -0.0066 | |
| src_text | -0.0064 | -0.0022 | |
| src_page | -0.0049 | -0.0014 | |
| src_pagelie | -0.0048 | -0.0006 | |
| lie_bool | -0.0028 | -0.0019 | |
| lie_date | -0.0003 | -0.0033 | |
| kind_oh | -0.0015 | -0.0024 | |

- Unsure layer for confidence only (`unsure: "conf"`, `conf_pu: true`): points unchanged, ECE P80 0.0246 -> 0.0094, P10 0.0597 -> 0.0536.
- C=0.5 forward selection: plugin level accepted src_idblock then lie_bool (0.7523); column level accepted round_up only; 10-null control deltas +-0.0022.
- C=0.1 column forward with nulls: stopped at [].
- Ablation of all12 at C0.1 (full set 0.80285 / 0.68998, `log_ablate_C01.txt`), change in mean points on removal: src_text +0.0039 (P80 +0.0095), prior +0.0006, lie_bool +0.0002, kind_oh 0.0000, restate -0.0006, lie_date -0.0023, lie_swap -0.0026, lie_stale -0.0027, src_pagelie -0.0028, src_page -0.0033, uns_tl -0.0039, lie_mult -0.0041. All within about 2x the null noise.

### On top of F2 feature plugins in V9 (`f5v`, lrC0.1)

| Plugins | with `F2/f2feat.py:core` | with `F2/f2feat.py:all` |
|---|---|---|
| none | 0.8171 / 0.6970 | 0.8155 / 0.7039 |
| src_idblock | 0.8355 / 0.6978 | 0.8324 / 0.7083 |
| round_up | | 0.8181 / 0.7175 |
| lie_mult | 0.8255 / 0.7037 | |
| lie_stale + lie_mult + src_idblock | 0.8229 / 0.7107 | 0.8292 / 0.7084 |
| stack_gen | 0.8197 / 0.7038 | |

None comes near Chain's P10 of 0.763.

### Suite transfer (test only)

- V9 family on `t` tracks: about 0.64 to 0.67 on Sdev-jt and Ssealed-jt.
- all12 is the worst on practice but the best V9-family config on the suite: S refit tracks 0.2720 vs base 0.2227; X 0.7609 vs 0.7184; Sdev-nr 0.8559 vs 0.7039; much worse on Sprac (0.549 vs 0.681).
- Sdiag, Sext* and Spilot negative for every V9-family config (about -0.2 to -0.36).
- Text fingerprints are generator-specific: first-person share 0.431 of rows on Sdev vs 0.036 in practice.

## Fingerprints by transfer class

- Generic: lie_stale, lie_swap, lie_date, restate, restate2, src_pagelie, uns_tl, kind_oh, w_nds (generic mechanism, but the weight learned on practice does not transfer).
- Generator-specific: src_idblock (reads the id layout), lie_mult and round_up (round-number hype lies), lie_bool (negated booleans), src_text and src_page (voice and page genre), txt_tuned (designed on all practice rows: optimistic), prior (refit per world).

## Plugins (`F5/plugins.py`, final; refs `F5/fp.py:<name>`, column names in `fp.COLS[name]`)

lie_stale 9, lie_mult 12, lie_swap 6, lie_bool 3, lie_date 3, restate 6, restate2 3, src_text 14, txt_tuned 2, src_page 11, src_pagelie 5, src_idblock 2, uns_tl 7, prior 9, kind_oh 8, round_up 1, w_nds 1 (the one column that adds to Chain), nulls 10 (control only).

Signal on Chain: w_nds only. Signal on V9: src_idblock (generator-specific), lie_mult and lie_stale (P10 only), stack_gen, round_up. No signal or negative: src_text, src_page, prior, kind_oh, lie_bool, lie_date, restate, uns_tl as a fact block, txt_tuned on P80.

## Everything tried

- `F5/rules.py`: about 40 rules (above).
- `F5/f5v.py`: model lr (C0.5), lrC1.0, lrC0.1, lrC0.05; each plugin alone, pairs, all12, generic set; column forward (`cols`); stack (stack6, stack_gen); unsure ev and conf with and without conf_pu; scorer_pts false and true; extra_features F2 core and all.
- `F5/onf2.py:OnChain`: {} reference; flr and slr controls at C 0.1, 1, 10; fact forward over 110 + 109 columns; stack forward over 110 columns; lie_mult block; round_up at fC 0.1 and 1.
- Paired rounds 1 and 2 on V9 at C0.5, C0.1, C0.05 (`cfg_paired1/2.json`), round 3 on Chain (`cfg_paired3.json`).
- Suite runs: suite1 (7 f5v configs), suite2 (3 OnChain configs), suite3 (top-3 #3), each on 44 tracks. Logs `F5/log_*.txt`.

## Suspicious

- OnChain's training-side inputs are slightly optimistic: Chain's isotonic fact map is fitted in sample before the out-of-fold F5 layer (training-side selection only; test rows stay unlabelled).
- Practice and suite disagree in direction: practice selection would never pick all12, yet it is the best V9-family config on the suite; W_nds helps practice and hurts transfer.
- remote.sh printed `line 161: o: command not found` during the suite1 launch; the run completed 308/308.

## Harness requests

1. Done: v9 `select='arena'`.
2. Done: remote.sh lock deadlock fixed.
3. P10 results lines lack a confusion matrix; add one.
4. Add repeated-fold P80 and 30-seed P10 tracks to run.py so the denoised check (`F5/paired.py`) can run on the box (Mac-only now).
5. remote.sh line 161 message.
