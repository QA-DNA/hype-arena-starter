"""Compare technique-1 variants on parsed facts: python -m bench.t1_experiment [date|row]"""
import sys
from . import common, run
from .judges import t1_soft as T
from .judges import a_bracket_gbm as A

split = sys.argv[1] if len(sys.argv) > 1 else "date"
rows = common.load("parsed", split)
T.load_hyps(split)
print(f"split={split}  parsed facts, hyps for {len(T.HYPS)} rows")
print(f"{'variant':34s} {'acc':>6s} {'logloss':>8s} {'brier':>6s} {'ece':>6s} {'hi_cov':>6s} {'hi_acc':>6s}")
def show(name, cls):
    m = run.evaluate(cls, rows, split)
    print(f"{name:34s} {m['acc']:6.3f} {m['logloss']:8.3f} {m['brier']:6.3f} {m['ece']:6.3f} {m['hi_cov']:6.2f} {m['hi_acc']:6.3f}", flush=True)
show("A (current, parsed evidence)", A.Judge)
for gold, trust, soft in [(True, False, False), (False, True, False), (True, True, False), (True, False, True), (True, True, True)]:
    T.GOLD_EVIDENCE, T.TRUST, T.SOFT = gold, trust, soft
    show(f"T1 gold_ev={int(gold)} trust={int(trust)} soft={int(soft)}", T.Judge)
