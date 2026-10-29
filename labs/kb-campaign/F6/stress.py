"""F6 stress and robustness battery for KB variants (wraps the harness worlds; never edits the harness).

  PY="$KBC/.venv/bin/python -I"; cd $KBC
  $PY F6/stress.py run --variant v9='{"model": ["lr", "hgb"]}' --variant always_true --jobs 2 --worker F6
  $PY F6/stress.py run --variant F3/mine.py:Best='{"a": 1}' --stress density,copies --base Sdev-jr --jobs 2
  $PY F6/stress.py run ... --remote F6-mytag --jobs 20 --worker F6-remote   # then: remote/remote.sh wait F6-mytag
  $PY F6/stress.py list [--stress ...]                                         # the cells of the battery
  $PY F6/stress.py summary [--worker F6,F6-remote] [--out F6/SUMMARY.md]       # degradation versus the clean track

One results line per (variant, params, cell) in $KBC_RESULTS_DIR/<worker>.jsonl, same fields as harness/run.py plus
stress, level, base_track, n_reps, subsets, stress_hash, stress_info; track = "F6/<stress>/<level>/<base>".
A cell = one stress at one level on one base track. Base tracks are harness tracks (P80, P10, S<w>-<m><f>); the
'labels' stress uses base 'P' (practice, all pages). Metrics: pooled over the folds/groups of one replicate (as P80),
then mean over replicates with metrics_std (as P10). Gold never reaches a variant: the stressed World is built from
the base World (public fields only); scenario builders that need gold (copied lies pick false rows) read it from the
Track held here, and copies carry no label and are never scored.

Stresses (see REPORT.md for the rationale):
  clean     identity on the base (reproduces harness/run.py exactly; the reference for every delta)
  density   keep 10/25/50/100% of the unlabelled rows: the unlabelled rows are split into K = 1/level random groups,
            each group is run with all labelled rows; every target is scored exactly once at every level (3 seeds)
  labels    practice with 5/10/20/50/80% of pages labelled (exp.py sampler, seeds 0..9; level 0.1 == P10)
  copies    copies.py scenarios: hlie/hctrl (tell-free: copies of hidden false rows / as many hidden true rows,
            3 copies each at +1/+7/+30 days on their own pages), lie/control/mixed (confounded, practice only)
  order     bundles (page order shuffled), rows (rows shuffled, pages recomputed from file order), single (one row per
            page), hid20 (page-size shift: hidden rows re-paged in file-order blocks of 20 rows, labelled pages kept)
  xforms    extractor forms: B/all (= the harness X track), B/hidden (gold on labelled rows, B on hidden rows);
            practice: worker D's page-grouped CV extraction cv/*, and its page-context variant cvpc/*
  noise     synthetic noise on gold forms: drop | subj (another subject with that attribute) | attr (another attribute
            of the same kind) | value (perturbed value) | op (comparison op lost) | mix, at a rate per fact, on
            hidden rows only or on all rows
  unseen    20% of keys held out: every labelled row stating a held-out key loses its label (stays as evidence,
            not scored); subsets heldout / seen (3 seeds)
"""
import argparse
import collections as C
import datetime as dt
import glob
import hashlib
import inspect
import json
import math
import multiprocessing as mp
import os
import random
import re
import resource
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KBC = os.path.dirname(HERE)
HARNESS = os.path.join(KBC, "harness")
for p in (HARNESS, KBC):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, HARNESS)  # harness first: api, metrics, world, variants

import numpy as np  # noqa: E402

import metrics as M  # noqa: E402
import world as W  # noqa: E402
import truth as A  # noqa: E402  (vendor_a, put on sys.path by world.py)
from api import check_prediction, resolve, run_variant  # noqa: E402

DATA = os.path.join(HERE, "data")
D_FORMS = {"cv": os.path.join(DATA, "forms_cv.jsonl"), "cvpc": os.path.join(DATA, "forms_cv_pagectx.jsonl")}

PRACTICE = ["P80", "P10"]
SUITE_J = ["Sdev-jr", "Sdev-jt", "Ssealed-jr", "Ssealed-jt"]
SUITE_N = ["Sdev-nr", "Sdev-nt"]
SUITE = SUITE_J + SUITE_N
NOISE_SUITE = ["Sdev-jr", "Sdev-jt", "Sdev-nr", "Sdev-nt"]
DENSITY = (0.1, 0.25, 0.5, 1.0)
RATIOS = (0.05, 0.1, 0.2, 0.5, 0.8)
TYPES = ("drop", "subj", "attr", "value", "op", "mix")
RATES = (0.05, 0.1, 0.2, 0.4)
SEEDS = {"density": 3, "order": 3, "unseen": 3, "labels": 10}
OFFSETS = (1, 7, 30)  # copies.py
COPY_SEED = 12345      # copies.py
SUBSET_KEYS = ("n", "points_per_row", "accuracy", "false_recall", "false_precision", "ece10", "coverage")


