"""F4 lexicon-derived fact features (label-free: lexicon + stated facts of the world only).

lex_features(world) -> (n_facts x 27):
  0-7   value kind one-hot (KINDS order)
  8     n aliases of the subject (log1p)
  9-13  subject type one-hot: root org, event, person, venue, other
  14    n lexicon attributes of the subject (log1p)
  15    subject is an event AND its date is known (stated 'date' fact, or Qn YYYY in the name)
  16    signed log1p(days from the event date to the row date) (0 if unknown)
  17    row dated on or after the event date
  18    subject birth date known (earliest stated joined/launched/released/opened/founded/announced/published)
  19    signed log1p(days from birth to the row date)
  20    value names another lexicon subject (a relation link)
  21    linked subject is a person
  22    row dated before the linked subject's birth (e.g. named lead before joining)
  23-26 key volatility from stated facts: distinct-value ratio, change rate in date order,
        monotone share of numeric changes, log1p(n observations of the key)
"""
import datetime as dt
import math
import re
import sys
import os
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "harness"))
from world import KINDS  # noqa: E402

BIRTH = ("joined", "launched", "released", "opened", "founded", "announced", "published", "beta_opened",
         "beta_date", "general_availability_date", "stable_release", "generally_available")
LEADISH = re.compile(r"(lead|head|ceo|cto|owner|sponsor|chair|run_by|host|speaker)", re.I)
QRE = re.compile(r"\bQ([1-4])\s+(\d{4})\b")
N_LEX = 27
_CACHE = {}


def _sl(x):
    return math.copysign(math.log1p(abs(x)), x)


def _qend(name):
    m = QRE.search(name)
    if not m:
        return None
    q, y = int(m.group(1)), int(m.group(2))
    end = dt.date(y + (q == 4), (3 * q) % 12 + 1, 1) - dt.timedelta(days=1)
    return end.toordinal()


def _mode_date(vals):
    """Most frequently stated full-precision date (earliest on ties)."""
    full = [v for v in vals if isinstance(v, str) and len(v) == 10]
    if not full:
        return None
    c = Counter(full)
    best = max(c.values())
    return dt.date.fromisoformat(min(v for v in c if c[v] == best)).toordinal()


def lex_struct(world):
    """Label-free per-world structure, cached by static_key."""
    k = world.static_key
    if k in _CACHE:
        return _CACHE[k]
    lex = world.lexicon
    subj = {s["name"]: s for s in lex["subjects"]}
    events = {e if isinstance(e, str) else e["name"] for e in lex["events"]}
    # root org = subject with most attributes
    root = max(subj, key=lambda s: len(subj[s]["attributes"])) if subj else None
    persons, venues = set(), set()
    for s, d in subj.items():
        if "joined" in d["attributes"] or "previous_employer" in d["attributes"]:
            persons.add(s)
    for f in world.flat:
        if f.kind == "name" and f.canon in subj:
            if LEADISH.search(f.key[1]) and f.canon not in events:
                persons.add(f.canon)
            if f.key[1] == "venue":
                venues.add(f.canon)
    dates = defaultdict(list)
    for f in world.flat:
        if f.kind == "date" and f.op == "eq":
            dates[f.key].append(f.raw["value"])
    ev_date, birth = {}, {}
    for s in subj:
        d = _mode_date(dates.get((s, "date"), [])) if s in events or (s, "date") in dates else None
        if d is None and s in events:
            d = _qend(s)
        if d is not None:
            ev_date[s] = d
        bs = [_mode_date(dates.get((s, a), [])) for a in BIRTH]
        bs = [b for b in bs if b is not None]
        if bs:
            birth[s] = min(bs)
    # key volatility from stated facts in date order
    vol = {}
    for key, obs in world.obs.items():
        fs = [world.facts[i][j] for i, j in obs if world.facts[i][j].op == "eq"]
        if not fs:
            vol[key] = (0.0, 0.0, 0.0, math.log1p(len(obs)))
            continue
        vals = [f.canon for f in fs]
        ch = [(a, b) for a, b in zip(vals, vals[1:]) if a != b]
        num = [(a, b) for a, b in ch if isinstance(a, float) and isinstance(b, float)]
        mono = (sum(b > a for a, b in num) / len(num)) if num else 0.5
        vol[key] = (len(set(map(str, vals))) / len(vals), len(ch) / max(1, len(vals) - 1), mono,
                    math.log1p(len(obs)))
    out = dict(subj=subj, events=events, root=root, persons=persons, venues=venues, ev_date=ev_date,
               birth=birth, vol=vol)
    _CACHE[k] = out
    return out


def lex_features(world):
    S = lex_struct(world)
    X = np.zeros((world.n_facts, N_LEX))
    for n, f in enumerate(world.flat):
        i = world.frow[n]
        D = int(world.date[i])
        s = f.key[0]
        d = S["subj"].get(s)
        X[n, KINDS.index(f.kind)] = 1
        X[n, 8] = math.log1p(len(d["aliases"])) if d else 0
        t = 0 if s == S["root"] else 1 if s in S["events"] else 2 if s in S["persons"] else 3 if s in S["venues"] else 4
        X[n, 9 + t] = 1
        X[n, 14] = math.log1p(len(d["attributes"])) if d else 0
        e = S["ev_date"].get(s) if s in S["events"] else None
        if e is not None:
            X[n, 15] = 1
            X[n, 16] = _sl(D - e)
            X[n, 17] = float(D >= e)
        b = S["birth"].get(s)
        if b is not None:
            X[n, 18] = 1
            X[n, 19] = _sl(D - b)
        if f.kind == "name" and f.canon in S["subj"] and f.canon != s:
            X[n, 20] = 1
            X[n, 21] = float(f.canon in S["persons"])
            lb = S["birth"].get(f.canon)
            X[n, 22] = float(lb is not None and D < lb)
        X[n, 23:27] = S["vol"].get(f.key, (0, 0, 0, 0))
    return X


def lex_small(world):
    """Compact subset for LR stacking: kind one-hot dropped (v9 has the kind), keeps 8-26."""
    return lex_features(world)[:, 8:]


if __name__ == "__main__":
    from world import practice_full
    w, _, gold = practice_full()
    X = lex_features(w)
    assert X.shape == (w.n_facts, N_LEX) and np.isfinite(X).all()
    assert (X[:, :8].sum(1) == 1).all() and (X[:, 9:14].sum(1) == 1).all()
    S = lex_struct(w)
    print("persons", sorted(S["persons"]), "venues", sorted(S["venues"]))
    print("event dates", {k: dt.date.fromordinal(v).isoformat() for k, v in S["ev_date"].items()})
    print("col means", np.round(X.mean(0), 3))
    yr = gold[w.frow]
    for c in (15, 17, 18, 20, 21, 22):
        m = X[:, c] > 0
        print(c, int(m.sum()), "false share", round(float(np.mean(yr[m] == "false")), 3) if m.any() else None)
    print("lex selfcheck ok")
