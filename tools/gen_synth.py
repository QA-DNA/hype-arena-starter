"""Build-time data generation (never part of the submitted system).
  Task 1 -> data/synthetic_validation.csv  (counterfactuals; rumours written by an LLM, mutations are deterministic)
  Task 2 -> data/claims_1000.csv           (claims derived from true practice rows by rule, so truth comes from the data, not a model)
Run: .venv/bin/python -m tools.gen_synth [--no-llm] [--only 1|2]
"""
import argparse, collections, csv, json, os, random, re, time
from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, *p)
MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
NUMERIC = {"quantity", "money", "percent", "duration"}
BAD = set("""ago yesterday tomorrow once formerly previously originally initially recently lately soon eventually then before after
since until till earlier later last next used january february march april may june july august september october november december
spring summer autumn winter monday tuesday wednesday thursday friday saturday sunday not never no""".split())
MONTHS = "January February March April May June July August September October November December".split()
SYM = {"EUR": "€", "USD": "$", "GBP": "£"}
SYMBOL_UNITS = {"B", "KB", "MB", "GB", "TB", "mm", "cm", "m", "km", "in", "g", "kg", "mAh", "Hz", "kHz", "MHz", "GHz", "mW", "W", "kW"}

rows = list(csv.DictReader(open(D("data/practice.csv"))))
lex = json.load(open(D("data/lexicon.json")))
EVENTS = set(lex["events"])
SUBJ = {s["name"]: s for s in lex["subjects"]}
from referencing import Registry, Resource
_cv = json.load(open(D("contracts/claimed_value.schema.json")))
_reg = Registry().with_resource(_cv["$id"], Resource.from_contents(_cv))
entry_v = Draft202012Validator(json.load(open(D("contracts/entry.schema.json"))), registry=_reg)
value_v = Draft202012Validator(_cv)
vkey = lambda v: json.dumps(v, sort_keys=True)

# ---------- timelines from true rows ----------
TL = collections.defaultdict(list)          # (subject, attribute) -> [(date, value, row id)]
for r in rows:
    if r["label"] == "true":
        for f in json.loads(r["form"]):
            if "op" not in f["value"]:
                TL[(f["subject"], f["attribute"])].append((r["date"], f["value"], r["id"]))
for k in TL:
    TL[k].sort(key=lambda t: t[0])


def current(k):
    """Latest true value and how many true rows agree with it; None if too thin to trust."""
    t = TL[k]; v = t[-1][1]; n = sum(1 for x in t if vkey(x[1]) == vkey(v))
    return (v, n) if n >= 2 or t[-1][0] >= "2026-09-01" else (None, 0)


conf = lambda n: round(min(0.98, 0.90 + 0.02 * n), 2)


# ---------- rendering (value-forms.md) ----------
def num(x):
    return f"{int(x):,}" if float(x).is_integer() else f"{x:,}"


def plural(u, n):
    if n == 1: return u
    if u == "person": return "people"
    if re.search(r"[^aeiou]y$", u): return u[:-1] + "ies"
    return u + "es" if re.search(r"(s|x|ch|sh)$", u) else u + "s"


def render(v):
    k = v["kind"]
    if k == "quantity":
        u = v["unit"]; return f"{num(v['value'])} {u if u in SYMBOL_UNITS else plural(u, v['value'])}"
    if k == "money":
        if v["currency"] not in SYM: return None
        return f"{SYM[v['currency']]}{num(v['value'])}" + (f" per {v['per']}" if v.get("per") else "")
    if k == "percent":
        return f"{v['value']}%"
    if k == "duration":
        u = v["unit"]; return f"{num(v['value'])} {plural(u, v['value']) if u in ('day', 'week', 'month', 'year') else u}"
    if k == "date":
        p = v["value"].split("-")
        if len(p) == 3: return f"{int(p[2])} {MONTHS[int(p[1]) - 1]} {p[0]}"
    return None


def words(attr):
    w = attr.replace("_", " ")
    return None if re.search(r"\d", w) or BAD & set(w.lower().split()) else w


name_ok = lambda s: not re.search(r"\d\.\d", s)
noun_qty = lambda v: v["kind"] == "quantity" and v["unit"] not in SYMBOL_UNITS


def fact_text(s, a, v):
    r, w = render(v), words(a)
    if r is None or w is None or not name_ok(s): return None
    if noun_qty(v): return f"{s} has {r}."
    if v["kind"] == "date": return f"{s} joined on {r}." if a == "joined" else None
    return f"The {w} of {s} is {r}."