def battery(bases=None):
    """Cells (stress, level, base). Default bases: P80, P10, dev and sealed in j mode (t and r), dev in n mode (t and r);
    synthetic noise on P80, P10 and the four dev tracks. `bases` (any harness track names, plus 'P' for the label-ratio
    curve) replaces every default base list: practice-only stresses go to P80/P10, the rest to every base."""
    prac = [b for b in (bases or PRACTICE) if b in PRACTICE]
    suite = [b for b in bases if b[0] in "SX"] if bases else SUITE
    noise_suite = suite if bases else NOISE_SUITE
    every = prac + suite
    cells = [("clean", "-", b) for b in every]
    cells += [("density", str(lv), b) for b in suite for lv in DENSITY]
    if bases is None or "P" in bases:
        cells += [("labels", str(lv), "P") for lv in RATIOS]
    cells += [("copies", s, b) for b in every for s in ("hlie", "hctrl")]
    cells += [("copies", s, b) for b in prac for s in ("lie", "control", "mixed")]
    cells += [("order", m, b) for b in every for m in ("bundles", "rows", "single", "hid20")]
    cells += [("xforms", f"B/{sc}", b) for b in suite if b[0] == "S" for sc in ("all", "hidden")]
    cells += [("xforms", f"{f}/{sc}", b) for b in prac for f in ("cv", "cvpc") for sc in ("all", "hidden")]
    cells += [("noise", f"{t}@{r}/{sc}", b) for b in prac + noise_suite for t in TYPES for r in RATES
              for sc in ("hidden", "all")]
    cells += [("unseen", "0.2", b) for b in every]
    return cells


def seed_of(*parts):  # ponytail: seeded by the base name, so t and r cells of one world draw independently
    return int(hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:12], 16)


# ---------------------------------------------------------------- world construction
def make_world(base, tag, ids, text, date, interval, facts, labelled, label, page, stats=None):
    """A fresh harness World (pages compacted to 0..k-1, first-seen order). static_key gets the stress tag so
    label-free plugin caches keyed on it never mix a stressed world with its base."""
    page = np.asarray(page, np.int64)
    _, first, inv = np.unique(page, return_index=True, return_inverse=True)
    rank = np.empty(len(first), np.int64)
    rank[np.argsort(first, kind="stable")] = np.arange(len(first))
    page = rank[inv]
    lab = np.asarray(labelled, bool)
    lbl = [label[i] if lab[i] else None for i in range(len(ids))]
    st = dict(base.stats)
    st.update(stats or {})
    key = f"{base.static_key}|F6:{tag}"
    return W.World(base.name, key, list(ids), list(text), date, list(interval), facts, base.lexicon, lab, lbl, page, st)


def subset_world(w, rows, tag, facts=None, page=None, labelled=None, stats=None):
    """Rows `rows` of w (in that order) -> (World, pos) with pos[orig_row] = new row (or -1)."""
    rows = np.asarray(rows, np.int64)
    pos = np.full(w.n, -1, np.int64)
    pos[rows] = np.arange(len(rows))
    nw = make_world(w, tag, [w.ids[i] for i in rows], [w.text[i] for i in rows], w.date[rows],
                    [w.interval[i] for i in rows], facts if facts is not None else [w.facts[i] for i in rows],
                    w.labelled[rows] if labelled is None else labelled, w.label[rows],
                    w.page[rows] if page is None else page, stats)
    return nw, pos


def remap(gold, sc, pos):
    keep = pos[sc] >= 0
    return gold[keep], pos[sc][keep], keep


# ---------------------------------------------------------------- base tracks
def base_parts(base):
    """-> (list of (rep, world, gold, sc)), train). P80: one replicate pooled over 5 folds; P10: 10 replicates."""
    t = W.load_track(base)
    if base == "P10":
        return [(k, w, g, sc) for k, (w, g, sc) in enumerate(t.folds)], t.train
    return [(0, w, g, sc) for w, g, sc in t.folds], t.train


def full_gold(w, gold, sc):
    g = np.array(w.label, dtype=object)
    g[sc] = gold
    return g


# ---------------------------------------------------------------- stresses: each -> list of (rep, world, gold, sc, subsets)
def st_clean(base, level):
    parts, train = base_parts(base)
    return [(r, w, g, sc, {}) for r, w, g, sc in parts], train, {}


def st_density(base, level):
    lv = float(level)
    k = max(1, round(1 / lv))
    parts, train = base_parts(base)
    out = []
    for r, w, g, sc in parts:
        lab = np.where(w.labelled)[0]
        unl = np.where(~w.labelled)[0]
        for s in range(SEEDS["density"] if k > 1 else 1):
            perm = np.random.default_rng(seed_of("density", base, r, s)).permutation(unl)
            for q, grp in enumerate(np.array_split(perm, k)):
                nw, pos = subset_world(w, np.sort(np.r_[lab, grp]), f"density:{level}:{r}:{s}:{q}")
                g2, sc2, _ = remap(g, sc, pos)
                out.append((r * 100 + s, nw, g2, sc2, {}))
    return out, train, {"groups": k}


def st_labels(base, level):
    lv = float(level)
    base_w, gold = W.practice_full()[1:]
    out = []
    for s in range(SEEDS["labels"]):
        rng = random.Random(s)  # exp.py splits(): Random(seed).sample(range(NP), round(r NP))
        lab_p = np.zeros(base_w.n_pages, bool)
        lab_p[rng.sample(range(base_w.n_pages), max(1, round(lv * base_w.n_pages)))] = True
        lab = lab_p[base_w.page]
        sc = np.where(~lab)[0]
        out.append((s, base_w.with_labels(lab, gold), gold[sc], sc, {}))
    return out, None, {}


