"""V0: always 'true'; confidence = share of 'true' among the training world's labelled rows (exp.py v0)."""
import numpy as np

from api import Base


class Variant(Base):
    def __init__(self):
        self.rate = 0.5

    def fit(self, train_world):
        lab = train_world.label[train_world.labelled]
        self.rate = float(np.mean(lab == "true")) if len(lab) else 0.5
        return self

    def predict(self, world):
        return np.full(world.n, "true", dtype=object), np.full(world.n, self.rate)
