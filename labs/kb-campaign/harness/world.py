"""World, Fact, data loaders and track definitions for the KB variant campaign (see API.md).

A World holds only public information: row text, public date, inferred page, STATED facts, and labels
for the labelled rows. Gold labels of scored rows live in the Track objects held by run.py, never here.
"""
import collections as C
import csv
import datetime as dt
import hashlib
import json
import os
import pickle
import random
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor_a"))
import truth as A  # noqa: E402  vendored copy of /tmp/veridyct-evalsuite/A/truth.py (unchanged)

ROOT = os.environ.get("KBC_ROOT", os.path.dirname(HERE))
PRACTICE_DIR = os.environ.get("KBC_PRACTICE_DIR", os.path.join(ROOT, "data"))
SUITE_DIR = os.path.expanduser(os.environ.get("KBC_SUITE_DIR", "~/Downloads/evaluation-data"))
EVALSUITE_DIR = os.environ.get("KBC_EVALSUITE_DIR", "/tmp/veridyct-evalsuite")
RESULTS_DIR = os.environ.get("KBC_RESULTS_DIR", os.path.join(ROOT, "results"))
CACHE_DIR = os.path.join(ROOT, "cache")

LABELS = ("true", "false", "unsure")
INF = float("inf")
KINDS = ["quantity", "money", "duration", "name", "percent", "boolean", "date", "version"]
CONV = {"KB": ("data", 1e-3), "MB": ("data", 1), "GB": ("data", 1e3), "TB": ("data", 1e6),
        "ms": ("time", 1e-3), "s": ("time", 1), "min": ("time", 60), "h": ("time", 3600),
        "day": ("time", 86400), "week": ("time", 604800)}


def date_interval(s):
    """exp.py: partial ISO date -> inclusive ordinal range."""
    p = s.split("-")
    if len(p) == 3:
        d = dt.date.fromisoformat(s).toordinal()
        return d, d
    if len(p) == 2:
        y, m = int(p[0]), int(p[1])
        a = dt.date(y, m, 1)
        b = dt.date(y + (m == 12), m % 12 + 1, 1)
        return a.toordinal(), b.toordinal() - 1
    y = int(p[0])
    return dt.date(y, 1, 1).toordinal(), dt.date(y, 12, 31).toordinal()


class Fact:
    """One stated atom. key=(subject, attribute) resolved through the lexicon (A/truth.slot_key);
    okey = key + (kind, dim) is exp.py's observation key (same kind and unit dimension).
    canon/lo/hi follow exp.py (V5/V9 semantics); acanon follows A/truth.py (exact rationals), None if unreadable."""
    __slots__ = ("key", "okey", "kind", "op", "value", "raw", "dim", "canon", "lo", "hi", "acanon")

    def __init__(self, a, alias, names):
        v = a["value"]
        kind = v["kind"]
        op = v.get("op", "eq") or "eq"
        x = v["value"]
        dim = None
        if kind in ("quantity", "duration"):
            unit = v.get("unit")
            if unit in CONV:
                dim, mult = CONV[unit]
                x = x * mult
            else:
                dim = unit
        elif kind == "money":
            dim = (v.get("currency"), v.get("per"))
        self.key = A.slot_key(a, names)
        self.okey = self.key + (kind, dim)
        self.kind, self.op, self.raw, self.value, self.dim = kind, op, v, v["value"], dim
        if kind in ("quantity", "duration", "money", "percent"):
            x = float(x)
            self.canon = round(x, 6)
            d = 1e-6 * max(1.0, abs(x))
            self.lo, self.hi = {"eq": (x, x), "lt": (-INF, x - d), "le": (-INF, x), "gt": (x + d, INF),
                                "ge": (x, INF)}[op]
        elif kind == "date":
            self.canon = x
            self.lo, self.hi = date_interval(x)
        elif kind == "name":
            self.canon = alias.get(str(x).casefold(), str(x).casefold())
            self.lo = self.hi = None
        else:
            self.canon = str(x).casefold() if kind == "version" else x
            self.lo = self.hi = None
        if kind not in KINDS:
            raise ValueError(kind)
        try:
            self.acanon = A.canon(v, names)
        except (ValueError, KeyError, TypeError, ZeroDivisionError, ArithmeticError):
            self.acanon = None

    def same(self, o):
        return self.canon == o.canon

    def consistent(self, o):  # exp.py V5: interval overlap
        if self.lo is None:
            return self.canon == o.canon
        tol = 1e-9 * max(1.0, abs(self.lo) if self.lo != -INF else 1.0)
        return max(self.lo, o.lo) <= min(self.hi, o.hi) + tol