def add_copies(w, src, tag):
    """copies.py augment(): 3 copies of each source row (text, facts, interval kept), dates +1/+7/+30, own new page
    each, unlabelled. Appended after the original rows in source order."""
    ids, text, date, iv, facts = list(w.ids), list(w.text), list(w.date), list(w.interval), list(w.facts)
    page = list(w.page)
    p = w.n_pages
    for i in src:
        for d in OFFSETS:
            ids.append(f"cp{d}-{w.ids[i]}"); text.append(w.text[i]); date.append(int(w.date[i]) + d)
            iv.append(w.interval[i]); facts.append(w.facts[i]); page.append(p)
            p += 1
    n0 = w.n
    labelled = np.r_[w.labelled, np.zeros(len(ids) - n0, bool)]
    label = np.r_[w.label, np.full(len(ids) - n0, None, dtype=object)]
    nw = make_world(w, tag, ids, text, np.asarray(date, np.int64), iv, facts, labelled, label, page,
                    {"copies": len(ids) - n0})
    return nw


def st_copies(base, scen):
    parts, train = base_parts(base)
    out = []
    n_src = []
    for r, w, g, sc in parts:
        gf = full_gold(w, g, sc)
        order = range(w.n)
        if scen in ("hlie", "hctrl"):  # tell-free: only rows the variant does not see labelled (the scored rows)
            hid = set(sc.tolist())
            hf = [i for i in order if i in hid and gf[i] == "false"]
            src = hf if scen == "hlie" else random.Random(COPY_SEED).sample(
                [i for i in order if i in hid and gf[i] == "true"], len(hf))
        else:  # confounded scenarios, built on every row of the world as in copies.py
            fl = [i for i in order if gf[i] == "false"]
            tr = [i for i in order if gf[i] == "true"]
            if scen == "lie":
                src = fl
            elif scen == "control":
                src = random.Random(COPY_SEED).sample(tr, len(fl))
            elif scen == "mixed":
                rng = random.Random(COPY_SEED); h = len(fl) // 2
                src = rng.sample(fl, h) + rng.sample(tr, h)
                rng.shuffle(src)
            else:
                raise ValueError(scen)
        n_src.append(len(src))
        nw = add_copies(w, src, f"copies:{scen}:{r}:{len(n_src)}")
        copied = np.isin(sc, src)
        out.append((r, nw, g, sc, {"copied": copied, "not_copied": ~copied}))
    return out, train, {"copy_sources": n_src}


def st_order(base, mode):
    parts, train = base_parts(base)
    out = []
    for r, w, g, sc in parts:
        for s in range(SEEDS["order"] if mode in ("bundles", "rows") else 1):
            rng = np.random.default_rng(seed_of("order", mode, base, r, s))
            tag = f"order:{mode}:{r}:{s}"
            if mode == "single":
                nw, pos = subset_world(w, np.arange(w.n), tag, page=np.arange(w.n))
            elif mode == "bundles":
                pages = rng.permutation(w.n_pages)
                rows = np.concatenate([np.where(w.page == p)[0] for p in pages])
                nw, pos = subset_world(w, rows, tag)
            elif mode == "hid20":  # page-size shift: hidden rows re-paged in file-order blocks of 20, labelled pages kept
                page = w.page.copy()
                hid = np.where(~w.labelled)[0]
                page[hid] = w.n_pages + np.arange(len(hid)) // 20
                nw, pos = subset_world(w, np.arange(w.n), tag, page=page)
            elif mode == "rows":
                rows = rng.permutation(w.n)
                nw, pos = subset_world(w, rows, tag, page=W.pages_of(w.date[rows], w.labelled[rows]))
            else:
                raise ValueError(mode)
            g2, sc2, _ = remap(g, sc, pos)
            out.append((r * 100 + s, nw, g2, sc2, {}))
    return out, train, {}


def fact_sig(fs):
    return sorted((f.key, f.kind, f.op, repr(f.canon)) for f in fs)


def practice_forms_world(path):
    """Practice World with worker D's extracted forms (ids p-N, same row order as world._practice)."""
    _, base, gold = W.practice_full()
    lex = base.lexicon
    alias, names = W.exp_alias(lex), A.alias_map(lex)
    recs = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            rec = json.loads(line)
            recs.setdefault(str(rec["id"]), rec)
    drops = C.Counter()
    facts = [W.parse_facts((recs.get(i) or {}).get("assertions"), alias, names, drops) for i in base.ids]
    return facts, base, gold


