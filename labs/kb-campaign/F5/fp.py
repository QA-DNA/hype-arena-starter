"""F5 feature plugins: lie fingerprints, source priors, unsure cues, attribute priors.

Every public function `name(world) -> (world.n_facts x k)` is a harness feature plugin (spec `F5/fp.py:name`
with cwd = $KBC, or `fp:name` with F5/ on sys.path). Only public information is used: text, dates, pages, stated
facts, and labels of LABELLED rows; evidence from the row's own page is always excluded, so a labelled training
row never sees its own label (leave-page-out by construction). Column names: COLS[name].
"""
import hashlib
import math
import re
from collections import defaultdict

import numpy as np

try:
    from world import KINDS
except ImportError:  # standalone import outside the harness
    KINDS = ["quantity", "money", "duration", "name", "percent", "boolean", "date", "version"]

NUMK = ("quantity", "money", "duration", "percent")
COLS = {}


def _cols(name, cols):
    COLS[name] = cols


# ----------------------------------------------------------------- caching and roles
def _sig(world):
    h = hashlib.md5(world.labelled.tobytes())
    h.update("|".join(str(x) for x in world.label[world.labelled]).encode())
    return h.hexdigest()


def _cache(world, name, fn):
    c = world.__dict__.get("_f5c")
    s = (_sig(world), world.n, world.n_facts)
    if c is None or c.get("_sig") != s:
        c = {"_sig": s}
        world.__dict__["_f5c"] = c
    if name not in c:
        c[name] = fn(world)
    return c[name]


def roles(world):
    """Per row: 'T','F','U' for labelled rows, 'V' (vote) for unlabelled ones."""
    m = {"true": "T", "false": "F", "unsure": "U"}
    return np.array([m.get(lab, "V") if world.labelled[i] else "V" for i, lab in enumerate(world.label)], dtype=object)


def _groups(world):
    """okey -> (flat idx, consistency matrix); reuses the V5 helper when available."""
    try:
        from variants.v5 import groups
        return groups(world)
    except ImportError:
        out = {}
        for okey, obs in world.obs_typed.items():
            g = np.array([world.fstart[i] + j for i, j in obs], np.int64)
            fs = [world.flat[n] for n in g]
            C = np.array([[a.consistent(b) for b in fs] for a in fs], bool)
            out[okey] = (g, C, None)
        return out


