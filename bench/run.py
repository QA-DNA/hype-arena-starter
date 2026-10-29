"""Run judges on date- or row-grouped 5-fold CV.  python -m bench.run [--split date|row] [--forms gold|parsed] [names...]"""
import argparse, importlib, pkgutil, sys, time, json
from . import common, judges


def discover():
    out = {}
    for m in pkgutil.iter_modules(judges.__path__):
        try:
            mod = importlib.import_module(f"bench.judges.{m.name}")
            if hasattr(mod, "Judge"):
                out[mod.Judge.name] = mod.Judge
        except Exception as e:  # a broken experimental judge must not stop the others
            print(f"skip {m.name}: {e!r}", file=sys.stderr)
    return out


def evaluate(cls, rows, split):
    p_all, y_all, t0 = [], [], time.time()
    for k, train, test in common.folds(rows, split):
        j = cls()
        j.fit(train, test)
        p = j.predict(test)
        assert len(p) == len(test)
        truth = {r["id"]: r["label"] for r in rows}
        for r, x in zip(test, p):
            if truth[r["id"]] in ("true", "false"):
                p_all.append(x); y_all.append(truth[r["id"]] == "true")
    m = common.metrics(p_all, y_all); m["secs"] = time.time() - t0
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*"); ap.add_argument("--split", default="date", choices=["date", "row"])
    ap.add_argument("--forms", default="gold", choices=["gold", "parsed"]); ap.add_argument("--json")
    a = ap.parse_args()
    rows = common.load(a.forms, a.split)
    reg = discover()
    names = a.names or sorted(reg)
    print(f"split={a.split} forms={a.forms} scored rows={len(common.scored(rows))}")
    print(f"{'judge':18s} {'acc':>6s} {'logloss':>8s} {'brier':>6s} {'ece':>6s} {'hi_cov':>6s} {'hi_acc':>6s} {'cw':>6s} {'secs':>5s}")
    res = {}
    for n in names:
        m = evaluate(reg[n], rows, a.split); res[n] = m
        print(f"{n:18s} {m['acc']:6.3f} {m['logloss']:8.3f} {m['brier']:6.3f} {m['ece']:6.3f} {m['hi_cov']:6.2f} {m['hi_acc']:6.3f} {m['cw']:6.3f} {m['secs']:5.1f}")
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