def st_xforms(base, level):
    src, scope = level.split("/")
    parts, train = base_parts(base)
    out = []
    if base in PRACTICE:
        xf, pbase, _ = practice_forms_world(D_FORMS[src])
        own_ok = np.array([fact_sig(a) == fact_sig(b) for a, b in zip(xf, pbase.facts)])
        for r, w, g, sc in parts:
            facts = [w.facts[i] if (scope == "hidden" and w.labelled[i]) else xf[i] for i in range(w.n)]
            nw, _ = subset_world(w, np.arange(w.n), f"xforms:{level}:{r}", facts=facts)
            out.append((r, nw, g, sc, {"own_exact": own_ok[sc], "own_wrong": ~own_ok[sc]}))
        return out, train, {"rows_exact": float(own_ok.mean())}
    xparts, _ = base_parts("X" + base[1:])
    for (r, w, g, sc), (_, xw, _, xsc) in zip(parts, xparts):
        assert w.ids == xw.ids and np.array_equal(sc, xsc), "S and X worlds must align row by row"
        own_ok = np.array([fact_sig(a) == fact_sig(b) for a, b in zip(xw.facts, w.facts)])
        if scope == "all":
            nw = xw  # exactly the harness X track
        else:
            use_s = w.labelled
            nw, _ = subset_world(w, np.arange(w.n), f"xforms:{level}:{r}",
                                 facts=[w.facts[i] if use_s[i] else xw.facts[i] for i in range(w.n)])
            nw.interval = [w.interval[i] if use_s[i] else xw.interval[i] for i in range(w.n)]
        out.append((r, nw, g, sc, {"own_exact": own_ok[sc], "own_wrong": ~own_ok[sc]}))
    return out, train, {"rows_exact_scored": float(own_ok[sc].mean())}


class Noise:
    """Synthetic normalization errors on stated facts. Uses only the world's public facts and lexicon."""

    def __init__(self, w):
        self.alias, self.names = W.exp_alias(w.lexicon), A.alias_map(w.lexicon)
        subj_by_attr, attr_sk, attr_k = C.defaultdict(set), C.defaultdict(set), C.defaultdict(set)
        vals, kvals = C.defaultdict(dict), C.defaultdict(dict)
        for f in w.flat:
            s, a = f.key
            kd = (f.kind, repr(f.dim))
            subj_by_attr[a].add(s); attr_sk[(s, kd)].add(a); attr_k[kd].add(a)
            if f.kind in ("name", "version"):
                vals[f.okey].setdefault(repr(f.canon), f.raw["value"])
                kvals[f.kind].setdefault(repr(f.canon), f.raw["value"])
        srt = lambda d: {k: sorted(v, key=str) for k, v in d.items()}  # noqa: E731
        self.subj_by_attr, self.attr_sk, self.attr_k = srt(subj_by_attr), srt(attr_sk), srt(attr_k)
        self.vals = {k: sorted(v.items()) for k, v in vals.items()}
        self.kvals = {k: sorted(v.items()) for k, v in kvals.items()}
        self.subjects = sorted({s["name"] for s in w.lexicon["subjects"]})

    def fact(self, s, a, raw):
        try:
            return W.Fact({"subject": s, "attribute": a, "value": raw}, self.alias, self.names)
        except Exception:
            return None

    @staticmethod
    def pick(rng, xs):
        return xs[rng.randrange(len(xs))] if xs else None

    def value(self, f, raw, rng):
        x, k = raw.get("value"), f.kind
        try:
            if k == "boolean":
                return not x
            if k in ("quantity", "duration", "money", "percent"):
                y = x * rng.choice((0.5, 0.75, 1.25, 1.5, 2.0))
                y = int(round(y)) if isinstance(x, int) else round(y, 4)
                return y if y != x else x + 1
            if k == "date":
                p = str(x).split("-")
                if len(p) == 3:
                    d = dt.date.fromisoformat(str(x)) + dt.timedelta(days=rng.choice((-1, 1)) * rng.randint(1, 60))
                    return d.isoformat()
                if len(p) == 2:
                    m = int(p[0]) * 12 + int(p[1]) - 1 + rng.choice((-1, 1)) * rng.randint(1, 3)
                    return f"{m // 12:04d}-{m % 12 + 1:02d}"
                return str(int(p[0]) + rng.choice((-1, 1)))
            if k in ("name", "version"):
                c = repr(f.canon)
                alt = [v for cc, v in self.vals.get(f.okey, ()) if cc != c] or \
                      [v for cc, v in self.kvals.get(k, ()) if cc != c]
                if alt:
                    return self.pick(rng, alt)
                if k == "version":
                    m = list(re.finditer(r"\d+", str(x)))
                    if m:
                        g = m[-1]
                        return str(x)[:g.start()] + str(int(g.group()) + 1) + str(x)[g.end():]
        except (TypeError, ValueError, OverflowError):
            return None
        return None

    def perturb(self, f, typ, rng):
        """-> list of replacement facts ([] = dropped) or None if the error type does not apply to f."""
        s, a = f.key
        raw = dict(f.raw)
        if typ == "drop":
            return []
        if typ == "subj":
            s = self.pick(rng, [x for x in self.subj_by_attr.get(a, ()) if x != s]) or \
                self.pick(rng, [x for x in self.subjects if x != s])
        elif typ == "attr":
            kd = (f.kind, repr(f.dim))
            a = self.pick(rng, [x for x in self.attr_sk.get((s, kd), ()) if x != a]) or \
                self.pick(rng, [x for x in self.attr_k.get(kd, ()) if x != a])
        elif typ == "value":
            v = self.value(f, raw, rng)
            if v is None:
                return None
            raw["value"] = v
        elif typ == "op":
            if f.op == "eq":
                return None
            raw.pop("op", None)
        if s is None or a is None:
            return None
        nf = self.fact(s, a, raw)
        return None if nf is None else [nf]

    def apply(self, facts, rows, typ, rate, rng):
        """Perturb each fact of the given rows with probability rate. 'op' acts on facts with a comparison op only
        (rate = share of those); 'mix' draws one applicable type per selected fact."""
        out = list(facts)
        hit = np.zeros(len(facts), bool)
        n_sel = 0
        for i in rows:
            new, changed = [], False
            for f in facts[i]:
                if typ == "op" and f.op == "eq":
                    new.append(f); continue
                if rng.random() >= rate:
                    new.append(f); continue
                n_sel += 1
                types = [typ] if typ != "mix" else rng.sample(("drop", "subj", "attr", "value", "op"), 5)
                rep = None
                for t in types:
                    rep = self.perturb(f, t, rng)
                    if rep is not None:
                        break
                if rep is None:
                    new.append(f); continue
                new.extend(rep); changed = True
            if changed:
                out[i] = new
                hit[i] = True
        return out, hit, n_sel


