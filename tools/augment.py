"""Build-time data augmentation: LLM paraphrases of practice rows, kept only if our deterministic value parser still reads
the same values. Output: data/synth/paraphrases.jsonl  {src, model, text, facts}.   python -m tools.augment --rows 30 --models A,B
"""
import argparse, json, random, re, sys, concurrent.futures as cf
from bench import common
from hype import parse, values
from tools.featherless import chat, spent, cap, BudgetExceeded

PROMPT = """Rewrite the sentence below in {n} different ways. Rules:
- Keep every number, unit, date, price, percentage, version and proper name EXACTLY as written (same digits, same currency symbol, same unit), and keep the meaning identical.
- If the sentence says something is not the case, keep that negation; if it does not, add none.
- Change the wording, sentence structure and style (formal, casual, headline, press-release). Keep each rewrite to one sentence.
- Do not add any new number, date or name.
Sentence: {text}
Answer with a JSON list of {n} strings and nothing else."""


def canon(v):
    d = {k: x for k, x in v.items() if k != "op"}
    if isinstance(d["value"], float): d["value"] = round(d["value"], 9)
    return json.dumps(d, sort_keys=True)


def accept(row, text, lex, units):
    if not 15 <= len(text) <= 300: return False
    ments = lex.mentions(text)
    want = {f["subject"] for f in row["facts"]} & {s for _, _, s in lex.mentions(row["text"])}
    if not want <= {s for _, _, s in ments}: return False
    masks = [(a, b) for a, b, _ in ments]
    got = {canon(c["v"]) for c in values.extract(text, masks=masks, known_units=units)}
    for f in row["facts"]:
        v = f["value"]
        if v["kind"] == "boolean":
            if v["value"] == values.has_negation(text): return False
        elif v["kind"] == "name":
            if v["value"].lower() not in text.lower(): return False
        elif canon(v) not in got: return False
    return True


def one(row, model, n, lex, units):
    try:
        out = chat(model, [{"role": "user", "content": PROMPT.format(n=n, text=row["text"])}], max_tokens=60 * n + 60, temperature=0.9, purpose="paraphrase")
        arr = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
        return [(t, accept(row, t, lex, units)) for t in arr if isinstance(t, str)]
    except BudgetExceeded: raise
    except Exception as e:
        return [("ERR " + repr(e)[:80], False)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--rows", type=int, default=30); ap.add_argument("--models", required=True)
    ap.add_argument("--n", type=int, default=3); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--out", default="data/synth/paraphrases.jsonl")
    ap.add_argument("--max-usd", type=float, default=2.0); a = ap.parse_args()
    rows = [r for r in common.load() if r["facts"]]; random.Random(1).shuffle(rows); rows = rows[:a.rows]
    lex = parse.Lex(json.load(open(common.LEXICON)))
    units = {f["value"]["unit"] for r in common.load() for f in r["facts"] if f["value"]["kind"] == "quantity"}
    start = spent(); stats = {}
    with open(a.out, "a") as fo, cf.ThreadPoolExecutor(a.workers) as ex:
        jobs = {ex.submit(one, r, m, a.n, lex, units): (r, m) for r in rows for m in a.models.split(",")}
        for j in cf.as_completed(jobs):
            r, m = jobs[j]
            try: res = j.result()
            except BudgetExceeded as e: print("STOP:", e); break
            s = stats.setdefault(m, [0, 0, 0])
            for t, ok in res:
                s[0] += 1; s[1] += ok; s[2] += t.startswith("ERR")
                if ok: fo.write(json.dumps({"src": r["id"], "model": m, "text": t, "facts": r["facts"]}) + "\n"); fo.flush()
            if spent() - start > a.max_usd: print("run cap reached"); break
    for m, (n, k, e) in stats.items(): print(f"{m}: {n} paraphrases, {k} kept ({k/max(n,1):.0%}), {e} errors")
    print("run cost $%.4f, total spent $%.4f of cap $%.2f" % (spent() - start, spent(), cap()))