# ---------- Task 2 ----------
def claims():
    out = {t: [] for t in ("fact", "compare", "change", "at_event", "relation")}
    rnd = random.Random(7)
    cur = {k: current(k) for k in TL}
    cur = {k: c for k, c in cur.items() if c[0] and k[0] not in EVENTS}
    for (s, a), (v, n) in cur.items():                                   # fact
        t = fact_text(s, a, v)
        if t and v["kind"] not in ("name", "boolean", "version"):
            out["fact"].append((t, {"subject": s, "attribute": a, "value": v}, conf(n)))
    cls = lambda v: (v["kind"], v.get("unit"), v.get("currency"), v.get("per")) if v["kind"] in NUMERIC else None
    pool = [(k, c) for k, c in cur.items() if cls(c[0]) and words(k[1]) and name_ok(k[0]) and not re.search(r"\d", k[0])]
    pairs = []
    for i, (k1, (v1, n1)) in enumerate(pool):                            # compare
        for k2, (v2, n2) in pool[i + 1:]:
            a, b = k1[0].lower(), k2[0].lower()
            if cls(v1) != cls(v2) or a in b or b in a or v1["value"] == v2["value"]: continue
            if max(v1["value"], v2["value"]) < 1.25 * min(v1["value"], v2["value"]): continue
            big, small = (k1, k2) if v1["value"] > v2["value"] else (k2, k1)
            op = rnd.choice(["gt", "lt"]); L, R = (big, small) if op == "gt" else (small, big)
            pairs.append((f"The {words(L[1])} of {L[0]} is {'higher' if op == 'gt' else 'lower'} than the {words(R[1])} of {R[0]}.",
                          {"left": {"subject": L[0], "attribute": L[1]}, "right": {"subject": R[0], "attribute": R[1]}, "op": op},
                          conf(min(n1, n2))))
    rnd.shuffle(pairs); use = collections.Counter()
    for p in pairs:
        ks = [(p[1][x]["subject"], p[1][x]["attribute"]) for x in ("left", "right")]
        if all(use[x] < 4 for x in ks):
            out["compare"].append(p); use.update(ks)
    for (s, a), t in TL.items():                                         # change
        if s in EVENTS or not words(a) or not name_ok(s): continue
        seq = []
        for d, v, _ in t:
            if v["kind"] in NUMERIC and (not seq or vkey(seq[-1][1]) != vkey(v)): seq.append((d, v))
        for i in range(len(seq)):
            for j in range(i + 1, len(seq)):
                A, B = render(seq[i][1]), render(seq[j][1])
                if A and B and A != B:
                    out["change"].append((f"The {words(a)} of {s} went from {A} to {B}.",
                                          {"subject": s, "attribute": a, "from": seq[i][1], "to": seq[j][1]}, 0.92 if j == i + 1 else 0.90))
    ev = {}                                                              # at_event
    for e in EVENTS:
        ds = collections.Counter(v["value"] for _, v, _ in TL.get((e, "date"), []) if len(v["value"]) == 10)
        if ds: ev[e] = ds.most_common(1)[0][0]
    for (s, a), t in TL.items():
        if s in EVENTS or not words(a) or not name_ok(s): continue
        for e, ed in ev.items():
            if any(w in e.split() for w in s.split()): continue
            before = [x for x in t if x[0] <= ed]; after = [x for x in t if x[0] >= ed]
            if before and after and vkey(before[-1][1]) == vkey(after[0][1]) and before[-1][1]["kind"] in NUMERIC:
                v = before[-1][1]; r = render(v)
                if not r: continue
                head = "the " + e[4:] if e.startswith("The ") else e
                tx = f"At {head}, {s} had {r}." if noun_qty(v) else f"At {head}, the {words(a)} of {s} was {r}."
                out["at_event"].append((tx, {"subject": s, "attribute": a, "event": e, "value": v}, 0.93))
    links = collections.defaultdict(list)                                # relation
    for (s, a), t in TL.items():
        for d, v, _ in t:
            if v["kind"] == "name" and v["value"] in SUBJ and s not in EVENTS: links[(s, a, v["value"])].append(d)
    for (s, a, tg), ds in links.items():
        lw = words(a)
        if not lw: continue
        for (ts, ta), t in TL.items():
            if ts != tg: continue
            win = [v for d, v, _ in t if ds[0] <= d <= ds[-1] and v["kind"] in NUMERIC | {"date"}]
            if win and len({vkey(x) for x in win}) == 1:
                v = win[0]; r = render(v)
                if not r: continue
                if v["kind"] == "date" and ta == "joined": tx = f"The {lw} of {s} joined on {r}."
                elif noun_qty(v): tx = f"The {lw} of {s} has {r}."
                else: continue
                out["relation"].append((tx, {"subject": s, "link": a, "target": tg, "attribute": ta, "value": v}, 0.92))
    inputs = {r["text"].strip().lower() for r in rows}
    final = []
    for t, items in out.items():
        seen = set(); keep = []
        for tx, f, c in items:
            if tx.lower() in inputs or tx in seen: continue
            seen.add(tx); keep.append((t, tx, f, c))
        rnd.shuffle(keep); final += keep[:200]
        print(f"{t}: {len(keep)} candidates, {min(200, len(keep))} kept")
    return final