def st_noise(base, level):
    m = re.fullmatch(r"(\w+)@([\d.]+)/(hidden|all)", level)
    typ, rate, scope = m.group(1), float(m.group(2)), m.group(3)
    assert typ in TYPES, typ
    parts, train = base_parts(base)
    out, nsel, nrow = [], [], []
    noise = None
    for r, w, g, sc in parts:
        noise = noise or Noise(w)  # label-free context, identical for every fold of the base
        rows = np.where(~w.labelled)[0] if scope == "hidden" else np.arange(w.n)
        rng = random.Random(seed_of("noise", level, base, r))
        facts, hit, k = noise.apply(w.facts, rows, typ, rate, rng)
        nsel.append(k); nrow.append(int(hit.sum()))
        nw, _ = subset_world(w, np.arange(w.n), f"noise:{level}:{r}", facts=facts)
        out.append((r, nw, g, sc, {"own_noisy": hit[sc], "own_clean": ~hit[sc]}))
    return out, train, {"facts_selected": nsel, "rows_changed": nrow}


def st_unseen(base, level):
    frac = float(level)
    parts, train = base_parts(base)
    out = []
    for r, w, g, sc in parts:
        keys = sorted({f.key for f in w.flat}, key=repr)
        for s in range(SEEDS["unseen"]):
            held = set(random.Random(seed_of("unseen", base, s)).sample(keys, round(frac * len(keys))))
            has = np.array([any(f.key in held for f in fs) for fs in w.facts])
            nw = w.with_labels(w.labelled & ~has, w.label)
            out.append((r * 100 + s, nw, g, sc, {"heldout": has[sc], "seen": ~has[sc]}))
    return out, train, {"keys": len(keys)}


STRESSES = {"clean": st_clean, "density": st_density, "labels": st_labels, "copies": st_copies, "order": st_order,
            "xforms": st_xforms, "noise": st_noise, "unseen": st_unseen}


def build(cell):
    stress, level, base = cell
    return STRESSES[stress](base, level)


# ---------------------------------------------------------------- jobs
def peak_rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / 2**20 if sys.platform == "darwin" else r / 1024, 1)


def file_hash(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(open(p, "rb").read())
    return h.hexdigest()[:12]


def aggregate(chunks):
    """chunks: rep -> list of (gold, pred, conf). Pooled within a replicate, mean (+ std) over replicates."""
    per = []
    for rep in sorted(chunks):
        g = np.concatenate([c[0] for c in chunks[rep]])
        if len(g) == 0:
            continue
        per.append(M.compute(g, np.concatenate([c[1] for c in chunks[rep]]), np.concatenate([c[2] for c in chunks[rep]])))
    if not per:
        return None, None
    if len(per) == 1:
        return per[0], None
    return M.mean_std(per)


def job(a):
    spec, params, cell, worker = a
    t0 = time.perf_counter()
    parts, train, info = build(cell)
    build_s = time.perf_counter() - t0
    cls, src = resolve(spec, "Variant")
    run_s, chosen, lowc = 0.0, [], [0, 0, 1.0]  # decided predictions with conf < 0.5, decided total, min conf
    main, subs = C.defaultdict(list), C.defaultdict(lambda: C.defaultdict(list))
    for rep, w, gold, sc, subsets in parts:
        v = cls(**params)
        t1 = time.perf_counter()
        p = check_prediction(w, run_variant(v, w, train))
        run_s += time.perf_counter() - t1
        if getattr(v, "chosen", None):
            chosen.append([list(c) for c in v.chosen])
        pr, cf = p.labels[sc], p.conf[sc]
        dec = pr != "unsure"
        lowc[0] += int((cf[dec] < 0.5).sum()); lowc[1] += int(dec.sum())
        lowc[2] = min(lowc[2], float(np.nanmin(cf[dec]))) if dec.any() else lowc[2]
        main[rep].append((gold, pr, cf))
        for name, mask in subsets.items():
            subs[name][rep].append((gold[mask], pr[mask], cf[mask]))
    m, sd = aggregate(main)
    stress, level, base = cell
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "worker": worker, "variant": spec, "params": params,
           "track": f"F6/{stress}/{level}/{base}", "stress": stress, "level": level, "base_track": base,
           "n_scored": int(sum(len(c[0]) for cs in main.values() for c in cs)), "n_reps": len(main),
           "n_parts": len(parts), "metrics": m,
           # final outputs need confidence in [0.5, 1]: decided predictions on the scored rows with confidence below 0.5
           "conf_below_half": {"n": lowc[0], "share": lowc[0] / lowc[1] if lowc[1] else 0.0, "min_conf": lowc[2]}}
    if sd:
        rec["metrics_std"] = sd
    rec["subsets"] = {k: {q: (aggregate(v)[0] or {}).get(q) for q in SUBSET_KEYS} for k, v in subs.items()}
    plug = [resolve(s, "features")[1] for s in params.get("extra_features", ())]
    rec.update(runtime_s=round(run_s, 3), load_s=round(build_s, 3), peak_rss_mb=peak_rss_mb(),
               src_hash=file_hash([src] + plug), stress_hash=file_hash([os.path.abspath(__file__)]),
               host=socket.gethostname(), stress_info=info, world_stats=parts[0][1].stats)
    if chosen:
        rec["chosen"] = chosen[:12]
    return rec