def exp_alias(lex):
    al = {}
    for s in lex["subjects"]:
        for a in [s["name"]] + s["aliases"]:
            al[a.casefold()] = s["name"]
    for e in lex["events"]:
        n = e if isinstance(e, str) else e["name"]
        al.setdefault(n.casefold(), n)
    return al


def parse_facts(assertions, alias, names, drops):
    out = []
    for a in assertions or []:
        try:
            out.append(Fact(a, alias, names))
        except Exception as e:  # unreadable stated value: dropped and counted (worker D's rule)
            drops[type(e).__name__] += 1
    return out


def pages_of(dates, labelled, ids_num=None):
    """Page = maximal run of consecutive rows with the same date and the same labelled status
    (practice: also consecutive numeric ids). Public information only."""
    page = np.zeros(len(dates), np.int64)
    p = -1
    for i in range(len(dates)):
        brk = i == 0 or dates[i] != dates[i - 1] or labelled[i] != labelled[i - 1]
        if ids_num is not None and i and ids_num[i] != ids_num[i - 1] + 1:
            brk = True
        p += brk
        page[i] = p
    return page


class World:
    """Public view of one run. Attributes (n rows, m facts):
    name, static_key (label-free identity, safe as a cache key for label-free plugin data),
    ids, text (lists), date (int ordinal array), page (int array), interval (list of (start, end) half-open
    ordinals or None), facts (list of lists of Fact), labelled (bool array), label (object array, None where
    not labelled), lexicon (dict), n, n_pages, n_facts, fidx (m x 2 int array: row, position), frow,
    flat (list of Fact aligned with fidx), fstart (flat index of each row's first fact),
    obs (key -> [(row, pos)] sorted by date, stable), obs_typed (okey -> same), stats (dict)."""

    def __init__(self, name, static_key, ids, text, date, interval, facts, lexicon, labelled, label, page, stats):
        self.name, self.static_key = name, static_key
        self.ids, self.text, self.interval, self.facts, self.lexicon = ids, text, interval, facts, lexicon
        self.date = np.asarray(date, np.int64)
        self.page = np.asarray(page, np.int64)
        self.n = len(ids)
        self.n_pages = int(self.page.max()) + 1 if self.n else 0
        self.stats = stats
        self.fidx = np.array([(i, j) for i, fs in enumerate(facts) for j in range(len(fs))], np.int64).reshape(-1, 2)
        self.frow = self.fidx[:, 0]
        self.flat = [facts[i][j] for i, j in self.fidx]
        self.n_facts = len(self.flat)
        self.fstart = np.r_[0, np.cumsum([len(f) for f in facts])[:-1]].astype(np.int64)
        order = np.argsort(self.date, kind="stable")
        self.obs, self.obs_typed = C.defaultdict(list), C.defaultdict(list)
        for i in order:
            for j, f in enumerate(facts[i]):
                self.obs[f.key].append((int(i), j))
                self.obs_typed[f.okey].append((int(i), j))
        self.obs, self.obs_typed = dict(self.obs), dict(self.obs_typed)
        self._set_labels(labelled, label)

    def _set_labels(self, labelled, label):
        self.labelled = np.asarray(labelled, bool).copy()
        self.label = np.array([label[i] if self.labelled[i] else None for i in range(self.n)], dtype=object)

    def with_labels(self, labelled, label):
        """Same rows, another labelled mask (labels outside the mask are discarded)."""
        w = object.__new__(World)
        w.__dict__.update(self.__dict__)
        w._set_labels(labelled, label)
        return w


class Track:
    """name, kind, folds: list of (World, gold labels of the scored rows, scored row indices), train (transfer
    tracks only: the practice world, every row labelled). Held by run.py only; gold never reaches a variant."""

    def __init__(self, name, folds, kind):
        self.name, self.folds, self.kind, self.train = name, folds, kind, None