# ----------------------------------------------------------------- timeline sequence helper
def _seq(world):
    """Per fact, two evidence sets (A = labelled-true anchors, W = anchors + unsure + unlabelled votes; labelled
    false rows never count), own page excluded. Returns dict of arrays (n_facts):
    for S in (A, W): mb/ma = has a consistent obs strictly before / after; lmb, fma = day offsets of the last
    consistent obs before and the first after; nds = distinct pages with an inconsistent obs in (lmb, 0];
    ndu = distinct pages inconsistent in [0, fma); gapc = days since the first inconsistent obs after lmb;
    any = has any obs; nprev = has an obs at or before the date; gap = days to the nearest obs; nv = distinct
    values among the set; ref (numeric value of the reference obs: latest at/before, else earliest after), refdd."""
    R = roles(world)
    nf = world.n_facts
    out = {}
    for S in ("A", "W"):
        for k in ("mb", "ma", "nds", "ndu", "gapc", "any", "nprev", "gap", "nv", "ref", "refdd", "nn"):
            out[S + k] = np.zeros(nf)
        out[S + "ref"][:] = np.nan
    fpage = world.page[world.frow]
    fdate = world.date[world.frow].astype(float)
    frole = R[world.frow]
    for g, cons, _ in _groups(world).values():
        m = len(g)
        if m < 2:
            for S in ("A", "W"):
                out[S + "gap"][g] = 9.0
                out[S + "gapc"][g] = 0.0
            continue
        pg = fpage[g]; dt = fdate[g]; rl = frole[g]
        other = pg[:, None] != pg[None, :]
        dd = dt[None, :] - dt[:, None]  # date_b - date_a
        C = np.asarray(cons, bool)
        _, pcode = np.unique(pg, return_inverse=True)
        P = np.zeros((m, pcode.max() + 1)); P[np.arange(m), pcode] = 1.0
        canon = [world.flat[n].canon for n in g]
        vcode = np.array([hash(c) for c in canon])
        numv = np.array([float(c) if isinstance(c, float) else np.nan for c in canon])
        for S, okr in (("A", rl == "T"), ("W", rl != "F")):
            valid = other & okr[None, :]
            match = valid & C; diff = valid & ~C
            lmb = np.where(match & (dd < 0), dd, -np.inf).max(1)
            fma = np.where(match & (dd > 0), dd, np.inf).min(1)
            since = diff & (dd > lmb[:, None]) & (dd <= 0)
            until = diff & (dd >= 0) & (dd < fma[:, None])
            nds = ((since.astype(float) @ P) > 0).sum(1)
            ndu = ((until.astype(float) @ P) > 0).sum(1)
            first_diff = np.where(since, dd, np.inf).min(1)
            gapc = np.where(np.isfinite(first_diff) & np.isfinite(lmb), -first_diff, 0.0)
            anyo = valid.any(1)
            nprev = (valid & (dd <= 0)).any(1)
            absd = np.where(valid, np.abs(dd), np.inf).min(1)
            o = out
            o[S + "mb"][g] = np.isfinite(lmb); o[S + "ma"][g] = np.isfinite(fma)
            o[S + "nds"][g] = nds; o[S + "ndu"][g] = ndu
            o[S + "gapc"][g] = gapc; o[S + "any"][g] = anyo; o[S + "nprev"][g] = nprev
            o[S + "gap"][g] = np.where(np.isfinite(absd), np.log1p(absd), 9.0)
            o[S + "nn"][g] = valid.sum(1)
            # distinct values among the set, and numeric reference value
            for a in range(m):
                vb = np.flatnonzero(valid[a])
                if len(vb):
                    o[S + "nv"][g[a]] = len(set(vcode[vb]))
                    prev = vb[dd[a, vb] <= 0]
                    if len(prev):
                        b = prev[np.argmax(dd[a, prev])]
                    else:
                        nxt = vb[dd[a, vb] > 0]; b = nxt[np.argmin(dd[a, nxt])]
                    o[S + "ref"][g[a]] = numv[b]; o[S + "refdd"][g[a]] = dd[a, b]
    return out


def seq(world):
    return _cache(world, "seq", _seq)


# ----------------------------------------------------------------- 1. lie fingerprints
_cols("lie_stale", ["A_stale", "A_nds", "A_gapc", "W_stale", "W_nds", "W_gapc", "A_prem", "W_prem", "W_ndu"])


def lie_stale(world):
    """Stale old value after a VISIBLE change: the value was seen before (consistent obs before the date), and
    after the last such sighting other pages stated a different value at or before the date. A = anchors only,
    W = anchors + unlabelled votes (works when anchors are sparse). Premature: value only seen after the date,
    older different value at/before it, and the old value is re-stated between the date and the confirmation."""
    s = seq(world)
    L = np.log1p
    cols = []
    for S in ("A", "W"):
        st = s[S + "mb"] * (s[S + "nds"] >= 1)
        cols += [st, L(s[S + "nds"]) * s[S + "mb"], L(s[S + "gapc"]) * st]
    for S in ("A", "W"):
        cols.append(s[S + "ma"] * (1 - s[S + "mb"]) * s[S + "nprev"] * (s[S + "ndu"] >= 1))
    cols.append(L(s["Wndu"]) * s["Wma"])
    return np.c_[tuple(cols)]


def _decimals(x):
    r = repr(float(x))
    if "e" in r:
        return 0
    return 0 if r.endswith(".0") else len(r.split(".")[1])


def roundness(x):
    """Trailing zeros of an integer value, minus the decimals of a fractional one (4,200,000 -> 5; 99.7 -> -1)."""
    x = abs(float(x))
    if x == 0 or not math.isfinite(x):
        return 0
    if x != int(x):
        return -_decimals(x)
    x, z = int(x), 0
    while x and x % 10 == 0:
        x //= 10; z += 1
    return z