def safe_job(a):
    try:
        return job(a)
    except Exception as e:  # one broken cell (e.g. refit on a single-class world) must not kill the battery
        import traceback
        spec, params, (stress, level, base), worker = a
        return {"ts": dt.datetime.now().isoformat(timespec="seconds"), "worker": worker, "variant": spec,
                "params": params, "track": f"F6/{stress}/{level}/{base}", "stress": stress, "level": level,
                "base_track": base, "metrics": None, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(),
                "host": socket.gethostname()}


def expand(grid):
    if grid is None:
        return [{}]
    if isinstance(grid, list):
        return [dict(g) for g in grid]
    keys = sorted(grid)
    vals = [v if isinstance(v, list) else [v] for v in (grid[k] for k in keys)]
    import itertools
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def select_cells(a):
    cells = battery(a.base.split(",") if a.base else None)
    if a.stress:
        keep = set(a.stress.split(","))
        cells = [c for c in cells if c[0] in keep]
    if a.level:
        rx = re.compile(a.level)
        cells = [c for c in cells if rx.search(c[1])]
    if a.only:
        rx = re.compile(a.only)
        cells = [c for c in cells if rx.search(f"F6/{c[0]}/{c[1]}/{c[2]}")]
    return cells


def cmd_run(a):
    if a.remote:
        return remote(a)
    cells = select_cells(a)
    jobs = []
    for v in a.variant:
        spec, _, grid = v.partition("=")
        for params in expand(json.loads(grid) if grid else None):
            jobs += [(spec, params, c, a.worker) for c in cells]
    # biggest first so the pool tail is short
    cost = {"density": 3, "noise": 1, "copies": 2, "order": 3, "unseen": 3, "xforms": 1, "labels": 2, "clean": 1}
    jobs.sort(key=lambda j: -(cost[j[2][0]] * (10 if j[2][2] == "P10" else 1) + (5 if "hgb" in json.dumps(j[1]) else 0)))
    if a.dry:
        for j in jobs:
            print(j)
        print(len(jobs), "jobs")
        return 0
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(var, "1")
    os.makedirs(W.RESULTS_DIR, exist_ok=True)
    out = os.path.join(W.RESULTS_DIR, f"{a.worker}.jsonl")
    err = os.path.join(W.RESULTS_DIR, f"{a.worker}.errors.jsonl")
    fails = 0
    t0 = time.time()
    fd = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    with mp.get_context("spawn").Pool(max(1, min(a.jobs, len(jobs))), maxtasksperchild=1) as pool:
        for k, rec in enumerate(pool.imap_unordered(safe_job, jobs), 1):
            if "error" in rec:  # recorded as a results line (metrics null, error field) and in the errors file
                fails += 1
                print(f"[{k}/{len(jobs)}] FAILED {rec['variant']} {json.dumps(rec['params'])} {rec['track']}: "
                      f"{rec['error']}", file=sys.stderr, flush=True)
                with open(err, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                os.write(fd, (json.dumps({k2: v for k2, v in rec.items() if k2 != "trace"}) + "\n").encode())
                continue
            os.write(fd, (json.dumps(rec) + "\n").encode())
            mm = rec["metrics"]
            print(f"[{k}/{len(jobs)} {time.time() - t0:.0f}s] {rec['variant']} {json.dumps(rec['params'])} {rec['track']}: "
                  f"pts={mm['points_per_row']:.4f} acc={mm['accuracy']:.4f} fr={mm['false_recall']} "
                  f"conf<0.5={rec['conf_below_half']['n']} run={rec['runtime_s']:.1f}s build={rec['load_s']:.1f}s "
                  f"rss={rec['peak_rss_mb']}MB", flush=True)
    print(f"{len(jobs) - fails}/{len(jobs)} jobs ok, {fails} recorded as error lines -> {out}")
    return 0  # failures are results (error lines); the battery itself succeeded


def remote(a):
    """Sync, then launch this command on the box through remote.sh exec + F6/rlaunch.sh (same caps, tmux, logs and
    exit files as remote.sh run, so `remote.sh wait <tag>` and `remote.sh status` work)."""
    rs = os.path.join(KBC, "remote", "remote.sh")
    argv = [x for x in sys.argv[1:]]
    i = argv.index("--remote")
    del argv[i:i + 2]
    subprocess.run([rs, "sync"], check=True)
    while True:
        rc = subprocess.run([rs, "exec", "--", "bash", "F6/rlaunch.sh", a.remote, str(a.jobs)] + argv).returncode
        if rc != 3:
            return rc
        print(f"[{time.strftime('%T')}] box busy, retry in 30 s", file=sys.stderr, flush=True)
        time.sleep(30)


# ---------------------------------------------------------------- summary
ALIASES = {("always_true", "{}"): "always_true", ("v5", "{}"): "V5", ("v9", '{"model": "lr"}'): "V9-LR",
           ("v9", '{"model": "hgb"}'): "V9-HGB", ("engines", '{"engine": "interval"}'): "interval",
           ("engines", '{"engine": "point"}'): "point", ("v9", '{"model": "lr", "select": "arena"}'): "V9-LR-arena",
           ("v9", '{"model": "hgb", "select": "arena"}'): "V9-HGB-arena",
           ("F2/f2var.py:Chain", '{"engine": "viterbi", "eps_a": 0.002, "pi_o": 2, "vote_lr": 12}'): "F2-chain",
           ("v9", '{"drop_features": [11, 12, 13, 14], "extra_features": ["v12:mmr"], "selftrain": 1}'): "V12mmr-replace"}


def vlabel(r):
    p = json.dumps(r["params"], sort_keys=True)
    return ALIASES.get((r["variant"], p), f"{r['variant']} {p}" if r["params"] else r["variant"])


def load_results(workers):
    recs = {}
    files = [os.path.join(W.RESULTS_DIR, f"{w}.jsonl") for w in workers] if workers else \
        [p for p in glob.glob(os.path.join(W.RESULTS_DIR, "*.jsonl")) if not p.endswith(".errors.jsonl")]
    for p in files:
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if "stress" not in r:
                continue
            k = (vlabel(r), r["track"])
            if k not in recs or r["ts"] >= recs[k]["ts"]:
                recs[k] = r
    return recs


def fmt(x, nd=3):
    return "" if x is None else f"{x:.{nd}f}"


def cmd_summary(a):
    recs = load_results(a.worker.split(",") if a.worker else None)
    metric = a.metric
    variants = sorted({k[0] for k in recs}, key=lambda v: ((list(ALIASES.values()) + [v]).index(v), v))
    if a.variants:
        want = a.variants.split(",")
        variants = [v for v in variants if v in want]
    cells = sorted({(r["stress"], r["level"], r["base_track"]) for r in recs.values()})
    order = {c: i for i, c in enumerate(battery())}
    cells.sort(key=lambda c: order.get(c, 10**6))
    clean = {(k[0], r["base_track"]): r for k, r in recs.items() if r["stress"] == "clean" and r.get("metrics")}
    L = [f"# F6 stress summary ({metric}; delta = stressed minus the clean track of the same base, same variant)", "",
         f"Generated {dt.datetime.now().isoformat(timespec='seconds')} from {len(recs)} results lines "
         f"(workers: {a.worker or 'all'}). Labels stress: the curve itself, no delta; 0.1 == P10.", ""]
    lab = "| stress | level | base | " + " | ".join(variants) + " |"
    sep = "|" + "---|" * (3 + len(variants))
    profile = C.defaultdict(lambda: C.defaultdict(list))
    for stress in [s for s in STRESSES if any(c[0] == s for c in cells)]:
        L += [f"## {stress}", "", lab, sep]
        for c in [c for c in cells if c[0] == stress]:
            row = [c[0], c[1], c[2]]
            for v in variants:
                r = recs.get((v, f"F6/{c[0]}/{c[1]}/{c[2]}"))
                if r is None:
                    row.append(""); continue
                if not r.get("metrics"):
                    row.append("ERR"); continue
                x = r["metrics"][metric]
                ref = clean.get((v, c[2]))
                if ref is not None and stress not in ("clean", "labels") and x is not None and ref["metrics"][metric] is not None:
                    d = x - ref["metrics"][metric]
                    profile[v][stress].append(d)
                    row.append(f"{fmt(x)} ({d:+.3f})")
                else:
                    row.append(fmt(x))
            L.append("| " + " | ".join(row) + " |")
        L.append("")
    nd = C.defaultdict(list)  # noise digest: mean delta over rates and bases per (type, scope)
    for c in cells:
        if c[0] != "noise":
            continue
        typ, rest = c[1].split("@"); scope = rest.split("/")[1]
        for v in variants:
            r, ref = recs.get((v, f"F6/{c[0]}/{c[1]}/{c[2]}")), clean.get((v, c[2]))
            if r and r.get("metrics") and ref and r["metrics"][metric] is not None and ref["metrics"][metric] is not None:
                nd[(typ, scope, v)].append(r["metrics"][metric] - ref["metrics"][metric])
    if nd:
        L += ["## Noise digest (mean delta over the 4 rates and every noise base)", "",
              "| type | scope | " + " | ".join(variants) + " |", "|" + "---|" * (2 + len(variants))]
        for typ in TYPES:
            for scope in ("hidden", "all"):
                L.append("| " + " | ".join([typ, scope] + [f"{np.mean(nd[(typ, scope, v)]):+.3f}" if nd.get((typ, scope, v))
                                                             else "" for v in variants]) + " |")
        L.append("")
    L += ["## Robustness profile (mean / worst delta per stress family)", "",
          "| variant | " + " | ".join(s for s in STRESSES if s not in ("clean", "labels")) + " |",
          "|" + "---|" * (1 + len(STRESSES) - 2)]
    for v in variants:
        row = [v]
        for s in STRESSES:
            if s in ("clean", "labels"):
                continue
            d = profile[v].get(s)
            worst = (max if metric == "ece10" else min)(d) if d else None
            row.append(f"{np.mean(d):+.3f} / {worst:+.3f}" if d else "")
        L.append("| " + " | ".join(row) + " |")
    # transfer (t: fitted on practice) versus refit (r: fitted on the world's own labels), same world and mode
    gap = C.defaultdict(lambda: C.defaultdict(list))
    for (v, tr), r in recs.items():
        b = r["base_track"]
        if not r.get("metrics") or not re.fullmatch(r"[SX]\w+-[jn]t", b):
            continue
        o = recs.get((v, f"F6/{r['stress']}/{r['level']}/{b[:-1]}r"))
        if o and o.get("metrics") and r["metrics"][metric] is not None and o["metrics"][metric] is not None:
            gap[v][r["stress"] if r["stress"] != "clean" else "clean " + b[:-1]].append(r["metrics"][metric] - o["metrics"][metric])
    cols = sorted({c for v in gap for c in gap[v]}, key=lambda c: (not c.startswith("clean"), c))
    if cols:
        L += ["", "## Transfer minus refit (t - r, same world, mode and stress cell; mean over cells)", "",
              "| variant | " + " | ".join(cols) + " |", "|" + "---|" * (1 + len(cols))]
        for v in variants:
            L.append("| " + " | ".join([v] + [f"{np.mean(gap[v][c]):+.3f}" if gap[v].get(c) else "" for c in cols]) + " |")
    low = [(k[0], k[1], r["conf_below_half"]["n"]) for k, r in recs.items() if r.get("conf_below_half", {}).get("n")]
    L += ["", f"## Confidence check: decided predictions with confidence below 0.5 ({len(low)} cells affected)", ""]
    for v in variants:
        vv = [x for x in low if x[0] == v]
        if vv:
            L.append(f"- {v}: {len(vv)} cells, {sum(x[2] for x in vv)} predictions (e.g. {vv[0][1]})")
    errs = [(k[0], k[1], r["error"]) for k, r in recs.items() if r.get("error")]
    if errs:
        L += ["", f"## Failed cells ({len(errs)})", ""] + [f"- {v} {t}: {e[:160]}" for v, t, e in sorted(errs)]
    L += ["", "## Subsets (points per row on the scored rows of each subset)", "",
          "| stress | level | base | subset | " + " | ".join(variants) + " |", "|" + "---|" * (4 + len(variants))]
    for c in cells:
        names = sorted({n for v in variants for n in (recs.get((v, f"F6/{c[0]}/{c[1]}/{c[2]}")) or {}).get("subsets", {})})
        for n in names:
            row = [c[0], c[1], c[2], n]
            for v in variants:
                r = recs.get((v, f"F6/{c[0]}/{c[1]}/{c[2]}"))
                s = (r or {}).get("subsets", {}).get(n) or {}
                row.append(f"{fmt(s.get('points_per_row'))} (n={s.get('n'):.0f})" if s.get("n") else "")
            L.append("| " + " | ".join(row) + " |")
    txt = "\n".join(L) + "\n"
    if a.out:
        with open(a.out, "w") as f:
            f.write(txt)
    print(txt)
    return 0


def cmd_list(a):
    for c in select_cells(a):
        print(*c)
    print(len(select_cells(a)), "cells")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "list"):
        s = sub.add_parser(name)
        s.add_argument("--stress", help="comma list of stresses (default: all)")
        s.add_argument("--base", help="comma list of base tracks (default: all)")
        s.add_argument("--level", help="regex on the level string")
        s.add_argument("--only", help="regex on the full cell track name F6/<stress>/<level>/<base>")
        if name == "run":
            s.add_argument("--variant", action="append", required=True, metavar="SPEC[=GRID_JSON]")
            s.add_argument("--jobs", type=int, default=2)
            s.add_argument("--worker", default="F6")
            s.add_argument("--dry", action="store_true")
            s.add_argument("--remote", metavar="TAG", help="launch on the box (remote.sh); then remote.sh wait TAG")
    s = sub.add_parser("summary")
    s.add_argument("--worker", help="comma list of result files (worker names); default: every file")
    s.add_argument("--metric", default="points_per_row")
    s.add_argument("--variants", help="comma list of variant labels to show")
    s.add_argument("--out")
    a = ap.parse_args()
    os.chdir(KBC)  # variant paths such as F3/x.py resolve the same on the Mac and on the box
    sys.exit({"run": cmd_run, "list": cmd_list, "summary": cmd_summary}[a.cmd](a))


if __name__ == "__main__":
    main()
