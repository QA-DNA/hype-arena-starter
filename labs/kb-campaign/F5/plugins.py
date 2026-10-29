"""F5 feature-plugin registry (lie fingerprints, source priors, unsure cues, priors).

ref = harness plugin spec, valid with cwd = $KBC (Mac) or $KBC_ROOT (box): e.g.
  run.py --variant v9='{"model": "lrC0.1", "extra_features": [["F5/fp.py:round_up"]]}'
Every plugin uses only public information and the labels of labelled rows of OTHER pages (leave-page-out).
'transfer' says whether the signal is a generic mechanism or a fingerprint of the organizers' practice generator.
Column names: fp.COLS[name]. Measured gains (OOF, P80/P10) are in the F5 report.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fp  # noqa: E402

_D = {
    "lie_stale": ("stale value after a visible change (anchors / votes), premature value re-contradicted, gap since the change", "generic"),
    "lie_mult": ("numeric perturbation vs the reference value: x0.1..x10 multiples, power of ten, direction, |log ratio|, digit change, roundness gain, rounder-and-larger, value roundness", "generator-specific (round-number hype lies)"),
    "lie_swap": ("value stated for another subject's same attribute or the same subject's other attribute, never for its own key", "generic"),
    "lie_bool": ("boolean fact, negated value, flip vs the nearest prior anchor", "partly generator-specific (negated booleans)"),
    "lie_date": ("date fact, stated date after the row date, log shift to the nearest anchor date", "generic"),
    "restate": ("event- or period-scoped subject, row later than every other observation, restatement words, power-of-ten interactions", "generic (closed periods hold fixed values)"),
    "restate2": ("retrospective statement: event-scoped subject dated >= 60 days after every other observation of its key, x power-of-ten, log gap", "generic"),
    "src_text": ("row text, generic lexicons: first person, hype, exclamation, speaker, hedge, negation, tail after the last digit, boast in the tail, subject not named, future date, today conflict, length, future phrasing", "generator-specific (voice)"),
    "txt_tuned": ("hyp.py's practice-tuned joke-tail and undercut regexes (designed on all practice rows: optimistic)", "generator-specific, optimistic"),
    "src_page": ("page size, relative position, first/last row, page shares of first-person / hype / social rows, subjects on the page", "generator-specific (page genre)"),
    "src_pagelie": ("number of other rows on the page where a hard lie rule fires (stale, both-sides mismatch, multiple, swap)", "generic"),
    "src_idblock": ("kernel-smoothed false / unsure rate of labelled rows nearby in file order (own page excluded)", "GENERATOR-SPECIFIC (id layout), does not transfer"),
    "uns_tl": ("unsure timeline cues: no anchor at/before the date, no anchor, no observation, gaps, evidence counts", "generic"),
    "prior": ("leave-page-out Beta-smoothed lie / unsure rates per attribute, key, kind; label-free attribute change rate; distinct values of the key", "world-specific, refit per world"),
    "kind_oh": ("one-hot value kind", "generic"),
    "round_up": ("single column: the value is rounder than and larger than its reference value (best F5 lie fingerprint)", "generator-specific (round-number hype lies)"),
    "w_nds": ("single column of lie_stale: distinct other pages contradicting the value since its last match before the date; the only F5 column accepted on top of F2's Chain (F5/onf2.py:OnChain fact layer)", "generic"),
    "nulls": ("selection-noise control: 10 permuted copies of real F5 columns", "control, never use as a feature"),
}

PLUGINS = {name: {"ref": f"F5/fp.py:{name}", "desc": d, "transfer": t, "k": len(fp.COLS[name])} for name, (d, t) in _D.items()}

if __name__ == "__main__":
    for k, v in PLUGINS.items():
        print(f"{k:12s} k={v['k']:2d} {v['ref']:22s} {v['transfer']}")