def sig_digits(x):
    x = abs(float(x))
    if x == 0 or not math.isfinite(x):
        return 1
    s = ("%.10g" % x).replace(".", "").lstrip("0").rstrip("0") if x == int(x) else ("%.10g" % x).replace(".", "").lstrip("0")
    return max(1, len(s))


def digit_change(a, b):
    fa = lambda v: ("%.10g" % v)  # noqa: E731
    sa, sb = fa(a), fa(b)
    if len(sa) != len(sb):
        return False
    d = [i for i in range(len(sa)) if sa[i] != sb[i]]
    return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and sa[d[0]] == sb[d[1]] and sa[d[1]] == sb[d[0]])


BUCKETS = (0.1, 0.2, 0.25, 0.4, 0.5, 2.0, 2.5, 4.0, 5.0, 10.0)
_cols("lie_mult", ["has_ref", "ref_anchor", "bucket", "p10", "up", "down", "abslog", "digit", "round_diff",
                   "round_up", "sig1", "sig_digits"])


def _mult(world):
    s = seq(world)
    X = np.zeros((world.n_facts, 12))
    for n, f in enumerate(world.flat):
        if f.kind not in NUMK or f.op != "eq" or not isinstance(f.canon, float):
            continue
        v = f.canon
        try:
            raw = float(f.value)
        except (TypeError, ValueError):
            raw = v
        X[n, 10] = float(sig_digits(raw) == 1)
        X[n, 11] = min(sig_digits(raw), 8)
        ref, anc = (s["Aref"][n], 1.0) if not np.isnan(s["Aref"][n]) else (s["Wref"][n], 0.0)
        if np.isnan(ref) or ref == v:
            X[n, 0] = float(not np.isnan(ref)); X[n, 1] = anc * X[n, 0]
            continue
        X[n, 0], X[n, 1] = 1.0, anc
        if ref == 0 or v == 0:
            continue
        q = v / ref
        X[n, 2] = float(any(abs(q - b) <= 0.01 * b for b in BUCKETS))
        lq = math.log10(abs(q))
        X[n, 3] = float(abs(lq - round(lq)) < 0.005 and round(lq) != 0)
        X[n, 4], X[n, 5] = float(q > 1), float(q < 1)
        X[n, 6] = min(3.0, abs(lq))
        X[n, 7] = float(digit_change(v, ref))
        rd = max(-3, min(3, roundness(v) - roundness(ref)))
        X[n, 8] = rd
        X[n, 9] = float(rd > 0 and q > 1)
    return X


def lie_mult(world):
    """Numeric perturbation vs the reference value (latest anchor at/before the date, else the earliest after; votes
    when there is no anchor): listed multiple x0.1..x10 (1%), exact power of ten, direction, |log10 ratio|, single-
    digit change, roundness gain, rounder-and-larger (the hype signature), and value-only roundness."""
    return _cache(world, "mult", _mult)


_cols("round_up", ["round_up"])


def fp_col(p, c):
    return COLS[p].index(c)


def round_up(world):
    """Single column of lie_mult: the value is rounder than its reference value and larger (hype lie signature)."""
    return lie_mult(world)[:, [9]]


_cols("w_nds", ["W_nds"])


def w_nds(world):
    """Single column of lie_stale: distinct other pages (anchors + unsure + votes) contradicting the value since its
    last match before the date (the one F5 column that adds to F2's Chain, see F5/onf2.py)."""
    return lie_stale(world)[:, [fp_col("lie_stale", "W_nds")]]


_cols("lie_swap", ["swap_subj_A", "swap_attr_A", "swap_subj_W", "swap_attr_W", "own_seen_W", "small_value"])


