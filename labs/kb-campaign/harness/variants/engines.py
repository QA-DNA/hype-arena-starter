"""Timeline truth engines of A/truth.py (vendored, unchanged) on the world's facts.
engine: 'interval' | 'point' | 'point-jitter' (A's semantics; on a -j world 'point' already is point-jitter)."""
import math

import numpy as np

import truth as A  # vendor_a, on sys.path via world.py
from api import Base
from world import jitter_day


class Variant(Base):
    def __init__(self, engine="interval"):
        assert engine in ("interval", "point", "point-jitter"), engine
        self.engine = engine

    def predict(self, world):  # parameter-free: evidence = the world's own labelled rows
        ev = A.Evidence("point" if self.engine == "point-jitter" else self.engine)
        ats = [[(f.key, f.acanon, f.op, 1.0) for f in fs] for fs in world.facts]
        for i in np.where(world.labelled)[0]:
            iv, day = world.interval[i], int(world.date[i])
            if self.engine == "point-jitter" and iv and iv[1] > iv[0]:
                day = jitter_day(world.ids[i], iv)
            ev.add(world.label[i], day, iv, ats[i])
        ev.finish()
        labels = np.full(world.n, "unsure", dtype=object)
        conf = np.full(world.n, np.nan)
        for i in range(world.n):
            if not ats[i]:
                continue
            day = int(world.date[i])
            verdicts = []
            for slot, c, op, _ in ats[i]:
                if c is None:
                    verdicts.append(("unknown", 0.0))
                    continue
                known, strength, conflict = ev.value_at(slot, day)
                if known is None:
                    v = "false" if (op or "eq") == "eq" and c in ev.neg.get((slot, day), ()) else "unknown"
                    verdicts.append((v, 0.9))
                    continue
                verdicts.append((A.compare(known, c, op), strength * (0.7 if conflict else 1.0)))
            falses = [p for v, p in verdicts if v == "false"]
            if falses:
                labels[i], conf[i] = "false", round(max(falses), 4)
            elif all(v != "unknown" for v, _ in verdicts):
                labels[i], conf[i] = "true", round(math.prod(p for _, p in verdicts), 4)
        return labels, conf
