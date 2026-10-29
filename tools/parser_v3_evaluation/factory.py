"""Fresh parser challenges; expected ASTs are constructed, never extracted.

Do not inspect the reserved branch of this factory to tune a parser. Its reserved
wordings and seeds are evaluator-only until the coordinator confirms freeze.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from itertools import product
import random
import secrets
from pathlib import Path

from .io import ROOT, digest, load_json, public_digest, public_hashes, require_artifacts, write_json, write_jsonl
from .oracle import INVERSE, assertions, ast_facts, canonical_ast, channel, evaluate, label, typed, validate_ast

FAMILIES = (
    "typed_exact", "comparisons", "negated_comparisons", "multi_entity", "multi_clause",
    "nested_scope", "version_binding", "object_distractors", "pronouns_enabled", "document_bounds",
    "ambiguous_ownership", "missing_values", "raw_precision", "units_and_billing", "punctuation", "metamorphic",
)
COUNTS = {"development": 32, "final": 128}
PROVENANCE = "New counterfactual cases and independent Python oracle authored with development-time OpenAI Codex assistance on 2026-10-29; no runtime LLM, no Hooly truth claims, no copied prior evaluation examples."


@dataclass(frozen=True)
class Slot:
    subject: str
    attribute: str
    kind: str
    unit: str | None = None


SLOTS = {
    "quantity": [Slot(s, a, "quantity", u) for s, a, u in (
        ("Hooly Gemini", "languages", "language"), ("Hooly Docs", "simultaneous_editors", "editor"),
        ("Hooly Workspace", "included_seats", "seat"), ("Hooly Drive", "free_storage", "GB"),
        ("Hooly Pixel 10", "weight", "g"), ("Hooly Pixel Watch", "water_resistance_depth", "m"),
        ("Hooly Pixel Fold", "base_storage", "GB"), ("Hooly Calendar", "max_guests", "guest"))],
    "money": [Slot(s, a, "money") for s, a in (
        ("Hooly AI Pro", "price"), ("Hooly Workspace", "price"), ("Hooly Jules", "price"),
        ("Hooly Photos Lite", "price"), ("Hooly Photos Plus", "price"), ("Hooly Photos Max", "price"),
        ("Hooly Pixel 10", "price"), ("Hooly Berlin Office", "rent"))],
    "percent": [Slot(s, a, "percent") for s, a in (
        ("Hooly Gemini", "flawbench_score"), ("Hooly Gemini", "uptime_last_quarter"),
        ("Hooly Cloud", "uptime_sla"), ("Hooly Gmail", "spam_catch_rate"),
        ("Hooly Translate", "rated_accuracy"), ("Hooly Photos", "yearly_billing_discount"),
        ("Hooly Hiring Programme", "offer_acceptance"), ("Hooly Employee Survey", "response_rate"))],
    "date": [Slot(s, a, "date") for s, a in (
        ("Hooly Docs", "launched"), ("Hooly Calendar", "launched"), ("Hooly Pixel 10 Pro", "released"),
        ("Hooly I/O 2027", "date"), ("Hooly Berlin Office", "lease_end"), ("Bertram Gilfoil", "joined"),
        ("Hooly Gemini", "training_data_cutoff"), ("Hooly Chrome", "stable_release_date"))],
    "version": [Slot(s, a, "version") for s, a in (
        ("Hooly Gemini", "version"), ("Hooly Gemini", "api_version"), ("Hooly Cloud", "cli_version"),
        ("Hooly Docs", "version"), ("Hooly Calendar", "version"), ("Hooly Sheets", "version"),
        ("Hooly Chrome", "stable_version"), ("Hooly Photos", "version"))],
    "duration": [Slot(s, a, "duration", u) for s, a, u in (
        ("Hooly AI Pro", "free_trial", "day"), ("Hooly Jules", "free_trial", "week"),
        ("Hooly Gemini", "median_response_time", "ms"), ("Hooly Gemini", "data_retention", "day"),
        ("Hooly Workspace", "free_trial", "month"), ("Hooly Meet", "max_call_length", "min"),
        ("Hooly Pixel Buds", "battery_life", "h"), ("Hooly Photos", "trash_retention", "day"))],
    "name": [Slot(s, a, "name") for s, a in (
        ("Hooly", "ceo"), ("Hooly", "cto"), ("Hooly Chrome", "lead"), ("Hooly Maps", "lead"),
        ("Hooly Gemini", "cloud_provider"), ("Bertram Gilfoil", "previous_employer"),
        ("Hooly Board", "chair"), ("Hooly Employee Survey", "run_by"))],
    "boolean": [Slot(s, a, "boolean") for s, a in (
        ("Hooly", "soc2_certified"), ("Hooly", "fully_remote"), ("Hooly Gemini", "open_source"),
        ("Hooly Gemini", "eu_hosted"), ("Hooly Docs", "offline_editing"),
        ("Hooly Calendar", "appointment_booking"), ("Hooly Photos", "ai_editing"),
        ("Hooly Workspace Enterprise", "single_sign_on"))],
}
KINDS = tuple(SLOTS)
NAMES = ("Bertram Gilfoil", "Dinesh Chugtay", "Erlich Bachmann", "Holdan", "Hoovar", "Patreese", "Peter Gregori", "Ron LaFlame", "Hooly Cloud", "Brightline Labs")


def attr(slot):
    return slot.attribute.replace("_", " ")


def make_value(slot, rng):
    kind = slot.kind
    value = {"kind": kind}
    if kind in {"quantity", "duration"}:
        value.update(value=str(rng.randrange(3, 180)), unit=slot.unit)
    elif kind == "money":
        value.update(value=f"{rng.randrange(13, 900)}.{rng.randrange(1, 99):02}", currency=rng.choice(("EUR", "USD", "GBP", "RON")))
        if rng.randrange(4): value["per"] = rng.choice(("month", "year", "week"))
    elif kind == "percent":
        value["value"] = f"{rng.randrange(21, 99)}.{rng.randrange(1, 99):02}"
    elif kind == "date":
        value["value"] = f"{rng.randrange(2031, 2040)}-{rng.randrange(1, 13):02}-{rng.randrange(1, 29):02}"
    elif kind == "version":
        parts = [str(rng.randrange(6, 24)), str(rng.randrange(1, 20))]
        if rng.randrange(2): parts.append(str(rng.randrange(1, 18)))
        value["value"] = ".".join(parts)
    elif kind == "name":
        value["value"] = rng.choice(NAMES)
    elif kind == "boolean":
        value["value"] = bool(rng.randrange(2))
    return value


def node(slot, value, op="eq"):
    value = deepcopy(value)
    if op != "eq": value["op"] = op
    return {"type": "atom", "fact": {"subject": slot.subject, "attribute": slot.attribute, "value": value}}


def connective(kind, *children):
    return {"type": kind, "children": list(children)}


def neg(child):
    return {"type": "not", "child": child}


def show(value, style=0):
    raw, kind = value["value"], value["kind"]
    if kind == "quantity":
        noun = value["unit"]
        if noun not in {"GB", "g", "m", "TB", "MB"} and str(raw) != "1": noun += "s"
        return f"{raw}{'' if style % 3 == 1 and noun in {'GB', 'MB', 'TB'} else ' '}{noun}"
    if kind == "duration":
        u = value["unit"]
        spellings = {"ms": "milliseconds", "s": "seconds", "min": "minutes", "h": "hours"}
        u = (spellings.get(u, u + "s") if style % 2 else u)
        return f"{raw} {u}"
    if kind == "money":
        c = value["currency"]
        symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        text = f"{symbols[c]}{raw}" if style % 3 == 1 and c in symbols else f"{c} {raw}"
        return text + (f" per {value['per']}" if value.get("per") else "")
    if kind == "percent": return f"{raw}{' percent' if style % 2 else '%'}"
    if kind == "version": return ("v" if style % 2 == 0 else "version ") + raw
    if kind == "boolean": return "yes" if raw else "no"
    return raw


def operator(op, reserved=False, style=0):
    public = {
        "eq": ("exactly", "equal to", ""), "ne": ("not equal to", "different from"),
        "lt": ("less than", "below"), "le": ("at most", "no more than"),
        "gt": ("greater than", "over"), "ge": ("at least", "no less than"),
    }
    reserved_words = {
        "eq": ("", "equal to"), "ne": ("unequal to", "other than"),
        "lt": ("lower than", "under"), "le": ("not more than", "up to"),
        "gt": ("higher than", "above"), "ge": ("not less than", "a minimum of"),
    }
    options = reserved_words[op] if reserved else public[op]
    return options[style % len(options)]


def clause(atom, style=0, reserved=False, omit_subject=False):
    fact = atom["fact"]
    subject, attribute, value = fact["subject"], fact["attribute"].replace("_", " "), fact["value"]
    op = operator(value.get("op", "eq"), reserved, style)
    tail = " ".join(x for x in (op, show(value, style)) if x)
    if omit_subject: return f"{attribute} is {tail}"
    if reserved:
        options = (f"{subject} reports its {attribute} as {tail}", f"For {subject}, the {attribute} is {tail}",
                   f"The {attribute} for {subject} is {tail}", f"{subject}: {attribute} is {tail}")
    else:
        options = (f"{subject} {attribute} is {tail}", f"The {attribute} of {subject} is {tail}",
                   f"{subject}'s {attribute} is {tail}", f"For {subject}, {attribute} is {tail}")
    return options[style % len(options)]


def altered(value, direction=1):
    result = deepcopy(value)
    result.pop("op", None)
    kind, raw = result["kind"], result["value"]
    if kind in {"quantity", "money", "percent", "duration"}:
        result["value"] = format(Decimal(raw) + Decimal(direction), "f")
    elif kind == "date":
        parts = raw.split("-")
        if len(parts) == 3:
            result["value"] = (date.fromisoformat(raw) + timedelta(days=direction)).isoformat()
        elif len(parts) == 2:
            y, m = map(int, parts)
            y, m = divmod(y * 12 + m - 1 + direction, 12)
            result["value"] = f"{y:04}-{m+1:02}"
        else: result["value"] = str(int(raw) + direction)
    elif kind == "version":
        parts = raw.split(".")
        parts[-1] = str(max(0, int(parts[-1]) + direction))
        if parts[-1] == raw.split(".")[-1]: parts[0] = str(int(parts[0]) + direction)
        result["value"] = ".".join(parts)
    elif kind == "boolean": result["value"] = not raw
    elif kind == "name": result["value"] = next(name for name in NAMES if name != raw)
    return result


def world_for(ast, case_index):
    world, alternatives = [], []
    for fact in ast_facts(ast):
        query = fact["value"]
        if any(old["subject"] == fact["subject"] and old["attribute"] == fact["attribute"]
               and channel(old["channel"]) == channel(query) for old in world): continue
        exact = deepcopy(query)
        exact.pop("op", None)
        op = query.get("op", "eq")
        true_value = altered(query, 1) if op in {"ne", "gt"} else altered(query, -1) if op == "lt" else exact
        false_value = altered(query, 1) if op in {"eq", "le"} else altered(query, -1) if op == "ge" else exact
        world.append({"subject": fact["subject"], "attribute": fact["attribute"], "channel": deepcopy(query), "value": None})
        alternatives.append((true_value, false_value, None))
    if ast and ast["type"] == "compare":
        for index, ref in enumerate((ast["left"], ast["right"])):
            value = {"kind": "quantity", "value": str(17 + 11 * index + case_index % 7), "unit": "language"}
            world.append({**ref, "channel": value, "value": None})
            alternatives.append((value, altered(value, 40), None))
    desired = (True, False, None)[case_index % 3]
    matches = []
    for assignment in product(*alternatives):
        candidate = [{**fact, "value": actual} for fact, actual in zip(world, assignment)]
        if evaluate(ast, candidate) is desired: matches.append(candidate)
    if matches: return matches[(case_index // 3) % len(matches)]
    return world


def generate_case(family, index, rng, reserved):
    """Return (public row, private gold). No text-to-gold inference happens here."""
    slot = rng.choice(SLOTS[KINDS[index % len(KINDS)]])
    value = make_value(slot, rng)
    ast = node(slot, value)
    text = clause(ast, index, reserved) + "."
    status, notes = ["parsed"], []
    context = {"enabled": True, "document_id": "", "prior_texts": []}
    variant = index % 8
    semantic_applicable = True
    morph = None

    if family in {"comparisons", "negated_comparisons"}:
        ops = ("eq", "ne") if slot.kind in {"name", "boolean"} else ("lt", "le", "gt", "ge", "eq", "ne")
        # Index divisors avoid coupling kind and inequality operator.
        op = ops[(index // 8 + index % 3) % len(ops)]
        ast = node(slot, value, op)
        if family == "negated_comparisons":
            ast = neg(ast)
            text = (f"It is false that ({clause(ast['child'], index, reserved)})." if reserved
                    else f"It is not the case that ({clause(ast['child'], index, reserved)}).")
        else:
            text = clause(ast, index, reserved) + "."

    elif family == "multi_entity":
        kind = KINDS[(index // 4) % 8]
        special_pairs = {
            "quantity": [Slot("Hooly Drive", "free_storage", kind, "GB"), Slot("Hooly Photos", "free_storage", kind, "GB")],
            "percent": [Slot("Hooly Cloud", "uptime_sla", kind), Slot("Hooly Workspace", "uptime_sla", kind)],
            "duration": [Slot("Hooly AI Pro", "free_trial", kind, "day"), Slot("Hooly Jules", "free_trial", kind, "day")],
            "name": [Slot("Hooly Maps", "lead", kind), Slot("Hooly Chrome", "lead", kind)],
            "boolean": [Slot("Hooly Gemini", "single_sign_on", kind), Slot("Hooly Workspace Enterprise", "single_sign_on", kind)],
        }
        pair = special_pairs.get(kind)
        if pair is None:
            eligible = [s for s in SLOTS[kind] if s.attribute == {"version": "version", "date": "launched", "money": "price"}[kind]]
            pair = rng.sample(eligible, 2)
        left, right = [node(s, make_value(s, rng)) for s in pair]
        ast = connective("all", left, right)
        if variant in {0, 3, 6}:
            text = f"The {attr(pair[0])} values for {pair[0].subject} and {pair[1].subject} are {show(left['fact']['value'])} and {show(right['fact']['value'])}, respectively."
        else:
            join = "; meanwhile, " if reserved else "; "
            text = clause(left, index, reserved) + join + clause(right, index + 1, reserved) + "."

    elif family == "multi_clause":
        s = Slot("Hooly Gemini", "languages", "quantity", "language")
        t = Slot("Hooly Gemini", "median_response_time", "duration", "ms")
        u = Slot("Hooly Gemini", "api_version", "version")
        children = [node(x, make_value(x, rng)) for x in (s, t, u)[:2 + index % 2]]
        if variant == 7:
            ast = {"type": "compare", "left": {"subject": "Hooly Docs", "attribute": "languages"},
                   "op": ("gt" if index % 2 else "le"), "right": {"subject": "Hooly Gemini", "attribute": "languages"}}
            text = f"The languages of Hooly Docs are {'greater than' if ast['op']=='gt' else 'at most'} the languages of Hooly Gemini."
        else:
            ast = connective("all", *children)
            text = clause(children[0], index, reserved) + ", and its " + ", and its ".join(clause(x, index, reserved, True) for x in children[1:]) + "."

    elif family == "nested_scope":
        specs = tuple(rng.choice(SLOTS[KINDS[(index + shift) % 8]]) for shift in (0, 3, 5))
        a, b, c = [node(s, make_value(s, rng), rng.choice(("eq", "ne"))) for s in specs]
        ca, cb, cc = [clause(x, index, reserved) for x in (a, b, c)]
        forms = [
            (connective("any", a, connective("all", b, c)), f"({ca}) or (({cb}) and ({cc}))"),
            (connective("all", connective("any", a, b), c), f"(({ca}) or ({cb})) and ({cc})"),
            (neg(connective("any", a, b)), f"not (({ca}) or ({cb}))"),
            (neg(connective("all", a, b)), f"not (({ca}) and ({cb}))"),
            (connective("any", neg(a), connective("all", b, neg(c))), f"(not ({ca})) or (({cb}) and (not ({cc})))"),
            (connective("all", a, neg(connective("any", b, c))), f"({ca}) and (not (({cb}) or ({cc})))"),
            (neg(neg(connective("any", a, c))), f"not (not (({ca}) or ({cc})))"),
            (connective("all", neg(a), connective("any", neg(b), c)), f"(not ({ca})) and ((not ({cb})) or ({cc}))"),
        ]
        ast, text = forms[variant]
        text += "."

    elif family == "version_binding":
        s, t = Slot("Hooly Gemini", "api_version", "version"), Slot("Hooly Gemini", "version", "version")
        av, pv = make_value(s, rng), make_value(t, rng)
        if av["value"] == pv["value"]: pv = altered(pv)
        a, b = node(s, av), node(t, pv)
        ast = connective("all", a, b)
        if variant % 3 == 0:
            text = f"Hooly Gemini's API version is {show(av)}, and its product version is {show(pv)}."
        elif variant % 3 == 1:
            text = f"The product version of Hooly Gemini is {show(pv)}; its API version is {show(av)}."
        else:
            text = f"Hooly Gemini uses API {show(av)} and product {show(pv)}."

    elif family == "object_distractors":
        subject = rng.choice(("Hooly Maps", "Hooly Chrome", "Hooly Jules"))
        s = Slot(subject, "lead", "name")
        value = {"kind": "name", "value": rng.choice(("Bertram Gilfoil", "Ron LaFlame", "Dinesh Chugtay"))}
        ast = node(s, value)
        if variant % 4 == 0:
            text = f"{value['value']} is the lead of {subject}."
        elif variant % 4 == 1:
            text = f"The lead of {subject}, unlike Hooly Docs, is {value['value']}."
        elif variant % 4 == 2:
            text = f"{subject} has {value['value']} as its lead."
        else:
            text = f"{subject}'s lead is {value['value']} (reference only: Hooly Calendar)."

    elif family in {"pronouns_enabled", "document_bounds"}:
        s = rng.choice(SLOTS[KINDS[index % 8]])
        value = make_value(s, rng)
        ast = node(s, value)
        context["enabled"] = family == "pronouns_enabled" or variant % 4 == 1
        context["prior_texts"] = [f"Record subject: {s.subject}."]
        text = f"Its {attr(s)} is {show(value, index)}."
        if family == "document_bounds":
            status, notes, ast, semantic_applicable = ["unresolved", "ambiguous"], ["subject"], None, False
            if variant % 4 == 0: context["enabled"] = False
            if variant % 4 == 1: context["different_document"] = True
            if variant % 4 == 2: context["prior_texts"] = []
            if variant % 4 == 3:
                s = Slot("Hooly Drive", "free_storage", "quantity", "GB")
                value = make_value(s, rng)
                text = f"Its free storage is {show(value, index)}."
                context["enabled"] = True
                context["prior_texts"] = ["Record subject: Hooly Drive and Hooly Photos."]
                notes = ["ambigu"]

    elif family == "ambiguous_ownership":
        a, b = rng.sample([s.subject for s in SLOTS["version"] if s.attribute == "version"], 2)
        v = show(value if value["kind"] == "version" else {"kind": "version", "value": f"{rng.randrange(7,20)}.4"})
        options = (
            f"{a} mentioned {b}. Its version is {v}.",
            f"During a discussion of {a} and {b}, its version was given as {v}.",
            f"The version is {v}; {a} and {b} are under discussion.",
            f"{a} and {b} were compared. The product's version is {v}.",
        )
        text = options[variant % len(options)]
        status, notes, ast, semantic_applicable = ["ambiguous", "unresolved"], ["ambigu"], None, False

    elif family == "missing_values":
        slot = rng.choice(SLOTS[KINDS[(index + index // 4) % 8]])
        value = make_value(slot, rng)
        if variant % 4 == 0:
            text = f"{slot.subject}'s {attr(slot)} is not recorded."
            status, notes, ast, semantic_applicable = ["unresolved"], ["unknown"], None, False
        elif variant % 4 == 1:
            text = f"{slot.subject}'s {attr(slot)} is unknown."
            status, notes, ast, semantic_applicable = ["unresolved"], ["unknown"], None, False
        elif variant % 4 == 2:
            slot = rng.choice(SLOTS[("quantity", "money", "percent", "duration")[(index // 4) % 4]])
            value = make_value(slot, rng)
            text = f"{slot.subject}'s {attr(slot)} is about {show(value, index)}."
            status, notes, ast, semantic_applicable = ["unresolved"], ["approx"], None, False
        else:
            s = Slot("Hooly Docs", "version", "version")
            ast = node(s, make_value(s, rng))
            text = clause(ast, index, reserved) + "; its launched date is not recorded."
            status, notes, semantic_applicable = ["partial"], ["unknown"], False

    elif family == "raw_precision":
        kind = ("quantity", "money", "percent", "duration")[index % 4]
        slot = rng.choice(SLOTS[kind])
        value = make_value(slot, rng)
        decimals = ("9007199254740993.0001", "123456789.123456789123456789", "0.000000000000000137", "42.1234567890123456789")
        value["value"] = decimals[(index // 4) % len(decimals)]
        if kind == "percent": value["value"] = ("99.999", "99.999999999999999999", "0.000000000000000137", "42.1234567890123456789")[(index // 4) % 4]
        ast = node(slot, value, ("eq", "le", "ge", "ne")[(index // 8) % 4])
        text = clause(ast, index, reserved) + "."

    elif family == "units_and_billing":
        if variant % 4 == 0:
            s = rng.choice(SLOTS["money"])
            amount = str(rng.randrange(11, 400))
            a = node(s, {"kind": "money", "value": amount, "currency": "EUR", "per": "month"})
            b = node(s, {"kind": "money", "value": amount, "currency": "EUR", "per": "year"})
            ast = connective("any" if variant == 4 else "all", a, b)
            text = clause(a, index, reserved) + (" or " if variant == 4 else " and ") + clause(b, index + 1, reserved) + "."
        elif variant % 4 == 1:
            s = Slot("Hooly AI Pro", "price", "money")
            a = node(s, {"kind": "money", "value": str(rng.randrange(11, 80)), "currency": "USD"})
            b = node(Slot("Hooly Jules", "price", "money"), {"kind": "money", "value": str(rng.randrange(11, 80)), "currency": "EUR", "per": "month"})
            ast = connective("all", a, b)
            text = clause(a, index, reserved) + "; " + clause(b, index + 1, reserved) + "."
        elif variant % 4 == 2:
            slot = Slot("Hooly Drive", "free_storage", "quantity", rng.choice(("GB", "MB", "TB")))
            ast = node(slot, make_value(slot, rng))
            text = clause(ast, index, reserved) + "."
        else:
            slot = Slot("Hooly AI Pro", "free_trial", "duration", rng.choice(("day", "week", "month", "year")))
            ast = node(slot, make_value(slot, rng), "le")
            text = clause(ast, index, reserved) + "."

    elif family == "punctuation":
        if variant % 2:
            slot = Slot("Hooly Gemini", "version", "version")
            value = {"kind": "version", "value": f"{rng.randrange(8, 20)}.{rng.randrange(1, 20)}.{rng.randrange(1, 10)}"}
            ast = node(slot, value)
            prefix = ("version ", "ver. ", "v", "")[(index // 2) % 4]
            if variant == 5:
                value["value"] = ".".join(value["value"].split(".")[:2])
                ast = node(slot, value)
                text = f"Hooly Gemini {value['value']}."
            else:
                text = f"Hooly Gemini version is {prefix}{value['value']}."
        else:
            slot = rng.choice(SLOTS["date"])
            value = make_value(slot, rng)
            precision = (index // 8) % 3
            if precision == 0: value["value"] = value["value"][:4]
            elif precision == 1: value["value"] = value["value"][:7]
            ast = node(slot, value)
            d = date.fromisoformat((value["value"] + "-01-01")[:10])
            if len(value["value"]) == 4: forms = (value["value"],) * 4
            elif len(value["value"]) == 7: forms = (d.strftime("%B %Y"), d.strftime("%b. %Y"), value["value"], d.strftime("%b %Y"))
            else: forms = (d.strftime("%d %b. %Y"), d.strftime("%B %d, %Y"), value["value"], d.strftime("%d %B %Y"))
            text = f"{slot.subject} {attr(slot)} is {forms[(index // 2) % 4]}."
            if index % 16 == 0:
                ast = node(Slot("Hooly", "founded", "date"), value)
                text = f"Hooly Inc. founded is {value['value']}."
        if index % 5 == 0: text = text.replace("Hooly Gemini", "Gemini")

    elif family == "metamorphic":
        # Paired public bytes (except IDs) and opposite/private-unknown worlds.
        pair_rng = random.Random("pair:" + str(index // 2) + (":reserved" if reserved else ":dev"))
        slot = rng.choice(SLOTS[KINDS[(index // 2) % len(KINDS)]])
        # Slot and wording are deterministic per pair, independent of IDs.
        slot = SLOTS[slot.kind][pair_rng.randrange(len(SLOTS[slot.kind]))]
        ast = node(slot, make_value(slot, pair_rng))
        text = clause(ast, index // 2, reserved) + "."
        morph = f"truth-pair-{index//2}"

    identity = secrets.token_hex(12)
    document_id = "doc-" + secrets.token_hex(10)
    different_document = context.pop("different_document", False)
    context["document_id"] = "prior-" + secrets.token_hex(10) if different_document else document_id
    row = {"id": identity, "document_id": document_id, "text": text, "context": context}
    world = world_for(ast, index if family != "metamorphic" else index % 2)
    truth = label(evaluate(ast, world)) if semantic_applicable else None
    gold = {"id": identity, "family": family, "variant": variant, "acceptable_statuses": status,
            "ast": ast, "assertions": assertions(ast), "note_categories": notes,
            "world": world, "semantic_truth": truth, "metamorphic_group": morph}
    return row, gold


def build_cases(split, seed, count_per_family=None):
    rng = random.Random(seed)
    count = count_per_family or COUNTS[split]
    result = [generate_case(family, index, rng, split == "final") for family in FAMILIES for index in range(count)]
    # Keep metamorphic pairs adjacent so adapters can test document resets in stream order.
    blocks = []
    index = 0
    while index < len(result):
        size = 2 if result[index][1]["family"] == "metamorphic" else 1
        blocks.append(result[index:index+size])
        index += size
    rng.shuffle(blocks)
    result = [case for block in blocks for case in block]
    return [row for row, _ in result], [gold for _, gold in result]


def write_bundle(output, split, seed=None):
    output = require_artifacts(output)
    if output.exists(): raise ValueError("refusing to overwrite an existing bundle")
    if split == "final" and seed is not None: raise ValueError("a final seed must come from the OS")
    seed = seed or secrets.token_hex(32)
    rows, gold = build_cases(split, seed)
    lexicon = load_json(ROOT / "data/lexicon.json")
    for item in gold: validate_ast(item["ast"], lexicon)
    from .audit import audit_cases
    audit_cases(rows, gold, lexicon)
    public, private = output / "public", output / "private"
    write_jsonl(public / "input.jsonl", rows)
    write_json(public / "lexicon.json", lexicon)
    write_json(public / "interface.schema.json", load_json(Path(__file__).with_name("interface.schema.json")))
    write_json(public / "adapter_variants.json", {
        "input_features": ["text", "document_id", "context.enabled", "context.document_id", "context.prior_texts"],
        "candidate_source": "frozen input-only value grammar; never prebound owners or attributes",
        "variants": ["reverse_candidates", "shuffle_candidates", "replace_candidate_ids", "inject_untrusted_gold_fields", "reverse_document_order"],
        "invariants": "status, resolved subject/attribute and normalized AST independent of nuisance candidate order/IDs/gold fields; no pronouns across document boundaries",
    })
    write_json(public / "POLICY.json", {
        "version": "parser-v3-challenge-1", "provenance": PROVENANCE,
        "context": "Prior texts are eligible only when context.enabled and context.document_id equals row.document_id; every row has explicit document bounds. Multiple possible antecedents require abstention.",
        "semantics": "Strong Kleene all/any/not; exact rational numerics; money currency and billing separate; calendar durations separate from fixed days; date precision retained; version numeric tuples retain component count.",
        "output": "JSONL {id,status:parsed|partial|unresolved|ambiguous,ast,assertions:[Fact],notes:[string]}; atom {type:atom,fact:{subject,attribute,value}}; all/any children; not child; compare left/op/right fact references",
        "values": "Eight kinds; numeric values may be exact JSON decimals or strings; no binary-float rounding is forgiven. Fact value.op defaults eq. Logical negation may be represented by not or inverted operators.",
        "assertions": "Negation-normal-form atom leaf set; all/any scope is scored separately. Compare reference nodes add no fabricated constant assertions.",
        "abstention": "Genuinely ambiguous or missing language has no chosen subject ID. Empty assertions plus ambiguous/unresolved status and a diagnostic are acceptable according to private expected categories.",
        "evaluation_only": split == "final",
    })
    write_jsonl(private / "gold.jsonl", gold)
    write_json(private / "generation.json", {"seed": seed, "split": split, "family_counts": dict(Counter(g["family"] for g in gold)), "provenance": PROVENANCE})
    source_hashes = {path.name: digest(path) for path in sorted(Path(__file__).parent.glob("*.py"))}
    manifest = {
        "format": "parser-v3-challenge-1", "split": split, "rows": len(rows),
        "created_utc": datetime.now(timezone.utc).isoformat(), "provenance": PROVENANCE,
        "public_sha256": public_hashes(output), "public_bundle_sha256": public_digest(output),
        "gold_sha256": digest(private / "gold.jsonl"), "lexicon_source_sha256": digest(ROOT / "data/lexicon.json"),
        "factory_source_sha256": source_hashes,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "final"), required=True)
    parser.add_argument("--seed", help="development only; final generation always uses the OS")
    args = parser.parse_args()
    manifest = write_bundle(args.output, args.split, args.seed)
    # No labels, reserved wording, or final seed are printed.
    print(f"{args.split}: {manifest['rows']} rows, public SHA-256 {manifest['public_bundle_sha256']}")


if __name__ == "__main__": main()