def _swap(world):
    R = roles(world)
    by_attr, by_subj = defaultdict(list), defaultdict(list)
    for n, f in enumerate(world.flat):
        if f.kind == "boolean":
            continue
        i = world.frow[n]
        if R[i] == "F":
            continue
        tag = (f.kind, str(f.dim), str(f.canon), f.op)
        by_attr[(f.key[1],) + tag].append((f.key[0], world.page[i], R[i] == "T"))
        by_subj[(f.key[0],) + tag].append((f.key[1], world.page[i], R[i] == "T"))
    s = seq(world)
    X = np.zeros((world.n_facts, 6))
    for n, f in enumerate(world.flat):
        if f.kind == "boolean":
            continue
        p = world.page[world.frow[n]]
        tag = (f.kind, str(f.dim), str(f.canon), f.op)
        oa = [a for subj, pg, a in by_attr.get((f.key[1],) + tag, ()) if pg != p and subj != f.key[0]]
        os_ = [a for attr, pg, a in by_subj.get((f.key[0],) + tag, ()) if pg != p and attr != f.key[1]]
        own_A = s["Amb"][n] or s["Ama"][n]
        own_W = s["Wmb"][n] or s["Wma"][n]
        X[n, 0] = float(any(oa) and not own_A)
        X[n, 1] = float(any(os_) and not own_A)
        X[n, 2] = float(bool(oa) and not own_W)
        X[n, 3] = float(bool(os_) and not own_W)
        X[n, 4] = float(own_W)
        X[n, 5] = float(isinstance(f.canon, float) and abs(f.canon) <= 10)
    return X


def lie_swap(world):
    """Swap: the value is stated (anchor A / any obs W) for ANOTHER subject's same attribute, or for the same
    subject's other attribute (same kind and unit), and never for its own key."""
    return _cache(world, "swap", _swap)


_cols("lie_bool", ["is_bool", "bool_false", "bool_flip_A"])


def lie_bool(world):
    """Boolean flip: boolean fact, stated value False (negation), and mismatch with the nearest prior anchor."""
    s = seq(world)
    X = np.zeros((world.n_facts, 3))
    for n, f in enumerate(world.flat):
        if f.kind == "boolean":
            X[n, 0] = 1.0
            X[n, 1] = float(f.value in (False, "false", "False", 0))
            X[n, 2] = float(s["Anprev"][n] and not s["Amb"][n] and s["Ands"][n] >= 1)
    return X


_cols("lie_date", ["is_date", "date_after_row", "date_shift_log"])


def lie_date(world):
    """Date fact: the stated date lies after the row date (event not yet happened), and |shift| to the reference
    date anchor in log days (time-shifted dates: -31, -93, +3,653 days in practice)."""
    X = np.zeros((world.n_facts, 3))
    for n, f in enumerate(world.flat):
        if f.kind != "date" or f.lo is None:
            continue
        X[n, 0] = 1.0
        X[n, 1] = float(f.lo > world.date[world.frow[n]])
    # shift to the nearest anchor date value
    R = roles(world)
    for okey, obs in world.obs_typed.items():
        if okey[2] != "date":
            continue
        g = [world.fstart[i] + j for i, j in obs]
        for a in g:
            i = world.frow[a]; best = None
            for b in g:
                k = world.frow[b]
                if R[k] != "T" or world.page[k] == world.page[i]:
                    continue
                dd = abs(int(world.date[k]) - int(world.date[i]))
                if best is None or dd < best[0]:
                    best = (dd, world.flat[b])
            if best is not None and not world.flat[a].consistent(best[1]):
                X[a, 2] = math.log1p(abs(world.flat[a].lo - best[1].lo))
    return X


# ----------------------------------------------------------------- restatements
def _events(world):
    ev = set()
    for e in world.lexicon.get("events", []):
        ev.add(e if isinstance(e, str) else e.get("name"))
    return ev


PERIOD = re.compile(r"\b(Q[1-4]|20\d\d|results|report|survey|outage|launch|night|day)\b", re.I)
_cols("restate", ["event_subj", "period_subj", "later_than_all", "restate_word", "evt_later_p10", "ref_vote_p10"])


def restate(world):
    """Restatement handling: an event- or period-scoped subject (lexicon events, 'Q1 2026 Results') holds fixed
    values, so a later re-statement of an old quarter is not a stale or perturbed value. Columns let the model
    cancel the power-of-ten penalty when the row is a later statement about a closed period, or when the
    reference it differs from is only an unlabelled vote (the earlier, boastful statement may be the lie)."""
    ev = _events(world)
    M = lie_mult(world)
    s = seq(world)
    X = np.zeros((world.n_facts, 6))
    for n, f in enumerate(world.flat):
        i = world.frow[n]
        X[n, 0] = float(f.key[0] in ev)
        X[n, 1] = float(bool(PERIOD.search(f.key[0])))
        X[n, 2] = float(s["Wany"][n] and not s["Wma"][n] and s["Wnprev"][n])
        X[n, 3] = float(bool(re.search(r"\brestat|\brevised|\bcorrected|\bfinal\b", world.text[i], re.I)))
        X[n, 4] = X[n, 0] * X[n, 2] * M[n, 3]
        X[n, 5] = (1 - M[n, 1]) * M[n, 3]
    return X