# ---------------------------------------------------------------- practice
def _practice():
    lex = json.load(open(os.path.join(PRACTICE_DIR, "lexicon.json"), encoding="utf-8"))
    alias, names = exp_alias(lex), A.alias_map(lex)
    rows = list(csv.DictReader(open(os.path.join(PRACTICE_DIR, "practice.csv"), newline="", encoding="utf-8")))
    rows.sort(key=lambda r: int(r["id"][2:]))
    drops = C.Counter()
    facts = [parse_facts(json.loads(r["form"]), alias, names, drops) for r in rows]
    date = [dt.date.fromisoformat(r["date"]).toordinal() for r in rows]
    page = pages_of(date, [True] * len(rows), [int(r["id"][2:]) for r in rows])
    gold = np.array([r["label"] for r in rows], dtype=object)
    w = World("practice", "practice", [r["id"] for r in rows], [r["text"] for r in rows], date, [None] * len(rows),
              facts, lex, np.zeros(len(rows), bool), gold, page, {"dropped_facts": dict(drops)})
    return w, gold


def practice_splits(n_pages, regime):
    """exp.py splits(): R80 = GroupKFold(5) over pages, R10 = 10 seeds of 10% labelled pages."""
    from sklearn.model_selection import GroupKFold
    pages = np.arange(n_pages)
    if regime == "P80":
        for _, te in GroupKFold(5).split(pages, groups=pages):
            lab = np.ones(n_pages, bool)
            lab[te] = False
            yield lab
    else:
        for seed in range(10):
            rng = random.Random(seed)
            lab = np.zeros(n_pages, bool)
            lab[rng.sample(range(n_pages), max(1, round(0.1 * n_pages)))] = True
            yield lab


# ---------------------------------------------------------------- suite
SUITE_WORLDS = {"dev": "dev", "diag": "diag", "cal": "cal", "sealed": "sealed", "syn": "synth", "pilot": "pilot",
                "prac": "prac", "extdev": "extdev", "extcal": "extcal", "extsealed": "extsealed"}
SUITE_PATHS = {"dev": "realistic-v1/development-20000", "cal": "realistic-v1/calibration-20000",
               "sealed": "realistic-v1/sealed-20000", "diag": "realistic-v1/diagnostic-6000",
               "synth": "realistic-synthetic-20000", "pilot": "realistic-v1/pilot-500",
               "prac": "realistic-v1/practice-1897", "extdev": "realistic-v1/external-development",
               "extcal": "realistic-v1/external-calibration", "extsealed": "realistic-v1/external-sealed"}
STRIP_IV = re.compile(r"^\s*from\b.{4,40}?\bthrough\b.{4,40}?\d{4}\s*,\s*", re.I)
HAS_IV = re.compile(r"\bfrom\b.{4,40}?\bthrough\b", re.I)


def jitter_day(rid, iv):
    """A/truth.py point-jitter: fixed pseudo-random day inside the half-open interval."""
    return iv[0] + int(hashlib.sha1(rid.encode()).hexdigest(), 16) % (iv[1] - iv[0])


def _suite_files(wkey, forms):
    base = os.path.join(SUITE_DIR, SUITE_PATHS[wkey])
    return (os.path.join(base, "public", "universe.csv"), os.path.join(base, "public", "lexicon.json"),
            os.path.join(EVALSUITE_DIR, "forms", forms, f"{wkey}.jsonl"))


