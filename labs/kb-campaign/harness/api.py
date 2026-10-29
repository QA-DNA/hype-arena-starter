"""Variant and feature-plugin loading (see API.md)."""
import importlib
import importlib.util
import inspect
import os
import sys
from collections import namedtuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# labels: object array of 'true'/'false'/'unsure' for every row; conf: float array, NaN on unsure;
# fact_scores: optional float array aligned with world.fidx (P(fact true) or any per-fact score).
Prediction = namedtuple("Prediction", "labels conf fact_scores", defaults=(None,))


class Base:
    """Optional base class. run(world) = fit(world) then predict(world); fit is a no-op by default.
    Parameter-free variants only implement predict(world)."""

    def fit(self, train_world):
        return self

    def predict(self, world):
        raise NotImplementedError

    def run(self, world):
        self.fit(world)
        return self.predict(world)


def run_variant(v, world, train=None):
    """How the harness calls a variant. train=None (P80, P10, ..r tracks): run(world) if defined, else
    fit(world) + predict(world). train given (..t tracks): fit(train) if defined, then predict(world)."""
    if train is None:
        if hasattr(v, "run"):
            return v.run(world)
        if hasattr(v, "fit"):
            v.fit(world)
        return v.predict(world)
    if not hasattr(v, "predict"):
        raise TypeError(f"{type(v).__name__} has no predict(world): transfer tracks need fit/predict")
    if hasattr(v, "fit"):
        v.fit(train)
    return v.predict(world)


def _module(name):
    if name.endswith(".py") or os.sep in name:
        path = os.path.abspath(name)
        spec = importlib.util.spec_from_file_location(os.path.splitext(os.path.basename(path))[0], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    try:
        return importlib.import_module(f"variants.{name}")
    except ModuleNotFoundError as e:
        if e.name not in (f"variants.{name}", "variants"):
            raise
        return importlib.import_module(name)


def resolve(spec, default_attr):
    """'name' | 'name:attr' | 'path/to/file.py:attr' -> (object, source file). A bare name is looked up
    in harness/variants/ first, then as a dotted module on sys.path."""
    mod_name, _, attr = spec.rpartition(":") if ":" in spec else (spec, "", default_attr)
    mod = _module(mod_name)
    return getattr(mod, attr or default_attr), inspect.getsourcefile(mod)


def feature_block(world, spec, role=None):
    """Call a feature plugin func(world[, role=...]) -> (world.n_facts x k) float array.
    role (per-row evidence role, only during self-training) is passed when the function accepts it."""
    fn, _ = resolve(spec, "features")
    kw = {"role": role} if "role" in inspect.signature(fn).parameters else {}
    X = np.asarray(fn(world, **kw), float)
    if X.ndim == 1:
        X = X[:, None]
    if X.shape[0] != world.n_facts:
        raise ValueError(f"feature plugin {spec}: {X.shape[0]} rows, world has {world.n_facts} facts")
    return X


def check_prediction(world, pred):
    if not isinstance(pred, Prediction):
        pred = Prediction(*pred)
    labels = np.asarray(pred.labels, dtype=object)
    conf = np.asarray(pred.conf, float)
    if labels.shape != (world.n,) or conf.shape != (world.n,):
        raise ValueError(f"prediction shape {labels.shape}/{conf.shape}, world has {world.n} rows")
    bad = set(labels.tolist()) - {"true", "false", "unsure"}
    if bad:
        raise ValueError(f"bad labels {sorted(map(str, bad))[:5]}")
    dec = labels != "unsure"
    if np.isnan(conf[dec]).any() or (conf[dec] < 0).any() or (conf[dec] > 1).any():
        raise ValueError("decided rows need a confidence in [0, 1]")
    conf = conf.copy()
    conf[~dec] = np.nan
    return Prediction(labels, conf, pred.fact_scores)