_cols("restate2", ["retro_event", "retro_event_p10", "retro_gap_log"])


def restate2(world, min_gap=60):
    """Retrospective statement about a closed period: event-scoped subject and the row is dated >= 60 days after
    every other-page observation of its key (practice: 31 true / 3 false facts; p-455, p-466 restate Q1 2026).
    Also its interaction with the power-of-ten flag and the log gap."""
    ev = _events(world)
    M = lie_mult(world)
    X = np.zeros((world.n_facts, 3))
    for n, f in enumerate(world.flat):
        if f.key[0] not in ev:
            continue
        i = world.frow[n]
        od = [world.date[r] for r, _ in world.obs.get(f.key, ()) if world.page[r] != world.page[i]]
        if not od:
            continue
        gap = int(world.date[i] - max(od))
        if gap >= min_gap:
            X[n] = (1.0, M[n, 3], math.log1p(gap))
    return X


# ----------------------------------------------------------------- 2. source priors (text, page)
FP_S = re.compile(r"\b(I|I'm|I've|I'd|me|my|mine|myself)\b")
FP_P = re.compile(r"\b(we|We|our|Our|us|ours|We're|we're)\b")
SPEAKER = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z]+)?: ")
# generic hype lexicon, written a priori (superlatives and boasts), not read off the practice unsure rows
HYPE_G = re.compile(r"\b(best|record|ever|greatest|incredible|amazing|unmatched|unbeatable|world's|number one|nobody|no one|"
                    r"everyone|every one|more than any|legend\w*|genius|revolution\w*|insane|crushing|dominat\w*|"
                    r"perfect|unstoppable|historic|massive|huge|biggest|fastest)\b", re.I)
HEDGE_G = re.compile(r"\b(about|around|roughly|approximately|nearly|almost|may|might|could|would|should|expected|"
                     r"planned|plans?|reportedly|rumou?red|allegedly|apparently|supposedly|probably|likely|"
                     r"maybe|perhaps|if|beta|preview|pilot|soon|told|heard|claims?|says?|said)\b", re.I)
NEG = re.compile(r"\b(not|no|never|none|without|n't)\b", re.I)
# practice-tuned (hyp.py, designed on ALL practice rows including the hidden folds: optimistic)
JOKE_T = re.compile(r"(,| and| which| while| though| but)\s.*\b(I|me|my|we|our|nobody|no one|not one|every one|all humans|"
                    r"poetry|tired|personal best|vertical|impossible|coffee|for you|the rest|regrets?|greatness|friends|asked|told)\b")
UNDERCUT_T = re.compile(r"\b(not live|in the beta|beta|preview|pilot|starts today|questions go to|I have been told|told me|"
                        r"reportedly|rumou?r|may|might|if|would|could|planned|expected)\b", re.I)