def write_claims():
    w = csv.writer(open(D("data/claims_1000.csv"), "w", newline="")); w.writerow("id,type,text,form,label,confidence".split(","))
    n = bad = 0
    for t, tx, f, c in claims():
        e = {"id": f"c-{n + 1:04d}", "type": t, "text": tx, "form": f, "tag": "true", "confidence": c}
        errs = list(entry_v.iter_errors(e))
        if errs: bad += 1; print("SCHEMA FAIL", tx, errs[0].message[:100]); continue
        n += 1; w.writerow([e["id"], t, tx, json.dumps(f, ensure_ascii=False), "true", c])
    print(f"claims_1000.csv: {n} rows written, {bad} failed schema (target 1000)")


# ---------- Task 1 ----------
def client():
    from openai import OpenAI
    key = next(l.split("=", 1)[1].strip().strip("\"'") for l in open(D(".env")) if l.startswith("FEATHERLESS_API_KEY="))
    return OpenAI(base_url="https://api.featherless.ai/v1", api_key=key)


def llm_json(cl, prompt):
    from openai import RateLimitError
    for a in range(6):
        try:
            r = cl.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.8,
                                           max_tokens=16000, response_format={"type": "json_object"})
            return json.loads(r.choices[0].message.content)
        except RateLimitError:
            time.sleep(2 ** (a + 1))
        except json.JSONDecodeError:
            pass
    return {}


RUMOUR = """For each item, write ONE short rumour sentence about the same subject, in the style of an unverified leak ("reportedly", "sources claim"). It must concern a topic that is NOT one of the subject's known attributes, contain no digits, and be neither confirmed nor contradicted by the true sentence. Name the subject exactly as given.
Items: {items}
Answer as JSON: {{"items":[{{"i":<id>,"text":"..."}}]}}"""


def bump(v):
    x = v["value"]
    return x + max(1, round(abs(x) * 0.1)) if isinstance(x, int) else round(x * 1.1, 2)


def numstr(v):
    x = v["value"]; c = {f"{x:,}", str(x)}
    if isinstance(x, float) and x.is_integer(): c |= {f"{int(x):,}", str(int(x))}
    return sorted(c, key=len, reverse=True)


def write_validation(use_llm, n_rows=400):
    cands = []
    for r in rows:
        f = json.loads(r["form"])
        if r["label"] != "true" or len(f) != 1 or f[0]["value"]["kind"] not in NUMERIC or "op" in f[0]["value"]: continue
        f = f[0]; v = f["value"]; t = TL.get((f["subject"], f["attribute"]), [])
        other = [d for d, x, _ in t if vkey(x) != vkey(v)]
        if not other: continue
        for s in numstr(v):                       # the value must appear literally in the text to be mutable
            m = re.search(r"(?<![\d,.])" + re.escape(s) + r"(?![\d,]|\.\d)", r["text"])
            if m: break
        else: continue
        nv = dict(v); nv["value"] = bump(v)
        if any(vkey(nv) == vkey(x) for _, x, _ in t): continue
        new = f"{nv['value']:,}" if isinstance(nv["value"], int) else str(nv["value"])
        cands.append((r, f, v, nv, other, r["text"][:m.start()] + new + r["text"][m.end():]))
    random.Random(3).shuffle(cands); cands = cands[:n_rows]
    rumours = {}
    if use_llm:
        cl = client()
        def run(b):
            batch = [{"i": b + j, "subject": c[1]["subject"], "known_attributes": SUBJ.get(c[1]["subject"], {}).get("attributes", []), "true_sentence": c[0]["text"]}
                     for j, c in enumerate(cands[b:b + 20])]
            return llm_json(cl, RUMOUR.format(items=json.dumps(batch))).get("items", [])
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(4) as ex:
            for items in ex.map(run, range(0, len(cands), 20)):
                for it in items:
                    if isinstance(it, dict): rumours[it.get("i")] = it.get("text")
    w = csv.writer(open(D("data/synthetic_validation.csv"), "w", newline="")); w.writerow("id,text,date,label,form,mutation_type".split(","))
    n = fb = 0
    for i, (r, f, v, nv, other, mtext) in enumerate(cands):
        rum = rumours.get(i)
        if not isinstance(rum, str) or f["subject"].lower() not in rum.lower() or re.search(r"\d", rum.replace(f["subject"], "")):
            rum = f"Unconfirmed reports claim {f['subject']} is quietly exploring a confidential new partnership."; fb += 1
        d = random.Random(i).choice(other)
        form = lambda val: json.dumps([{**f, "value": val}])
        for mt, tx, dt, lab, fm in (("temporal", r["text"], d, "false", form(v)), ("numeric", mtext, r["date"], "false", form(nv)),
                                    ("rumour", rum, r["date"], "unsure", "[]")):
            for x in json.loads(fm):
                errs = list(value_v.iter_errors(x["value"]))
                assert not errs, (x, errs[0].message)
            n += 1; w.writerow([f"sv-{n:04d}", tx, dt, lab, fm, mt])
    print(f"synthetic_validation.csv: {n} rows from {len(cands)} source rows ({fb} rumours used the fallback template)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--no-llm", action="store_true"); ap.add_argument("--only", choices=["1", "2"])
    a = ap.parse_args()
    if a.only != "1": write_claims()
    if a.only != "2": write_validation(not a.no_llm)
