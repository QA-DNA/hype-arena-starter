"""Independent schema, lexicon, provenance and public-grammar checks for claim reports.

Requires Python jsonschema and referencing. This is a diagnostic, not the private referee.
Usage: py -3 tools/validate_claims.py artifacts/claims-report.json
"""
import argparse
import csv
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
NEGATION = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot|\w+n't)\b", re.I)
TIME = re.compile(r"\b(?:ago|yesterday|tomorrow|once|formerly|previously|originally|initially|recently|lately|soon|eventually|then|before|after|since|until|till|earlier|later|used to|last (?:week|month|quarter|year)|next (?:week|month|quarter|year)|in the past|in the future|at (?:the|that) time|January|February|March|April|June|July|August|September|October|November|December|spring|summer|autumn|winter|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", re.I)


def normalized(text):
    return " ".join(text.lower().split()).rstrip(".!? ")


def load_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def canonical_fact(fact):
    fact = json.loads(json.dumps(fact))
    if fact.get("value", {}).get("op") == "eq":
        fact["value"].pop("op")
    return json.dumps(fact, sort_keys=True)


def render(value):
    kind, amount = value["kind"], value["value"]
    if kind == "quantity":
        return f"{amount:,} {value['unit']}"
    if kind == "duration":
        return f"{amount} {value['unit']}"
    if kind == "money":
        return f"{value['currency']} {amount}" + (f" per {value['per']}" if "per" in value else "")
    if kind == "percent":
        return f"{amount}%"
    if kind == "version":
        return f"v{amount}"
    if kind == "boolean":
        return "yes" if amount else "not"
    return str(amount)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    claims = report.get("generation", report)["claims"]
    lexicon = json.loads((ROOT / "data/lexicon.json").read_text(encoding="utf-8"))
    subjects = {s["name"]: s for s in lexicon["subjects"]}
    rows = load_rows(ROOT / "data/practice.csv")
    for path in args.input:
        rows.extend(load_rows(path))
    originals = {normalized(r["text"]) for r in rows}
    sources = {r["id"]: r for r in rows}
    registry = Registry()
    schemas = []
    for name in ("entry.schema.json", "claimed_value.schema.json"):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        schemas.append(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(schemas[0], registry=registry)
    problems = []
    if len(claims) != args.count:
        problems.append(f"Expected {args.count} claims, found {len(claims)}")
    seen_ids, seen_texts, seen_forms = set(), set(), set()
    checked_sources = 0
    for claim in claims:
        prefix = claim["id"]
        def check(condition, message):
            if not condition:
                problems.append(f"{prefix}: {message}")
        entry = {k: claim[k] for k in ("id", "type", "text", "form", "confidence")}
        entry["tag"] = "true"
        for error in validator.iter_errors(entry):
            problems.append(f"{prefix}: schema {error.message}")
        text, form, kind = claim["text"], claim["form"], claim["type"]
        key = json.dumps([kind, form], sort_keys=True)
        check(prefix not in seen_ids, "duplicate ID")
        check(normalized(text) not in seen_texts, "duplicate normalized text")
        check(key not in seen_forms, "duplicate form")
        check(normalized(text) not in originals, "copies input text")
        check(prefix not in sources, "ID collides with input")
        seen_ids.add(prefix); seen_texts.add(normalized(text)); seen_forms.add(key)
        facts = [form["left"], form["right"]] if kind == "compare" else [form]
        for fact in facts:
            subject = subjects.get(fact["subject"])
            if kind != "relation":
                check(subject is not None and fact["attribute"] in subject["attributes"], "unknown lexicon fact")
        if kind == "relation":
            check(form["link"] in subjects.get(form["subject"], {}).get("attributes", []), "unknown link")
            check(form["attribute"] in subjects.get(form["target"], {}).get("attributes", []), "unknown target attribute")
        if kind == "at_event":
            check(form["event"] in lexicon["events"], "unknown event")
        residue = text
        named = [f["subject"] for f in facts]
        if kind == "at_event": named.append(form["event"])
        for name in named:
            surfaces = [name] + subjects.get(name, {}).get("aliases", [])
            patterns = [r"(?<!\w)" + r"\s*".join(map(re.escape, surface.split())) + r"(?!\w)" for surface in surfaces]
            matches = [m for pattern in patterns for m in re.finditer(pattern, residue, re.I)]
            check(bool(matches), f"subject/event absent: {name}")
            if matches:
                match = max(matches, key=lambda m: m.end()-m.start())
                residue = residue[:match.start()] + " " + residue[match.end():]
        values = [form["from"], form["to"]] if kind == "change" else ([form["value"]] if kind != "compare" else [])
        for value in values:
            literal = render(value)
            check(literal.lower() in text.lower(), f"declared value absent: {literal}")
            residue = re.sub(re.escape(literal), " ", residue, count=1, flags=re.I)
        if kind == "compare":
            phrase = {"lt":"is earlier than", "gt":"is later than", "eq":"is on the same day as"}[form["op"]]
            check(phrase in text, "date comparison phrase missing")
            residue = residue.replace(phrase, " ", 1)
            check(not re.search(r"\d", residue), "number outside required names")
        if kind not in ("change",):
            check(not TIME.search(residue), "extra temporal word")
        if not any(value["kind"] == "boolean" for value in values):
            check(not NEGATION.search(text), "negation in non-boolean claim")
        evidence = claim.get("evidence", [])
        check(bool(evidence), "no provenance")
        for observation in evidence:
            check(observation["label"] == "true", "non-true generation evidence")
            source = sources.get(observation["row_id"])
            check(source is not None, "evidence source absent from supplied inputs")
            if source:
                check(source["label"] == "true" and source["date"] == observation["date"], "evidence source label/date mismatch")
                if source.get("form"):
                    source_facts = {canonical_fact(f) for f in json.loads(source["form"])}
                    check(canonical_fact(observation["fact"]) in source_facts, "evidence assertion absent from source form")
                checked_sources += 1
        def matching(subject, attribute, value=None):
            return [e for e in evidence if e["fact"]["subject"] == subject
                    and e["fact"]["attribute"] == attribute
                    and (value is None or e["fact"]["value"] == value)]
        if kind == "change":
            before = matching(form["subject"], form["attribute"], form["from"])
            after = matching(form["subject"], form["attribute"], form["to"])
            check(any(a["date"] < b["date"] for a in before for b in after), "change lacks ordered source values")
        elif kind == "compare":
            left = matching(form["left"]["subject"], form["left"]["attribute"])
            right = matching(form["right"]["subject"], form["right"]["attribute"])
            check(bool(left and right), "comparison lacks both source facts")
            if left and right:
                a, b = left[0]["fact"]["value"], right[0]["fact"]["value"]
                check(a["kind"] == b["kind"] == "date", "unexpected non-date comparison")
                expected = "lt" if a["value"] < b["value"] else "gt" if a["value"] > b["value"] else "eq"
                check(form["op"] == expected, "comparison direction disagrees with sources")
        elif kind == "relation":
            links = matching(form["subject"], form["link"])
            targets = matching(form["target"], form["attribute"], form["value"])
            check(any(a["date"] == b["date"] and a["fact"]["value"] == {"kind":"name", "value":form["target"]}
                      for a in links for b in targets), "relation lacks contemporaneous link/target evidence")
        elif kind == "at_event":
            values = matching(form["subject"], form["attribute"], form["value"])
            dates = matching(form["event"], "date")
            check(any(a["date"] == b["fact"]["value"]["value"] for a in values for b in dates), "event value lacks matching event day")
        else:
            check(bool(matching(form["subject"], form["attribute"], form["value"])), "fact value absent from evidence")
    if problems:
        print("\n".join(problems[:40]))
        raise SystemExit(f"{len(problems)} diagnostic problems")
    print(f"Validated {len(claims)} claims: schemas, lexicon, newness, {checked_sources} source references and selected public-grammar conditions.")
    print("This diagnostic does not implement the private referee or guarantee temporal truth.")


if __name__ == "__main__":
    main()