DIGIT = re.compile(r"\d")
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
DATE_RX = [re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?(?: of)? (" + MONTHS + r"),? (\d{4})\b", re.I),
           re.compile(r"\b(" + MONTHS + r") (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})\b", re.I),
           re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")]


def _text_dates(t):
    import datetime as dt
    out = []
    ml = MONTHS.split("|")
    for k, rx in enumerate(DATE_RX):
        for m in rx.finditer(t):
            try:
                if k == 0:
                    d = dt.date(int(m.group(3)), ml.index(m.group(2).lower()) + 1, int(m.group(1)))
                elif k == 1:
                    d = dt.date(int(m.group(3)), ml.index(m.group(1).lower()) + 1, int(m.group(2)))
                else:
                    d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                out.append(d.toordinal())
            except ValueError:
                pass
    return out


def _names(world):
    nm = defaultdict(list)
    for s in world.lexicon.get("subjects", []):
        for a in [s["name"]] + list(s.get("aliases", [])):
            nm[s["name"]].append(a.casefold())
    for e in _events(world):
        nm[e].append(e.casefold())
    return nm


def _rowtext(world):
    """Row-level text flags (n x k)."""
    nm = _names(world)
    T = np.zeros((world.n, 16))
    for i, t in enumerate(world.text):
        tl = t.casefold()
        digs = [m.end() for m in DIGIT.finditer(t)]
        tail = t[digs[-1]:] if digs else ""
        subj = {f.key[0] for f in world.facts[i]}
        named = any(a and a in tl for s in subj for a in nm.get(s, [s.casefold()]))
        dates = _text_dates(t)
        D = int(world.date[i])
        T[i] = [bool(FP_S.search(t)), bool(FP_P.search(t)), bool(HYPE_G.search(t)), "!" in t, bool(SPEAKER.match(t)),
                bool(HEDGE_G.search(t)), bool(NEG.search(t)), math.log1p(len(tail.split())),
                bool(FP_S.search(tail) or FP_P.search(tail) or HYPE_G.search(tail)), not named,
                any(d > D for d in dates), bool(re.search(r"\btoday\b", t, re.I)) and any(d != D for d in dates),
                bool(JOKE_T.search(t)), bool(UNDERCUT_T.search(t)), math.log1p(len(t.split())),
                bool(re.search(r"\b(will|going to|next (week|month|year|quarter)|plans? to|set to|soon)\b", t, re.I))]
    return T


def rowtext(world):
    return _cache(world, "rowtext", _rowtext)


_cols("src_text", ["fp_sing", "fp_plur", "hype", "exclam", "speaker", "hedge", "neg", "tail_words", "tail_boast",
                   "subj_not_named", "future_date_text", "today_conflict", "words", "future_phrase"])


def src_text(world):
    """Row text, generic lexicons only: first person, hype words, exclamation, speaker tag, hedges, negation,
    words after the last digit, boast in that tail (generic joke tail), subject not named, a date in the text
    after the row date, 'today' with another date, length, future phrasing."""
    T = rowtext(world)
    return T[:, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15]][world.frow]


_cols("txt_tuned", ["joke_tail_tuned", "undercut_tuned"])


def txt_tuned(world):
    """hyp.py's practice-tuned joke-tail and undercutting regexes (designed on all of practice: OPTIMISTIC)."""
    return rowtext(world)[:, [12, 13]][world.frow]


_cols("src_page", ["page_size_log", "pos_rel", "is_first", "is_last", "pg_fp_share", "pg_hype_share",
                   "pg_social_any", "pg_social_share", "pg_nsubj_log", "pg_subj_share", "pg_tailboast_share"])


def _page(world):
    T = rowtext(world)
    social = (T[:, 0] + T[:, 2] + T[:, 3]) > 0
    P = np.zeros((world.n, 11))
    for p in range(world.n_pages):
        rows = np.flatnonzero(world.page == p)
        k = len(rows)
        subj = [f.key[0] for i in rows for f in world.facts[i]]
        for r, i in enumerate(rows):
            own = [f.key[0] for f in world.facts[i]]
            share = np.mean([subj.count(s) / max(1, len(subj)) for s in own]) if own else 0.0
            P[i] = [math.log(k), r / max(1, k - 1), r == 0, r == k - 1 and k > 1, T[rows, 0].mean(), T[rows, 2].mean(),
                    social[rows].any(), social[rows].mean(), math.log1p(len(set(subj))), share, T[rows, 8].mean()]
    return P


def src_page(world):
    """Page source prior: page size, relative position, first / last row, page share of first-person, hype and
    social rows, number of subjects on the page, the row subject's share of the page's facts."""
    return _cache(world, "page", _page)[world.frow]