def _suite_world(wkey, forms, mode):
    uni_p, lex_p, forms_p = _suite_files(wkey, forms)
    uni = list(csv.DictReader(open(uni_p, newline="", encoding="utf-8")))
    lex = json.load(open(lex_p, encoding="utf-8"))
    alias, names = exp_alias(lex), A.alias_map(lex)
    recs = {}
    for line in open(forms_p, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            recs.setdefault(str(r.get("id")), r)  # first record per id wins (A)
    drops, st = C.Counter(), C.Counter()
    ids, text, date, ivs, facts, labelled, label = [], [], [], [], [], [], []
    for r in uni:
        rec = recs.get(r["id"]) or {}
        lab = r["label"].strip().lower()
        d = A.ordinal(r["date"])
        iv = A.parse_interval(rec.get("interval"))
        t = r["text"]
        if mode == "j":
            if lab and iv and iv[1] > iv[0]:
                d = jitter_day(r["id"], iv)
                t2 = STRIP_IV.sub("", t)
                st["anchors_redated"] += 1
                st["anchor_text_still_states_interval"] += bool(HAS_IV.search(t2))
                t = t2[:1].upper() + t2[1:]
            iv = None
        st["rows_without_facts"] += not rec.get("assertions")
        ids.append(r["id"]); text.append(t); date.append(d); ivs.append(iv)
        facts.append(parse_facts(rec.get("assertions"), alias, names, drops))
        labelled.append(bool(lab)); label.append(lab or None)
    page = pages_of(date, labelled)
    st["dropped_facts"] = dict(drops)
    tag = f"{'S' if forms == 'gold' else 'X'}{[k for k, v in SUITE_WORLDS.items() if v == wkey][0]}-{mode}"
    return World(tag, tag, ids, text, date, ivs, facts, lex, labelled, label, page, dict(st))


def _cached(key_parts, files, build):
    h = hashlib.sha256()
    for p in files + [os.path.abspath(__file__), os.path.join(HERE, "vendor_a", "truth.py")]:
        h.update(open(p, "rb").read())
    h.update(json.dumps(key_parts).encode())
    path = os.path.join(CACHE_DIR, "-".join(map(str, key_parts)) + "-" + h.hexdigest()[:16] + ".pkl")
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except (OSError, EOFError, pickle.UnpicklingError):
        pass
    obj = build()
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)  # atomic: concurrent workers never read a partial file
    return obj


def suite_gold(wkey):
    """Gold labels of the targets (public label empty). Scoring only; never passed to a variant."""
    base = os.path.join(SUITE_DIR, SUITE_PATHS[wkey])
    g = {r["id"]: r["label"] for r in csv.DictReader(open(os.path.join(base, "gold", "labeled.csv"), newline="",
                                                          encoding="utf-8"))}
    return g


TRACK_RE = re.compile(r"^(P80|P10|([SX])(" + "|".join(SUITE_WORLDS) + r")-([jn])([tr]))$")
SELECTION = ("P80", "P10")


def parse_track(name):
    m = TRACK_RE.match(name)
    if not m:
        raise ValueError(f"unknown track {name!r}: P80, P10, S<w>-<j|n><t|r>, X<w>-<j|n><t|r>, w in {list(SUITE_WORLDS)}")
    return m


def practice_full():
    """Practice with every row labelled (the transfer training world)."""
    base, gold = _cached(["practice"], [os.path.join(PRACTICE_DIR, f) for f in ("practice.csv", "lexicon.json")],
                         _practice)
    return base.with_labels(np.ones(base.n, bool), gold), base, gold


def load_track(name):
    """-> Track. kind 'pooled' (P80), 'seeds' (P10), 'refit' (S/X ..r), 'transfer' (S/X ..t, track.train =
    practice with all rows labelled)."""
    m = parse_track(name)
    if name in ("P80", "P10"):
        _, base, gold = practice_full()
        folds = []
        for lab_pages in practice_splits(base.n_pages, name):
            lab = lab_pages[base.page]
            w = base.with_labels(lab, gold)
            sc = np.where(~lab)[0]
            folds.append((w, gold[sc], sc))
        return Track(name, folds, "pooled" if name == "P80" else "seeds")
    forms = "gold" if m.group(2) == "S" else "B"
    wkey, mode = SUITE_WORLDS[m.group(3)], m.group(4)
    w = _cached([wkey, forms, mode], list(_suite_files(wkey, forms)), lambda: _suite_world(wkey, forms, mode))
    g = suite_gold(wkey)
    sc = np.where(~w.labelled)[0]
    gold = np.array([g[w.ids[i]] for i in sc], dtype=object)
    t = Track(name, [(w, gold, sc)], "transfer" if m.group(5) == "t" else "refit")
    if m.group(5) == "t":
        t.train = practice_full()[0]
    return t
