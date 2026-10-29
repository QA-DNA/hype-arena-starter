"""Example: a fact is true iff the latest labelled-true observation of its key at or before the row date
(other page) states a consistent value; no evidence -> fall back to the training true rate."""
import numpy as np
from api import Base, Prediction


class Variant(Base):
    def __init__(self, fallback="true"):
        self.fallback = fallback

    def predict(self, world):
        lab = np.full(world.n, self.fallback, dtype=object); conf = np.full(world.n, 0.6)
        ps = np.full(world.n_facts, np.nan)
        for n, (i, j) in enumerate(world.fidx):
            f = world.flat[n]
            prev = [(r, q) for r, q in world.obs_typed[f.okey] if world.label[r] == "true"
                    and world.page[r] != world.page[i] and world.date[r] <= world.date[i]]
            if prev:
                ps[n] = float(f.consistent(world.facts[prev[-1][0]][prev[-1][1]]))
                if ps[n] == 0: lab[i], conf[i] = "false", 0.7
        return Prediction(lab, np.where(lab == "unsure", np.nan, conf), ps)