def _rule_rows(world):
    """Per row, hard lie rules over its facts (anchors only, own page excluded): stale, both-sides mismatch,
    listed multiple, swap. Used for the page-level 'page already holds a detected lie' prior."""
    s = seq(world); M = lie_mult(world); S = lie_swap(world)
    st = s["Amb"] * (s["Ands"] >= 1)
    # both sides mismatch: has anchors before and after, no consistent one either side (the N-N pattern)
    nn = (s["Anprev"] > 0) & (s["Amb"] == 0) & (s["Ands"] >= 1) & (s["Ama"] == 0) & (s["Andu"] >= 1)
    mult = (M[:, 2] > 0) & (M[:, 1] > 0)
    sw = (S[:, 0] + S[:, 1]) > 0
    R = np.zeros((world.n, 4))
    for c, v in enumerate((st, nn, mult, sw)):
        np.maximum.at(R[:, c], world.frow, v.astype(float))
    return R


_cols("src_pagelie", ["pg_other_stale", "pg_other_nn", "pg_other_mult", "pg_other_swap", "pg_other_any"])


def src_pagelie(world):
    """Page already contains a detected lie: number of OTHER rows of the page where a hard rule fires (stale,
    both-sides mismatch, listed multiple, swap), and whether any does."""
    R = _cache(world, "rulerows", _rule_rows)
    tot = np.zeros((world.n_pages, 4))
    np.add.at(tot, world.page, R)
    O = tot[world.page] - R
    O = np.c_[O, (O.sum(1) > 0)]
    return np.log1p(O)[world.frow]


_cols("src_idblock", ["id_false_rate", "id_unsure_rate"])


def src_idblock(world, h=50.0, a=5.0):
    """GENERATOR-SPECIFIC: kernel-smoothed false and unsure rates of labelled rows near this row in file order
    (exp(-|di|/50)), own page excluded; practice ids p-1001..1100 are 46% false. Does not transfer by design."""
    lab = world.labelled
    y = np.array([lab_ == "false" for lab_ in world.label], float)
    u = np.array([lab_ == "unsure" for lab_ in world.label], float)
    base = y[lab].mean() if lab.any() else 0.15
    ub = u[lab].mean() if lab.any() else 0.02
    idx = np.flatnonzero(lab)
    out = np.zeros((world.n, 2))
    for i in range(world.n):
        lo, hi = np.searchsorted(idx, [i - 5 * h, i + 5 * h])
        j = idx[lo:hi]
        j = j[world.page[j] != world.page[i]]
        w = np.exp(-np.abs(j - i) / h)
        out[i] = ((w @ y[j] + a * base) / (w.sum() + a), (w @ u[j] + a * ub) / (w.sum() + a))
    return out[world.frow]


# ----------------------------------------------------------------- 3. unsure cues (timeline)
_cols("uns_tl", ["no_anchor_before", "no_anchor", "no_obs", "gap_obs", "gap_anchor", "n_anchor_log", "n_obs_log"])


def uns_tl(world):
    """Unsure timeline cues: no true anchor of the key at or before the date (practice: 28 of 39 unsure rows), no
    anchor at all, no other-page observation, log days to the nearest observation / anchor, evidence counts."""
    s = seq(world)
    return np.c_[1 - s["Anprev"], 1 - s["Aany"], 1 - s["Wany"], s["Wgap"], s["Agap"], np.log1p(s["Ann"]),
                 np.log1p(s["Wnn"])]


# ----------------------------------------------------------------- 4. priors per attribute and kind (out-of-fold)
_cols("prior", ["attr_false", "attr_unsure", "key_false", "kind_false", "attr_change_W", "key_nvals_W",
                "key_nvals_A", "attr_nkeys_log", "event_subj"])


