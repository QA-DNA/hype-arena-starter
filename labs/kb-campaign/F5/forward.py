"""Forward selection and ablation of F5 plugins on top of V9-LR (select=points), scored by run.py on P80 + P10.

  python -I F5/forward.py forward [--base '{"model": "lr"}'] [--cands a,b,c] [--tag x]
  python -I F5/forward.py ablate --set a,b,c [--base ...]
Pre-registered acceptance at each forward step: mean points gain >= 0.002 over the current set and no track
(P80, P10) losing more than 0.002. Every evaluated set is a results line in results/F5.jsonl.
"""
import argparse
import json
import os
import subprocess
import sys

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(KBC, ".venv", "bin", "python")
VAR = "F5/f5v.py"
sys.path.insert(0, os.path.join(KBC, "F5"))
import summ  # noqa: E402

ALL = ["lie_stale", "lie_mult", "lie_swap", "lie_bool", "lie_date", "restate", "src_text", "txt_tuned", "src_page",
       "src_pagelie", "src_idblock", "uns_tl", "prior", "kind_oh"]


COLKEY = {"k": "cols"}
REMOTE = {"on": False, "jobs": 20, "n": 0, "tag": ""}
FILES = ("F5.jsonl", "F5-remote.jsonl")


def evaluate(param_list, jobs=2):
    R = summ.load(FILES)
    todo = [p for p in param_list if any((VAR, json.dumps(p, sort_keys=True), t) not in R for t in ("P80", "P10"))]
    if todo and REMOTE["on"]:
        REMOTE["n"] += 1
        tag = f"F5-fw{REMOTE['tag']}-{REMOTE['n']}"
        rs = os.path.join(KBC, "remote", "remote.sh")
        subprocess.run([rs, "run", tag, "--", "--variant", f"{VAR}={json.dumps(todo)}", "--tracks", "P80,P10",
                        "--jobs", str(REMOTE["jobs"]), "--worker", "F5-remote"], cwd=KBC, check=False,
                       stdout=subprocess.DEVNULL)
        subprocess.run([rs, "wait", tag], cwd=KBC, check=False, stdout=subprocess.DEVNULL)
        R = summ.load(FILES)
    elif todo:
        subprocess.run([PY, "-I", "harness/run.py", "--variant", f"{VAR}={json.dumps(todo)}", "--tracks", "P80,P10",
                        "--jobs", str(jobs), "--worker", "F5"], cwd=KBC, check=False, stdout=subprocess.DEVNULL)
        R = summ.load(FILES)
    out = []
    for p in param_list:
        a, b = (R.get((VAR, json.dumps(p, sort_keys=True), t)) for t in ("P80", "P10"))
        if a is None or b is None:
            out.append(None); continue
        x, y = a["metrics"]["points_per_row"], b["metrics"]["points_per_row"]
        out.append((round((x + y) / 2, 5), round(x, 5), round(y, 5)))
    return out


def forward(base, cands, log):
    cur = []
    s0 = evaluate([dict(base, plugins=cur)])[0]
    print("start", s0, file=log, flush=True)
    while cands:
        ps = [dict(base, plugins=cur + [c]) for c in cands]
        res = evaluate(ps)
        step = sorted(zip(res, cands), key=lambda x: -(x[0][0] if x[0] else -9))
        for r, c in step:
            print(f"  + {c:12s} {r}  (delta mean {r[0] - s0[0]:+.4f} P80 {r[1] - s0[1]:+.4f} P10 {r[2] - s0[2]:+.4f})",
                  file=log, flush=True)
        r, c = step[0]
        if r[0] - s0[0] >= 0.002 and min(r[1] - s0[1], r[2] - s0[2]) >= -0.002:
            cur.append(c); cands = [x for x in cands if x != c]; s0 = r
            print(f"ACCEPT {c} -> {cur} {s0}", file=log, flush=True)
        else:
            print(f"STOP at {cur} {s0}", file=log, flush=True)
            break
    return cur, s0


