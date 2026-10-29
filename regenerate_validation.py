"""
regenerate_validation.py - deletes the broken Step-5 / GLM files and rebuilds an
honest validation set FROM practice.csv, where the LABEL IS COMPUTED BY CODE.

Why the old files had no `true` rows: the old recipe only defined 3 mutation
types (temporal_violation, metric_violation, unverified_claim), which by
construction are false/unsure. The LLM obeyed. Here the LLM never decides a
label; it only rewords text, and every reworded text is checked.

Output (data/):
  validation_v2.csv   id,text,date,label,form,mutation_type,source_id
  kb_v2.csv           practice.csv MINUS every source row used above
                      -> evaluate with:  run_pipeline.py --kb data/kb_v2.csv --eval data/validation_v2.csv
Target mix (matches the real practice data, ~80% true):
  true_original 40% | true_paraphrase 20% | true_shifted_date 10% (date moved inside the
  interval where the value still held) | metric_violation 15% | temporal_violation 10%
  (date moved into an interval where ANOTHER value held) | unsure_holdout 5%

LLM (optional): Featherless OpenAI-compatible API, key from env FEATHERLESS_API_KEY,
model from env FEATHERLESS_MODEL (default deepseek-ai/DeepSeek-V3-0324).
Without a key it runs fully offline with no paraphrases (still valid).

  python regenerate_validation.py --n 1200 [--no-llm] [--keep-old]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA = Path("data")
BAD_FILES = ["synthetic_validation.csv", "synthetic_validation_glm.csv"]
MIX = {"true_original": .40, "true_paraphrase": .20, "true_shifted_date": .10,
       "metric_violation": .15, "temporal_violation": .10, "unsure_holdout": .05}
UNIVERSE = (date(2025, 10, 7), date(2026, 10, 28))
rng = random.Random(42)


# ---------------------------------------------------------------- helpers
def vkey(v):  # value identity, ignoring op
    return json.dumps({k: v[k] for k in sorted(v) if k != "op"}, sort_keys=True)


def num_str(x) -> list[str]:
    """Ways a number may be written in text: 8800, 8,800, 8.800, 99.9"""
    if isinstance(x, bool):
        return []
    if isinstance(x, (int, float)):
        i = int(x)
        if float(x) == i:
            return [f"{i:,}", f"{i:,}".replace(",", "."), str(i)]
        return [str(x)]
    return [str(x)]


def mutate_value(v: dict):
    """Return a different value of the same kind and unit, or None."""
    k, x = v["kind"], v.get("value")
    w = dict(v)
    w.pop("op", None)
    if k in ("quantity", "money", "duration", "percent") and isinstance(x, (int, float)):
        for _ in range(10):
            f = rng.choice([0.5, 0.75, 1.25, 1.5, 2, 3]) if x else 1
            y = round(x * f) if float(x) == int(x) else round(x * f, 1)
            if k == "percent":
                y = min(y, 100)
            if y != x and y > 0:
                w["value"] = int(y) if float(y) == int(y) else y
                return w
        return None
    if k == "version":
        parts = str(x).split(".")
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + rng.choice([1, 2, 3]))
            w["value"] = ".".join(parts)
            return w
    return None  # booleans/names/dates: skip (need text rewrites, too risky)


def replace_number(text: str, old, new) -> str | None:
    for s in num_str(old):
        pat = r"(?<![\d.,])" + re.escape(s) + r"(?![\d]|[.,]\d)"
        if len(re.findall(pat, text)) == 1:
            new_s = f"{new:,}" if ("," in s and isinstance(new, int)) else str(new)
            return re.sub(pat, new_s, text)
    return None


# ---------------------------------------------------------------- LLM
def llm_paraphrase(text: str, must_keep: list[str]) -> str | None:
    key = os.environ.get("FEATHERLESS_API_KEY")
    if not key:
        return None
    import requests
    model = os.environ.get("FEATHERLESS_MODEL", "deepseek-ai/DeepSeek-V3-0324")
    prompt = ("Rewrite this sentence from a company news page with different wording. "
              "Keep every number, name, price, date and unit EXACTLY as written. Do not add "
              "any new fact, number, date, time word or negation. One sentence, output only it.\n\n"
              f"Sentence: {text}")
    for attempt in range(3):
        try:
            r = requests.post("https://api.featherless.ai/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key}"},
                              json={"model": model, "temperature": 0.7, "max_tokens": 120,
                                    "messages": [{"role": "user", "content": prompt}]}, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1)); continue
            r.raise_for_status()
            out = r.json()["choices"][0]["message"]["content"].strip().strip('"').split("\n")[0]
            # guard: every value string kept, no new digits, no negation
            if all(m in out for m in must_keep) and \
               set(re.findall(r"\d+", out)) <= set(re.findall(r"\d+", text)) and \
               not re.search(r"\b(not|never|no)\b|n't", out, re.I) and out != text:
                return out
            return None
        except Exception as e:  # noqa
            print("LLM error:", e, file=sys.stderr)
            time.sleep(2)
    return None


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--keep-old", action="store_true")
    a = ap.parse_args()
    if a.no_llm:
        os.environ.pop("FEATHERLESS_API_KEY", None)

    # 1) delete the broken files
    if not a.keep_old:
        for f in BAD_FILES:
            p = DATA / f
            if p.exists():
                p.unlink(); print("deleted", p)

    rows = list(csv.DictReader(open(DATA / "practice.csv", encoding="utf-8")))
    for r in rows:
        r["atoms"] = json.loads(r["form"]) if r.get("form") else []

    # 2) timeline of every (subject, attribute) from TRUE rows
    tl = defaultdict(list)                       # key -> [(date, vkey, row_id)]
    for r in rows:
        if r["label"] == "true":
            for at in r["atoms"]:
                tl[(at["subject"], at["attribute"])].append((date.fromisoformat(r["date"]), vkey(at["value"]), r["id"]))
    for k in tl:
        tl[k].sort()

    def intervals(key):
        """[(start, end_exclusive, vkey)] merged by value."""
        out = []
        for d, v, _ in tl[key]:
            if out and out[-1][2] == v:
                continue
            if out:
                out[-1][1] = d
            out.append([d, UNIVERSE[1] + timedelta(days=1), v])
        return out

    single = [r for r in rows if len(r["atoms"]) == 1 and r["label"] == "true"]
    quota = {m: round(a.n * p) for m, p in MIX.items()}
    used, out = set(), []

    def take(pool):
        pool = [r for r in pool if r["id"] not in used]
        if not pool:
            return None
        r = rng.choice(pool); used.add(r["id"]); return r

    def emit(r, text, d, label, atoms, m):
        out.append({"id": f"v2-{m[:4]}-{len(out)+1:04d}", "text": text, "date": str(d), "label": label,
                    "form": json.dumps(atoms, ensure_ascii=False), "mutation_type": m, "source_id": r["id"]})

    trues = [r for r in rows if r["label"] == "true"]
    for _ in range(quota["true_original"]):
        if (r := take(trues)): emit(r, r["text"], r["date"], "true", r["atoms"], "true_original")

    tries = 0
    while sum(o["mutation_type"] == "true_paraphrase" for o in out) < quota["true_paraphrase"] and tries < quota["true_paraphrase"] * 3:
        tries += 1
        r = take(trues)
        if not r: break
        keep = [s for at in r["atoms"] for s in num_str(at["value"].get("value"))[:1] if s]
        p = llm_paraphrase(r["text"], keep)
        if p: emit(r, p, r["date"], "true", r["atoms"], "true_paraphrase")
        else: used.discard(r["id"])
        if not os.environ.get("FEATHERLESS_API_KEY"): break
    # if no LLM, fill paraphrase quota with more originals
    missing = quota["true_paraphrase"] - sum(o["mutation_type"] == "true_paraphrase" for o in out)
    for _ in range(missing):
        if (r := take(trues)): emit(r, r["text"], r["date"], "true", r["atoms"], "true_original")

    # true, date shifted inside the SAME validity interval (temporal reasoning, still true)
    cand = [r for r in single if (r["atoms"][0]["subject"], r["atoms"][0]["attribute"]) in tl]
    for _ in range(quota["true_shifted_date"] * 4):
        if sum(o["mutation_type"] == "true_shifted_date" for o in out) >= quota["true_shifted_date"]: break
        r = take(cand)
        if not r: break
        at = r["atoms"][0]; d0 = date.fromisoformat(r["date"])
        iv = next((i for i in intervals((at["subject"], at["attribute"])) if i[0] <= d0 < i[1] and i[2] == vkey(at["value"])), None)
        if iv and (iv[1] - d0).days > 2:
            d = d0 + timedelta(days=rng.randint(1, min((iv[1] - d0).days - 1, 120)))
            if d <= UNIVERSE[1]:
                emit(r, r["text"], d, "true", r["atoms"], "true_shifted_date"); continue
        used.discard(r["id"])

    # metric violation: one number changed, same date -> false
    for _ in range(quota["metric_violation"] * 4):
        if sum(o["mutation_type"] == "metric_violation" for o in out) >= quota["metric_violation"]: break
        r = take(single)
        if not r: break
        at = r["atoms"][0]; nv = mutate_value(at["value"])
        txt = nv and replace_number(r["text"], at["value"]["value"], nv["value"])
        if txt and txt != r["text"]:
            emit(r, txt, r["date"], "false", [{**at, "value": nv}], "metric_violation"); continue
        used.discard(r["id"])

    # temporal violation: same text, date moved into an interval where ANOTHER value held -> false
    for _ in range(quota["temporal_violation"] * 4):
        if sum(o["mutation_type"] == "temporal_violation" for o in out) >= quota["temporal_violation"]: break
        r = take(cand)
        if not r: break
        at = r["atoms"][0]; ivs = intervals((at["subject"], at["attribute"]))
        other = [i for i in ivs if i[2] != vkey(at["value"]) and i[0] != i[1]]
        if other:
            i = rng.choice(other)
            span = max(0, min((i[1] - i[0]).days - 1, 120))
            d = i[0] + timedelta(days=rng.randint(0, span))
            emit(r, r["text"], d, "false", r["atoms"], "temporal_violation"); continue
        used.discard(r["id"])

    # unsure: the practice data's own unsure rows (the only honest source of unsure)
    uns = [r for r in rows if r["label"] == "unsure"]
    for _ in range(quota["unsure_holdout"]):
        if (r := take(uns)): emit(r, r["text"], r["date"], "unsure", r["atoms"], "unsure_holdout")

    # 3) checks: fail loudly instead of writing a broken file
    labels = Counter(o["label"] for o in out)
    texts = Counter((o["text"], o["date"]) for o in out)
    assert labels["true"] >= 0.6 * len(out), f"too few true rows: {labels}"
    assert labels["false"] > 0 and labels["unsure"] > 0, labels
    assert max(texts.values()) == 1, "duplicate rows"
    assert all(UNIVERSE[0] <= date.fromisoformat(o["date"]) <= UNIVERSE[1] for o in out), "date outside universe"
    assert not any(re.match(r"On \d{4}-\d\d-\d\d,", o["text"]) for o in out), "date prefix artefact"

    rng.shuffle(out)
    cols = ["id", "text", "date", "label", "form", "mutation_type", "source_id"]
    with open(DATA / "validation_v2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    with open(DATA / "kb_v2.csv", "w", newline="", encoding="utf-8") as f:   # no leakage
        w = csv.DictWriter(f, fieldnames=["id", "text", "date", "label", "form"])
        w.writeheader()
        w.writerows({k: r[k] for k in ["id", "text", "date", "label", "form"]} for r in rows if r["id"] not in used)
    print("wrote", DATA / "validation_v2.csv", len(out), "rows", dict(labels))
    print("mix:", dict(Counter(o["mutation_type"] for o in out)))
    print("wrote", DATA / "kb_v2.csv", "(practice minus", len(used), "source rows)")


if __name__ == "__main__":
    main()