def _prior(world, a=10.0):
    """Leave-own-page-out smoothed rates from labelled rows: per attribute, key, kind (row label of each fact).
    Change rates are label-free: share of the attribute's keys with >= 2 distinct stated values (all obs)."""
    lab = world.labelled
    y = np.array([lab_ == "false" for lab_ in world.label], float)
    u = np.array([lab_ == "unsure" for lab_ in world.label], float)
    base = y[lab].mean() if lab.any() else 0.15
    ub = u[lab].mean() if lab.any() else 0.02
    fl = lab[world.frow]; fy = y[world.frow]; fu = u[world.frow]; fp = world.page[world.frow]
    out = np.zeros((world.n_facts, 9))
    groups_ = {"attr": [f.key[1] for f in world.flat], "key": [f.key for f in world.flat], "kind": [f.kind for f in world.flat]}
    cols = {}
    for gname, keys in groups_.items():
        tot = defaultdict(lambda: np.zeros(3)); per = defaultdict(lambda: np.zeros(3))
        for n, k in enumerate(keys):
            if fl[n]:
                v = np.array([1.0, fy[n], fu[n]])
                tot[k] += v; per[(k, fp[n])] += v
        r = np.zeros((world.n_facts, 2))
        for n, k in enumerate(keys):
            c = tot[k] - per[(k, fp[n])] if k in tot else np.zeros(3)
            r[n] = ((c[1] + a * base) / (c[0] + a), (c[2] + a * ub) / (c[0] + a))
        cols[gname] = r
    out[:, 0], out[:, 1] = cols["attr"][:, 0], cols["attr"][:, 1]
    out[:, 2], out[:, 3] = cols["key"][:, 0], cols["kind"][:, 0]
    # label-free change rate per attribute
    vals = defaultdict(set)
    for f in world.flat:
        vals[f.okey].add(str(f.canon))
    akeys = defaultdict(list)
    for k, v in vals.items():
        akeys[k[1]].append(len(v) > 1)
    s = seq(world)
    ev = _events(world)
    for n, f in enumerate(world.flat):
        ch = akeys[f.key[1]]
        out[n, 4] = (sum(ch) + 1) / (len(ch) + 2)
        out[n, 5] = math.log1p(s["Wnv"][n]); out[n, 6] = math.log1p(s["Anv"][n])
        out[n, 7] = math.log1p(len(ch)); out[n, 8] = float(f.key[0] in ev)
    return out


def prior(world):
    """Per-attribute / key / kind lie and unsure rates (labelled rows of OTHER pages, Beta-smoothed a=10), label-free
    attribute change rate, distinct values of the key (all obs / anchors), number of keys of the attribute."""
    return _cache(world, "prior", _prior)


_cols("kind_oh", list(KINDS))


def kind_oh(world):
    """One-hot value kind (V9 feeds the kind as one ordinal column, which a linear model cannot use)."""
    X = np.zeros((world.n_facts, len(KINDS)))
    for n, f in enumerate(world.flat):
        X[n, KINDS.index(f.kind)] = 1.0
    return X


_cols("nulls", [f"n{k}" for k in range(10)])
NULL_SRC = [("lie_mult", "round_up"), ("lie_swap", "swap_subj_W"), ("lie_mult", "round_diff"), ("restate", "later_than_all"),
            ("lie_bool", "bool_false"), ("prior", "attr_change_W"), ("lie_mult", "bucket"), ("prior", "key_nvals_W"),
            ("src_pagelie", "pg_other_any"), ("lie_mult", "up")]


def nulls(world):
    """Selection-noise control: 10 columns, each a fixed random permutation (seed k) over facts of a real F5
    column, so its marginal distribution is real and its link to the label is destroyed. A forward step's gain
    is only credible if it clearly beats the best null candidate."""
    out = np.zeros((world.n_facts, 10))
    for k, (b, c) in enumerate(NULL_SRC):
        x = getattr(globals()[b](world), "__array__")()[:, COLS[b].index(c)]
        out[:, k] = x[np.random.RandomState(1000 + k).permutation(world.n_facts)]
    return out


PLUGINS = ["lie_stale", "lie_mult", "lie_swap", "lie_bool", "lie_date", "restate", "restate2", "src_text", "txt_tuned",
           "src_page", "src_pagelie", "src_idblock", "uns_tl", "prior", "kind_oh"]


def _selfcheck():
    assert roundness(4200000) == 5 and roundness(99.7) == -1 and roundness(0) == 0
    assert sig_digits(4200000) == 2 and sig_digits(99.7) == 3 and sig_digits(500000) == 1
    assert digit_change(1234, 1243) and digit_change(80, 30) and not digit_change(80, 800)
    assert _text_dates("beta starts today, 3 September 2025") == [__import__("datetime").date(2025, 9, 3).toordinal()]
    print("fp selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
