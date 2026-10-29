"""F5 single-rule variants: each fingerprint as a hard rule, measured out-of-fold by the harness.

Variant(rule=NAME): a row 'fires' when any of its facts fires (row rules: when the row does). Target 'false' or
'unsure' rules label firing rows with the target and every other row 'true'; 'true' rules label firing rows
'true' and the rest 'unsure', so the confusion matrix gives the rule's precision for true. Only the world's
labelled rows of OTHER pages feed a rule (fp.py), so the scored rows are out-of-fold.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fp  # noqa: E402

from api import Base, Prediction  # noqa: E402


def _c(block, col):
    return lambda w: getattr(fp, block)(w)[:, fp.COLS[block].index(col)]


def _gt(block, col, t):
    return lambda w: getattr(fp, block)(w)[:, fp.COLS[block].index(col)] > t


def _and(*fs):
    return lambda w: np.logical_and.reduce([np.asarray(f(w)) > 0 for f in fs])


def _nn(w):
    s = fp.seq(w)
    return (s["Anprev"] > 0) & (s["Amb"] == 0) & (s["Ands"] >= 1) & (s["Ama"] == 0) & (s["Andu"] >= 1)


M = lambda col: _c("lie_mult", col)  # noqa: E731
RULES = {  # name -> (target, fact-level function returning a bool/0-1 array over facts)
    # 1. lies
    "stale_A": ("false", _c("lie_stale", "A_stale")),
    "stale_W": ("false", _c("lie_stale", "W_stale")),
    "stale_W2": ("false", lambda w: (fp.seq(w)["Wmb"] > 0) & (fp.seq(w)["Wnds"] >= 2)),
    "premature_A": ("false", _c("lie_stale", "A_prem")),
    "premature_W": ("false", _c("lie_stale", "W_prem")),
    "both_sides_mismatch_A": ("false", _nn),
    "mult_bucket_A": ("false", _and(M("bucket"), M("ref_anchor"))),
    "mult_bucket_any": ("false", M("bucket")),
    "pow10_any": ("false", M("p10")),
    "round_up_A": ("false", _and(M("round_up"), M("ref_anchor"))),
    "up_A": ("false", _and(M("up"), M("ref_anchor"))),
    "digit_change_A": ("false", _and(M("digit"), M("ref_anchor"))),
    "sig1_value": ("false", M("sig1")),
    "swap_subj_A": ("false", _c("lie_swap", "swap_subj_A")),
    "swap_attr_A": ("false", _c("lie_swap", "swap_attr_A")),
    "swap_any_W": ("false", lambda w: fp.lie_swap(w)[:, 2:4].sum(1) > 0),
    "bool_flip_A": ("false", _c("lie_bool", "bool_flip_A")),
    "bool_false_value": ("false", _c("lie_bool", "bool_false")),
    "date_after_row": ("false", _c("lie_date", "date_after_row")),
    "date_shift_A": ("false", _gt("lie_date", "date_shift_log", 0)),
    # restatements: fires -> TRUE
    "restate_event_later": ("true", _and(_c("restate", "event_subj"), _c("restate", "later_than_all"))),
    "event_subject": ("true", _c("restate", "event_subj")),
    # 2. source priors
    "row_social": ("false", lambda w: fp.src_text(w)[:, [0, 2, 3]].sum(1) > 0),
    "row_fp_sing": ("false", _c("src_text", "fp_sing")),
    "row_hype": ("false", _c("src_text", "hype")),
    "page_social": ("false", _c("src_page", "pg_social_any")),
    "page_social_major": ("false", _gt("src_page", "pg_social_share", 0.3)),
    "last_on_page": ("false", _c("src_page", "is_last")),
    "page_has_detected_lie": ("false", _c("src_pagelie", "pg_other_any")),
    "page_big": ("false", _gt("src_page", "page_size_log", np.log(10) - 1e-9)),
    "idblock_false_rate_gt_0.25": ("false", _gt("src_idblock", "id_false_rate", 0.25)),
    # 4. priors
    "attr_false_rate_gt_0.3": ("false", _gt("prior", "attr_false", 0.3)),
    "key_false_rate_gt_0.3": ("false", _gt("prior", "key_false", 0.3)),
    "attr_change_rate_gt_0.6": ("false", _gt("prior", "attr_change_W", 0.6)),
    # 3. unsure cues
    "U_no_anchor_before": ("unsure", _c("uns_tl", "no_anchor_before")),
    "U_no_anchor": ("unsure", _c("uns_tl", "no_anchor")),
    "U_no_obs": ("unsure", _c("uns_tl", "no_obs")),
    "U_joke_tail_tuned": ("unsure", _c("txt_tuned", "joke_tail_tuned")),
    "U_undercut_tuned": ("unsure", _c("txt_tuned", "undercut_tuned")),
    "U_tail_boast": ("unsure", _c("src_text", "tail_boast")),
    "U_hedge": ("unsure", _c("src_text", "hedge")),
    "U_subj_not_named": ("unsure", _c("src_text", "subj_not_named")),
    "U_future_date_text": ("unsure", _c("src_text", "future_date_text")),
    "U_today_conflict": ("unsure", _c("src_text", "today_conflict")),
    "U_date_after_row": ("unsure", _c("lie_date", "date_after_row")),
    "U_no_anchor_before_and_social_page": ("unsure", _and(_c("uns_tl", "no_anchor_before"), _c("src_page", "pg_social_any"))),
    "U_no_anchor_before_and_tail_boast": ("unsure", _and(_c("uns_tl", "no_anchor_before"), _c("src_text", "tail_boast"))),
    "U_no_anchor_before_and_joke_tuned": ("unsure", _and(_c("uns_tl", "no_anchor_before"), _c("txt_tuned", "joke_tail_tuned"))),
    "U_attr_unsure_rate_gt_0.05": ("unsure", _gt("prior", "attr_unsure", 0.05)),
}


def fires(world, rule):
    target, fn = RULES[rule]
    f = np.asarray(fn(world), float) > 0
    r = np.zeros(world.n, bool)
    np.logical_or.at(r, world.frow, f)
    return target, r


class Variant(Base):
    def __init__(self, rule="stale_A"):
        self.rule = rule

    def predict(self, world):
        target, r = fires(world, self.rule)
        other = "unsure" if target == "true" else "true"
        lab = np.where(r, target, other).astype(object)
        conf = np.where(lab == "unsure", np.nan, 0.75)
        return Prediction(lab, conf, None)