def colparams(base, cols):
    """['plugin.col', ...] -> f5v params with plugins + cols (column order: plugin first-seen order); with
    --colkey fact|stack (F5/onf2.py:OnChain) -> dict(base, fact=cols) or dict(base, stack=cols)."""
    if COLKEY["k"] != "cols":
        return dict(base, **{COLKEY["k"]: list(cols)})
    plugins, sel = [], {}
    for c in cols:
        p, col = c.split(".", 1)
        if p not in sel:
            plugins.append(p); sel[p] = []
        sel[p].append(col)
    return dict(base, plugins=plugins, cols=sel)


def colforward(base, cands, log, max_steps=12):
    cur = []
    s0 = evaluate([colparams(base, cur)])[0]
    print("start", s0, file=log, flush=True)
    for _ in range(max_steps):
        res = evaluate([colparams(base, cur + [c]) for c in cands])
        step = sorted(zip(res, cands), key=lambda x: -(x[0][0] if x[0] else -9))
        for r, c in step[:14]:
            print(f"  + {c:28s} {r}  (delta mean {r[0] - s0[0]:+.4f} P80 {r[1] - s0[1]:+.4f} P10 {r[2] - s0[2]:+.4f})",
                  file=log, flush=True)
        nul = [r[0] - s0[0] for r, c in step if c.startswith("nulls.")]
        real = [(r, c) for r, c in step if not c.startswith("nulls.")]
        bn = max(nul) if nul else -1.0
        print(f"  best null gain {bn:+.4f} over {len(nul)} nulls", file=log, flush=True)
        r, c = real[0]
        # revised rule (after the C=0.5 null control): gain >= max(0.002, best null + 0.002), no track losing > 0.002
        if r[0] - s0[0] >= max(0.002, bn + 0.002) and min(r[1] - s0[1], r[2] - s0[2]) >= -0.002:
            cur.append(c); cands = [x for x in cands if x != c]; s0 = r
            print(f"ACCEPT {c} -> {cur} {s0}", file=log, flush=True)
        else:
            print(f"STOP at {cur} {s0}", file=log, flush=True)
            break
    return cur, s0


def ablate(base, full, log):
    s_full = evaluate([dict(base, plugins=full)])[0]
    print("full", full, s_full, file=log, flush=True)
    res = evaluate([dict(base, plugins=[x for x in full if x != c]) for c in full])
    for c, r in zip(full, res):
        print(f"  - {c:12s} {r}  (delta mean {r[0] - s_full[0]:+.4f} P80 {r[1] - s_full[1]:+.4f} P10 {r[2] - s_full[2]:+.4f})",
              file=log, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode")
    ap.add_argument("--base", default="{}")
    ap.add_argument("--cands", default=",".join(ALL))
    ap.add_argument("--set", default=",".join(ALL))
    ap.add_argument("--tag", default="")
    ap.add_argument("--remote", action="store_true")
    ap.add_argument("--var", default=VAR, help="variant spec, e.g. F5/onf2.py:OnChain")
    ap.add_argument("--colkey", default="cols", choices=["cols", "fact", "stack"])
    a = ap.parse_args()
    VAR, COLKEY["k"] = a.var, a.colkey
    REMOTE["on"], REMOTE["tag"] = a.remote, a.tag
    base = json.loads(a.base)
    logp = os.path.join(KBC, "F5", f"log_{a.mode}{a.tag}.txt")
    with open(logp, "a") as log:
        print(f"== {a.mode} var={VAR} colkey={a.colkey} base={base}", file=log, flush=True)
        if a.mode == "colforward":
            colforward(base, a.cands.split(","), log)
        elif a.mode == "forward":
            forward(base, a.cands.split(","), log)
        else:
            ablate(base, a.set.split(","), log)
    print(open(logp).read())
