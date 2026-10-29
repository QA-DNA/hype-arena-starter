"""F2 (temporal resolution) feature plugins. Each ref is "module:func" with module = F2/f2feat.py (path relative to
the kbc root, which is the cwd of run.py locally and on the remote box). func(world) -> (world.n_facts x k) finite
floats, own page always excluded, labels read only from labelled rows (anchors; hazard lambda fitted per value kind
on the same world's labelled anchors)."""

M = "F2/f2feat.py"

PLUGINS = {
    "f2_hmm": {"ref": f"{M}:hmm", "k": 3,
               "desc": "per-key HMM forward-backward: P(true state at the fact's date agrees with it), P(unseen-value "
                       "state), no-other-page-evidence flag"},
    "f2_viterbi": {"ref": f"{M}:viterbi", "k": 12,
                   "desc": "MAP timeline from the date: max-marginal margin, segment age/remaining (log days), gap to "
                           "previous/next change point, segment support (anchors, votes agreeing, votes against), stale "
                           "flag, premature flag, agrees with MAP value, distance to nearest change point"},
    "f2_tecore": {"ref": f"{M}:tecore", "k": 1,
                  "desc": "TeCoRe-style max-weight consistent timeline (anchors hard, false anchors forbidden): margin "
                          "of the best timeline agreeing with the fact over the best disagreeing one"},
    "f2_seg": {"ref": f"{M}:seg", "k": 1,
               "desc": "penalised segmentation (BIC-like penalty c log n, exact DP): share of a penalty sweep "
                       "c in {.25,.5,1,2,4} whose MAP value at the date agrees with the fact"},
    "f2_stale": {"ref": f"{M}:stale", "k": 6,
                 "desc": "staleness hazard exp(-lambda_kind g): gap to latest agreeing obs before / earliest after, to "
                         "latest agreeing anchor before, to latest disagreeing anchor before; anchor stale and "
                         "premature flags"},
    "f2_bracket": {"ref": f"{M}:bracket", "k": 15,
                   "desc": "one-hot before/same/after cell (Y/N anchor agrees/disagrees, y/n votes only, - nothing)"},
    "f2_core": {"ref": f"{M}:core", "k": 10,
                "desc": "compact block: hmm post + P(other), viterbi margin, cp distance, segment support anchors and "
                        "votes, stale, premature, staleness back and forward"},
    "f2_all": {"ref": f"{M}:all", "k": 23,
               "desc": "hmm + viterbi + tecore + seg + stale concatenated"},
}
