"""Robustness check: rewrite gold forms into equivalent surface variants an extractor might
emit (lexicon alias subjects, converted units, plural nouns, 'v' versions, currency symbols,
attribute spacing, 12 months -> 1 year...). The ceiling must not move.
Usage: python -I perturb.py --worlds dev,diag  -> forms/gold-perturbed/<world>.jsonl"""
import argparse, json, os, random, sys
from fractions import Fraction
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite  # noqa: E402

DOWN = {"GB": ("MB", 1000), "TB": ("GB", 1000), "kg": ("g", 1000), "km": ("m", 1000), "GHz": ("MHz", 1000),
        "kW": ("W", 1000), "week": ("day", 7), "h": ("min", 60), "min": ("s", 60), "year": ("month", 12)}
SYM = {"EUR": "€", "USD": "$", "GBP": "£"}


def num(x):
    f = Fraction(str(x))
    return int(f) if f.denominator == 1 else float(f)


def variant(a, aliases, rng):
    a = json.loads(json.dumps(a))
    if aliases.get(a["subject"]) and rng.random() < 0.7:
        a["subject"] = rng.choice(aliases[a["subject"]])
    elif rng.random() < 0.3:
        a["subject"] = a["subject"].upper()
    if rng.random() < 0.5:
        a["attribute"] = a["attribute"].replace("_", " ")
    v = a["value"]
    k = v["kind"]
    if k in ("quantity", "duration") and v.get("unit") in DOWN and rng.random() < 0.7:
        u, f = DOWN[v["unit"]]
        v["unit"], v["value"] = u, num(Fraction(str(v["value"])) * f)
    elif k == "quantity" and v.get("unit") not in DOWN and rng.random() < 0.5 and v["unit"].isalpha() and len(v["unit"]) > 3:
        v["unit"] = v["unit"] + ("es" if v["unit"].endswith(("ch", "sh", "x")) else "s") if not v["unit"].endswith("y") else v["unit"][:-1] + "ies"
    elif k == "money" and rng.random() < 0.6:
        v["currency"] = SYM.get(v["currency"], v["currency"])
        if v.get("per") == "month" and rng.random() < 0.5:
            v["per"] = "monthly"
    elif k == "version" and rng.random() < 0.6:
        v["value"] = "v" + v["value"] + (".0" if v["value"].count(".") < 3 and rng.random() < 0.5 else "")
    elif k == "name" and rng.random() < 0.5:
        v["value"] = v["value"].lower()
    elif k == "percent" and rng.random() < 0.5:
        v["value"] = str(v["value"])
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worlds", default="dev,diag")
    a = ap.parse_args()
    out_dir = os.path.join(suite.OUT, "forms", "gold-perturbed")
    os.makedirs(out_dir, exist_ok=True)
    for w in a.worlds.split(","):
        lex = suite.read_lexicon(w)
        aliases = {s["name"]: s["aliases"] for s in lex["subjects"]}
        rng = random.Random(7)
        with open(os.path.join(out_dir, f"{w}.jsonl"), "w") as f:
            for r in suite.read_jsonl(os.path.join(suite.OUT, "forms", "gold", f"{w}.jsonl")):
                r["assertions"] = [variant(x, aliases, rng) for x in r["assertions"]]
                f.write(json.dumps(r) + "\n")
        print("wrote", w)


if __name__ == "__main__":
    main()
