"""Build fresh, independently seeded counterfactual worlds using public names.

Only the published lexicon and contracts constrain the schema. No practice
values, former benchmark, production implementation, or model are imported.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import secrets
import subprocess
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

from .grammar import (DATE_OPERATOR_PHRASES, OPERATOR_PHRASES, decimal_text,
                      parse_value, render_value)
from .oracle import (DURATION_UNITS, OPERATORS, QUANTITY_UNITS, OracleError, World,
                     channel, compare, partial_date, rational, resolve_public_context)


ROOT = Path(__file__).resolve().parents[2]
SCOPE_START, SCOPE_END = date(2024, 1, 1), date(2027, 12, 31)
SCHEMA = "veridyct-independent-world-v1"

# Only public names/attributes, not organizer factual values. Each base unit
# fixes a dimension; money has three independently generated channels.
SPECS = [
    ("Hooly", "employees", "quantity", "employee"),
    ("Hooly", "paying_customers", "quantity", "customer"),
    ("Hooly AI Free", "max_upload_size", "quantity", "MB"),
    ("Hooly Drive", "free_storage", "quantity", "GB"),
    ("Hooly Maps", "mapped_distance", "quantity", "km"),
    ("Hooly Pixel 10", "weight", "quantity", "g"),
    ("Hooly Pixel 10 Pro", "charging_power", "quantity", "W"),
    ("Hooly Pixel 10", "battery_capacity", "quantity", "mAh"),
    ("Hooly Docs", "languages", "quantity", "language"),
    ("Hooly Workspace", "included_seats", "quantity", "seat"),
    ("Hooly Pixel 10", "screen_size", "quantity", "in"),
    ("Hooly Chrome", "monthly_active_users", "quantity", "user"),
    ("Hooly Cloud", "regions", "quantity", "region"),
    ("Hooly Pixel 10", "refresh_rate", "quantity", "Hz"),
    ("Hooly AI Pro", "price", "money", "month"),
    ("Hooly Workspace", "price", "money", "month"),
    ("Hooly Workspace Enterprise", "price", "money", "month"),
    ("Hooly Jules", "price", "money", "month"),
    ("Hooly Photos Lite", "price", "money", "month"),
    ("Hooly Pixel 10", "price", "money", "once"),
    ("Hooly Berlin Office", "rent", "money", "month"),
    ("Hooly Photos Max", "price", "money", "month"),
    ("Hooly Cloud", "uptime_sla", "percent", ""),
    ("Hooly Gemini", "flawbench_score", "percent", ""),
    ("Hooly Chrome", "browser_market_share", "percent", ""),
    ("Hooly Employee Survey", "response_rate", "percent", ""),
    ("Hooly Photos", "yearly_billing_discount", "percent", ""),
    ("Hooly", "support_satisfaction", "percent", ""),
    ("Hooly Maps", "share_of_ad_revenue", "percent", ""),
    ("Hooly Translate", "rated_accuracy", "percent", ""),
    ("Hooly", "founded", "date", ""),
    ("Hooly Docs", "launched", "date", ""),
    ("Hooly Maps", "latest_release_date", "date", ""),
    ("Hooly Pixel 10", "released", "date", ""),
    ("Hooly I/O 2026", "date", "date", ""),
    ("Hooly Hiring Programme", "launched", "date", ""),
    ("Hooly Sustainability Report", "published", "date", ""),
    ("Hooly Board", "next_meeting", "date", ""),
    ("Bertram Gilfoil", "joined", "date", ""),
    ("Hooly Vault", "announced", "date", ""),
    ("Hooly Android", "version", "version", ""),
    ("Hooly Calendar", "version", "version", ""),
    ("Hooly Chrome", "stable_version", "version", ""),
    ("Hooly Cloud", "cli_version", "version", ""),
    ("Hooly Docs", "version", "version", ""),
    ("Hooly Gemini", "version", "version", ""),
    ("Hooly Jules", "version", "version", ""),
    ("Hooly Sheets", "version", "version", ""),
    ("Hooly AI Pro", "free_trial", "duration", "day"),
    ("Hooly AI Pro", "refund_window", "duration", "day"),
    ("Hooly AI Pro", "support_first_response", "duration", "min"),
    ("Hooly AI Pro", "history_retention", "duration", "month"),
    ("Hooly Chrome", "cold_start_time", "duration", "ms"),
    ("Hooly Chrome", "release_cadence", "duration", "week"),
    ("Hooly Cloud", "median_time_to_recover", "duration", "min"),
    ("Hooly Gemini", "median_response_time", "duration", "s"),
    ("Hooly Meet", "max_call_length", "duration", "h"),
    ("Hooly Photos", "trash_retention", "duration", "day"),
    ("Hooly Pixel 10", "battery_life", "duration", "h"),
    ("Hooly Hiring Programme", "time_to_hire", "duration", "week"),
    ("Hooly", "ceo", "name", ""),
    ("Hooly", "cto", "name", ""),
    ("Hooly", "head_of_security", "name", ""),
    ("Hooly Gemini", "cloud_provider", "name", ""),
    ("Hooly Android", "lead", "name", ""),
    ("Hooly Maps", "lead", "name", ""),
    ("Hooly Cloud", "reliability_lead", "name", ""),
    ("Hooly Hiring Programme", "executive_sponsor", "name", ""),
    ("Hooly", "soc2_certified", "boolean", ""),
    ("Hooly", "fully_remote", "boolean", ""),
    ("Hooly Cloud", "carbon_neutral", "boolean", ""),
    ("Hooly Docs", "offline_editing", "boolean", ""),
    ("Hooly Android", "open_source", "boolean", ""),
    ("Hooly Gemini", "encryption_at_rest", "boolean", ""),
    ("Hooly Meet", "cloud_recording", "boolean", ""),
    ("Hooly Pixel Buds", "adaptive_noise_cancelling", "boolean", ""),
    ("Hooly Photos", "ai_editing", "boolean", ""),
    ("Hooly Board", "audit_committee", "boolean", ""),
    ("Hooly Search", "ai_answers", "boolean", ""),
    ("Hooly Workspace", "copilot_included", "boolean", ""),
]
NAME_POOL = ("Bertram Gilfoil", "Dinesh Chugtay", "Erlich Bachmann", "Holdan", "Hoovar",
             "Patreese", "Peter Gregori", "Ron LaFlame", "Brightline Labs", "Meridian Health")

POLICY = """# Independent counterfactual temporal-world evaluation v1

This is synthetic test data, never official Hooly evidence. All values are
invented independently of practice truths and former evaluation worlds. The
public lexicon is used only for names, aliases and legal attributes. Development
construction/code used OpenAI Codex LLM assistance; no runtime LLM is used.

The CSV has only id,text,date,label. True-labelled anchors are the entire public
evidence. Blank labels are targets. In every anchor, `From YYYY-MM-DD through
YYYY-MM-DD` gives an INCLUSIVE validity interval; the CSV date is only its page
publication date and never extends or replaces that interval. Intervals cover
2024-01-01 through 2027-12-31. An anchor saying `explicitly unrecorded (unknown)`
declares a world gap, not a false value. Gaps are not forward-filled. There is no
outside-scope test. Multiple anchors can repeat the same interval consistently.

Target assertions are evaluated on their CSV date. `and`/`; and` joins a
conjunction: any false component makes the row false, otherwise any explicit
unknown component makes it unsure, otherwise it is true. Failure to extract a
known statement does not make its gold unsure. The three classes are target
truth labels, not parser-status labels.

The bounded language contains possessive, attribute-first, record/catalog,
value-first and topical forms, explicit comparisons, conjunctions, aliases,
unique same-paragraph pronouns and explicitly marked identifier distractors.
`Record subject: NAME.` declares the only antecedent for `It`/`Its` in that same
row. context.json records actual Unicode code-point, half-open declaration and
claim spans and document boundaries; it contains no hidden antecedent field.
`Document reference: NUMBER (identifier only).` adds no assertion. No context
crosses rows or documents. Ordinary English beyond these documented families is
not covered, and this test cannot establish open-domain language accuracy.

Kinds: quantity, money, percent, date, version, duration, name and boolean.
Numbers use exact decimal/rational arithmetic. Physical quantities use decimal
SI conversion (1 GB = 1000 MB; 1 inch = 0.0254 m). Counted nouns are separate
dimensions. Fixed durations convert ms/s/min/h/day/week; 1 year = 12 months in a
separate calendar dimension, with no month/day conversion. Money currency and
billing period form independent channels: EUR/month is neither EUR/year,
USD/month nor a once-only payment, and annual totals are not inferred. All three
generated channels for every money attribute are explicitly covered by anchors.

Operators: eq, ne, lt, le, gt, ge. `ne` (different from/not equal to) is an explicit
INPUT evaluation extension; the official claimed_value submission schema has
only the other five operators. Names/booleans use only eq/ne. Boolean literals
yes/no give the stated attribute's polarity. Negated comparison phrases such as
`no more than` remain le, not independent boolean negations.

Dates retain exactly their written precision: 2026 differs from 2026-03 and from
2026-03-01. Ordering tests use equal date precision, ordered chronologically;
mixed-precision ordering is outside the factory. Versions are numeric component
tuples compared AS WRITTEN: 2.3 != 2.3.0 and 2.10 > 2.9. No zero padding and no
prerelease/build-metadata syntax is used. Name aliases resolve via the lexicon.

Ambiguous numeric spellings/ranges/approximations and arbitrary prose are not
assigned unsure merely because a parser cannot interpret them. The independent
grammar rejects unsupported semantics. Unknown targets exist only in published
unknown intervals. Hard surface forms with known evidence still have true/false
gold labels and any abstention on them is an extraction/reasoning failure.

Use development/public and its released gold for development only. Sealed public
inputs are evaluation-only, never training/model selection. Sealed gold and seeds
remain private until a coordinator-confirmed source/model freeze and one-shot
evaluation. Source/seed provenance and gold are stored separately from public.

Sampler revision 3 pairs each primary slot and nuisance draw with all three row
labels. Style, context, distractor presence, arity and boundary sampling come from
a separate random stream, shared across each three-label triplet before rows are
shuffled. Intervals use independently randomized positive duration partitions,
not common seasonal change dates. The final incomplete triplet can add at most
two rows. This prevents the retired prototypes' slot/distractor class shortcuts;
it does not prove freedom from every synthetic-language bias. Sealed sets add 12
wording families beyond development's 12; their gold is never tuning material.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_hashes(directory: Path) -> dict[str, str]:
    return {name: sha256(directory / name)
            for name in ("universe.csv", "lexicon.json", "context.json", "POLICY.md")}


def digest_hashes(hashes: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{name}:{value}\n" for name, value in sorted(hashes.items())).encode()).hexdigest()


def source_hashes() -> dict[str, str]:
    return {path.name: sha256(path) for path in sorted(Path(__file__).parent.glob("*.py"))}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def opaque_id(seed: str, category: str, counter: int) -> str:
    digest = hashlib.sha256(f"{seed}:{category}:{counter}".encode()).hexdigest()[:24]
    return f"{category}-{digest}"


def random_value(spec: tuple, rng: random.Random) -> dict:
    _, attribute, kind, unit = spec
    result: dict = {"kind": kind}
    if kind == "quantity":
        maxima = {"employee": 9999, "customer": 999999, "MB": 256, "GB": 4096,
                  "km": 999999, "g": 1800, "W": 240, "mAh": 9999,
                  "language": 98, "seat": 98, "in": 120, "user": 9999999,
                  "region": 98, "Hz": 240}
        value = Fraction(rng.randint(2, maxima[unit]), 10 if unit == "in" else 1)
        result.update(value=decimal_text(value), unit=unit)
    elif kind == "money":
        result.update(value=decimal_text(Fraction(rng.randint(101, 299999), 100)), currency="EUR")
        if unit != "once":
            result["per"] = unit
    elif kind == "percent":
        result["value"] = decimal_text(Fraction(rng.randint(1, 99999), 1000))
    elif kind == "date":
        actual = date(2020, 1, 1) + timedelta(days=rng.randrange(4000))
        precision = rng.choice((4, 7, 10))
        result["value"] = actual.isoformat()[:precision]
    elif kind == "version":
        components = [rng.randint(2, 23), rng.choice((0, 2, 3, 9, 10, 11, 21))]
        components.extend(rng.choice((0, 1, 2, 9, 10)) for _ in range(rng.randrange(3)))
        result["value"] = ".".join(map(str, components))
    elif kind == "duration":
        result.update(value=decimal_text(Fraction(rng.randint(10, 2400), 10)), unit=unit)
    elif kind == "name":
        result["value"] = rng.choice(NAME_POOL)
    elif kind == "boolean":
        result["value"] = bool(rng.randrange(2))
    else:
        raise OracleError(f"no factory for {attribute}/{kind}")
    return result


def make_world(seed: str, lexicon: dict) -> World:
    rng = random.Random(int(seed, 16))
    total_days = (SCOPE_END - SCOPE_START).days + 1
    timelines = []
    for spec in SPECS:
        exemplar = random_value(spec, rng)
        channels = [exemplar]
        if spec[2] == "money":
            alternate = "year" if exemplar.get("per") != "year" else "month"
            channels += [dict(exemplar, per=alternate), dict(exemplar, currency="USD")]
        for exemplar in channels:
            cursor, segments = SCOPE_START, []
            gap_lengths = [rng.randint(10, 35) for _ in range(7)]
            known_days = total_days - sum(gap_lengths)
            weights = [rng.randint(1, 100) for _ in range(8)]
            extra = known_days - 8 * 45
            known_lengths = [45 + extra * weight // sum(weights) for weight in weights]
            known_lengths[-1] += known_days - sum(known_lengths)
            for interval in range(8):
                end = cursor + timedelta(days=known_lengths[interval] - 1)
                value = random_value(spec, rng)
                if spec[2] == "money":
                    value["currency"] = exemplar["currency"]
                    if "per" in exemplar:
                        value["per"] = exemplar["per"]
                    else:
                        value.pop("per", None)
                segments.append({"start": cursor.isoformat(), "end": end.isoformat(), "value": value})
                cursor = end + timedelta(days=1)
                if interval < 7:
                    end = cursor + timedelta(days=gap_lengths[interval] - 1)
                    segments.append({"start": cursor.isoformat(), "end": end.isoformat(),
                                     "value": None, "reason": "explicit_gap"})
                    cursor = end + timedelta(days=1)
            timelines.append({"subject": spec[0], "attribute": spec[1], "channel": channel(exemplar),
                              "segments": segments})
    return World(timelines, lexicon)


def equivalent_surface(value: dict, rng: random.Random) -> dict:
    result = dict(value)
    kind = value["kind"]
    if kind not in ("quantity", "duration"):
        return result
    table = QUANTITY_UNITS if kind == "quantity" else DURATION_UNITS
    if value["unit"] not in table:
        return result
    dimension, factor = table[value["unit"]]
    candidates = []
    for unit, (other_dimension, other_factor) in table.items():
        if dimension == other_dimension:
            amount = rational(value["value"]) * factor / other_factor
            try:
                text = decimal_text(amount)
            except OracleError:
                continue
            if len(text) < 22:
                candidates.append((unit, text))
    result["unit"], result["value"] = rng.choice(candidates)
    return result


def shifted(value: dict, direction: int) -> dict:
    result, kind = dict(value), value["kind"]
    if kind in ("quantity", "money", "percent", "duration"):
        step = Fraction(1, 100) if kind in ("money", "percent") else Fraction(1, 10)
        result["value"] = decimal_text(rational(value["value"]) + direction * step)
    elif kind == "date":
        bits = partial_date(value["value"])
        if len(bits) == 1:
            result["value"] = str(bits[0] + direction)
        elif len(bits) == 2:
            index = bits[0] * 12 + bits[1] - 1 + direction
            result["value"] = f"{index // 12:04}-{index % 12 + 1:02}"
        else:
            result["value"] = (date(*bits) + timedelta(days=direction)).isoformat()
    elif kind == "version":
        bits = value["value"].split(".")
        bits[0] = str(int(bits[0]) + direction)
        result["value"] = ".".join(bits)
    elif kind == "name":
        result["value"] = NAME_POOL[(NAME_POOL.index(value["value"]) + 1) % len(NAME_POOL)]
    elif kind == "boolean":
        result["value"] = not value["value"]
    return result


def assertion_for(world: World, key: tuple, at: str, wanted: str, rng: random.Random) -> dict:
    segments = world.timelines[key]
    segment = next(segment for segment in segments if segment.start <= date.fromisoformat(at) <= segment.end)
    actual = segment.value or rng.choice([segment.value for segment in segments if segment.value is not None])
    op = rng.choice(OPERATORS if actual["kind"] not in ("name", "boolean") else ("eq", "ne"))
    value = dict(actual)
    if wanted != "unsure":
        if (op == "eq" and wanted == "false") or (op == "ne" and wanted == "true"):
            # Explicitly exercise the official unpadded version distinction.
            if actual["kind"] == "version" and len(actual["value"].split(".")) < 4 and rng.random() < .35:
                value["value"] += ".0"
            else:
                value = shifted(actual, 1)
        elif op in ("lt", "gt", "le", "ge"):
            directions = {("lt", "true"): 1, ("lt", "false"): 0,
                          ("le", "true"): rng.choice((0, 1)), ("le", "false"): -1,
                          ("gt", "true"): -1, ("gt", "false"): 0,
                          ("ge", "true"): rng.choice((0, -1)), ("ge", "false"): 1}
            direction = directions[(op, wanted)]
            value = shifted(actual, direction) if direction else value
    value = equivalent_surface(value, rng)
    result = {"subject": key[0], "attribute": key[1], "value": value, "op": op}
    got, _ = world.evaluate(result, at)
    if got != wanted:
        raise OracleError(f"factory predicate construction failed: {got} != {wanted}")
    return result


def render_clause(assertion: dict, style: int, spelling: str, rng: random.Random,
                  *, pronoun: bool = False, heldout: bool = False) -> str:
    attribute = assertion["attribute"].replace("_", " ")
    if "soc2" in attribute:
        attribute = attribute.replace("soc2", "SOC 2")
    value = render_value(assertion["value"], rng.randrange(42))
    parsed = parse_value(value, assertion["value"]["kind"], rng.aliases)
    if compare(parsed, assertion["value"], "eq", rng.aliases) != "true":
        raise OracleError("rendered isolated value changed its exact semantics")
    phrase_table = DATE_OPERATOR_PHRASES if heldout and assertion["value"]["kind"] == "date" else OPERATOR_PHRASES
    phrase = rng.choice(phrase_table[assertion["op"]])
    value = phrase + value
    if pronoun:
        options = [f"Its {attribute} is {value}", f"It records {value} for {attribute}",
                   f"Its entry lists {attribute} as {value}", f"It has {value} as its {attribute}"]
        return options[style % len(options)]
    options = [
        f"{spelling}'s {attribute} is {value}",
        f"The {attribute} of {spelling} is {value}",
        f"{spelling} records {value} for {attribute}",
        f"For {spelling}, the recorded {attribute} stands at {value}",
        f"{value} is the recorded {attribute} for {spelling}",
        f"{spelling}: {attribute}, {value}",
        f"The register gives {spelling} a {attribute} of {value}",
        f"Concerning {spelling}, {attribute} reads {value}",
        f"{spelling} has {value} as its {attribute}",
        f"{spelling}'s entry lists {attribute} as {value}",
        f"A check of {spelling} finds {attribute} at {value}",
        f"As recorded for {spelling}, {attribute} is {value}",
        f"{spelling} reports a {attribute} value of {value}",
        f"For the {attribute} entry, {spelling} is recorded at {value}",
        f"The ledger lists {attribute} for {spelling} as {value}",
        f"{spelling} is assigned {value} under {attribute}",
        f"An entry for {spelling} gives {attribute}: {value}",
        f"The value recorded against {spelling}'s {attribute} is {value}",
        f"{attribute.capitalize()} for {spelling} is listed as {value}",
        f"The register entry {spelling} / {attribute} reads {value}",
        f"The {attribute} field for {spelling} records {value}",
        f"{spelling}'s record gives {value} under the heading {attribute}",
        f"In the ledger, {spelling} has a {attribute} value of {value}",
        f"For {spelling}, {attribute} has the recorded value {value}",
    ]
    return options[style % (24 if heldout else 12)]


def money_descriptor(slot: str) -> str:
    if not slot.startswith("money:"):
        return ""
    _, currency, period = slot.split(":")
    return f" [{currency}, {'one-off' if period == 'once' else 'per ' + period}]"


def anchor_text(key: tuple, segment, style: int) -> str:
    subject, attribute, slot = key
    prefix = f"From {segment.start} through {segment.end}, "
    attribute = attribute.replace("_", " ") + money_descriptor(slot)
    if segment.value is None:
        return prefix + f"{subject}'s {attribute} is explicitly unrecorded (unknown)."
    value = render_value(segment.value, style)
    choices = [f"{subject}'s {attribute} is {value}.",
               f"the {attribute} of {subject} is {value}.",
               f"{subject} records {value} for {attribute}."]
    return prefix + choices[style % 3]


def make_dataset(world: World, seed: str, target_count: int, anchor_count: int = 1897,
                 *, heldout: bool = False) -> tuple:
    rng = random.Random(int(hashlib.sha256((seed + ":surface").encode()).hexdigest(), 16))
    nuisance_rng = random.Random(int(hashlib.sha256((seed + ":nuisance").encode()).hexdigest(), 16))
    rng.aliases = world.aliases
    spellings = {item["name"]: [item["name"], *item.get("aliases", [])]
                 for item in world.lexicon["subjects"]}
    anchors, targets, gold, contexts = [], [], [], []
    all_segments = [(key, segment) for key, segments in world.timelines.items() for segment in segments]
    if anchor_count < len(all_segments):
        raise OracleError(f"need at least {len(all_segments)} anchors to publish every interval")
    for index in range(anchor_count):
        key, segment = all_segments[index] if index < len(all_segments) else rng.choice(all_segments)
        # Publication date varies independently and can lie outside validity.
        publication = SCOPE_START + timedelta(days=rng.randrange((SCOPE_END - SCOPE_START).days + 1))
        anchors.append({"id": opaque_id(seed, "a", index), "text": anchor_text(key, segment, index),
                        "date": publication.isoformat(), "label": "true"})

    keys = list(world.timelines)
    primary_order = list(keys)
    rng.shuffle(primary_order)
    nuisance = []
    for _ in range((target_count + 2) // 3):
        nuisance.append({"style": nuisance_rng.randrange(24 if heldout else 12),
                         "pronoun": nuisance_rng.random() < .2,
                         "distractor": nuisance_rng.random() < 1/3,
                         "arity": nuisance_rng.choices((1, 2, 3), weights=(50, 32, 18))[0],
                         "boundary": nuisance_rng.random() < .4})
    for index in range(target_count):
        wanted = ("true", "false", "unsure")[index % 3]
        nuisance_row = nuisance[index // 3]
        arity = nuisance_row["arity"]
        if wanted == "true":
            pattern = ["true"] * arity
        elif wanted == "false":
            pattern = [rng.choice(("true", "false", "unsure")) for _ in range(arity)]
            pattern[rng.randrange(arity)] = "false"
        else:
            pattern = [rng.choice(("true", "unsure")) for _ in range(arity)]
            pattern[rng.randrange(arity)] = "unsure"
        # Every primary slot receives all three row labels in each triplet.
        # A modulo-N slot cycle aligned with modulo-3 labels would otherwise
        # leak a constant class per slot whenever N is divisible by three.
        primary = primary_order[(index // 3) % len(primary_order)]
        choices = [segment for segment in world.timelines[primary]
                   if (segment.value is None) == (pattern[0] == "unsure")]
        for _ in range(100):
            segment = rng.choice(choices)
            day = rng.choice((segment.start, segment.end)) if nuisance_row["boundary"] else (
                segment.start + timedelta(days=rng.randrange((segment.end - segment.start).days + 1)))
            available = {"unknown": set(), "known": set()}
            for key in keys:
                if key[:2] != primary[:2]:
                    current = next(part for part in world.timelines[key] if part.start <= day <= part.end)
                    available["unknown" if current.value is None else "known"].add(key[:2])
            if (len(available["unknown"]) >= pattern[1:].count("unsure") and
                    len(available["known"]) >= sum(label != "unsure" for label in pattern[1:]) and
                    len(available["unknown"] | available["known"]) >= len(pattern) - 1):
                break
        else:
            raise OracleError("could not place conjunction within the declared interval policy")
        at, selected, assertions = day.isoformat(), [primary], []
        assertions.append(assertion_for(world, primary, at, pattern[0], rng))
        for offset, component_label in enumerate(pattern[1:]):
            candidates = [key for key in keys if (key[0], key[1]) not in [(s[0], s[1]) for s in selected]
                          and any(segment.start <= day <= segment.end and
                                  (segment.value is None) == (component_label == "unsure")
                                  for segment in world.timelines[key])]
            # Preserve a matching for later components. A money attribute can
            # have a known yearly channel and an unknown monthly channel on the
            # same day; consuming it here must not strand the later unknown.
            remaining = pattern[offset + 2:]
            need_unknown = remaining.count("unsure")
            need_known = len(remaining) - need_unknown
            feasible = []
            for candidate in candidates:
                used = {key[:2] for key in selected} | {candidate[:2]}
                unknowns = available["unknown"] - used
                knowns = available["known"] - used
                if (len(unknowns) >= need_unknown and len(knowns) >= need_known and
                        len(unknowns | knowns) >= len(remaining)):
                    feasible.append(candidate)
            candidates = feasible
            if not candidates:
                raise OracleError("no fact available for a declared conjunction shape")
            key = rng.choice(candidates)
            selected.append(key)
            assertions.append(assertion_for(world, key, at, component_label, rng))
        row_id = opaque_id(seed, "t", index)
        style, pronoun, distractor = (nuisance_row["style"], nuisance_row["pronoun"], nuisance_row["distractor"])
        prefix = ""
        if pronoun:
            spelling = rng.choice(spellings[assertions[0]["subject"]])
            prefix = f"Record subject: {spelling}. "
        clauses = [render_clause(assertion, (style + offset) % (24 if heldout else 12),
                                 rng.choice(spellings[assertion["subject"]]), rng,
                                 pronoun=pronoun and offset == 0, heldout=heldout)
                   for offset, assertion in enumerate(assertions)]
        claim_text = "; and ".join(clauses) + "."
        text = prefix + claim_text
        claim_end = len(text)
        if distractor:
            text += f" Document reference: {rng.randint(100000, 999999)} (identifier only)."
        if pronoun:
            context = {"row_id": row_id, "document_id": opaque_id(seed, "doc", index),
                       "row_ids": [row_id], "declaration_span": [0, len(prefix)],
                       "claim_span": [len(prefix), claim_end], "scope": "same_row_only"}
            if resolve_public_context(text, context, world.lexicon) != assertions[0]["subject"]:
                raise OracleError("public context does not establish the generated subject")
            contexts.append(context)
        targets.append({"id": row_id, "text": text, "date": at, "label": ""})
        label, components = world.evaluate_all(assertions, at)
        if label != wanted:
            raise OracleError("oracle conjunction label differs from construction target")
        gold.append({"id": row_id, "date": at, "label": label, "assertions": assertions,
                     "components": components, "style": style,
                     "context": "public_same_row_pronoun" if pronoun else "explicit_subject",
                     "distractor": distractor, "arity": len(assertions)})
    # IDs, order and text templates do not encode class through a modulo/counter.
    rng.shuffle(anchors)
    rng.shuffle(targets)
    rng.shuffle(gold)
    rng.shuffle(contexts)
    return anchors + targets, gold, contexts


def assert_ignored_artifact(path: Path) -> None:
    path = path.resolve()
    if not path.is_relative_to(ROOT / "artifacts"):
        raise OracleError("generated datasets must stay in this checkout's ignored artifacts directory")
    result = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, check=False)
    if result.returncode != 0:
        raise OracleError("output path is not ignored by Git")


def write_bundle(directory: Path, targets: int, *, sealed: bool, seed: str | None = None) -> dict:
    directory = directory.resolve()
    assert_ignored_artifact(directory)
    if directory.exists():
        raise OracleError("refusing to overwrite an existing evaluation bundle")
    if sealed and seed is not None:
        raise OracleError("sealed production bundles require a fresh OS-random private seed")
    seed = seed or secrets.token_hex(32)
    lexicon = json.loads((ROOT / "data" / "lexicon.json").read_text(encoding="utf-8"))
    world = make_world(seed, lexicon)
    rows, gold, contexts = make_dataset(world, seed, targets, heldout=sealed)
    public, private = directory / "public", directory / "private"
    public.mkdir(parents=True)
    private.mkdir()
    snapshot = private / "source_snapshot"
    snapshot.mkdir()
    for source_file in Path(__file__).parent.glob("*.py"):
        (snapshot / source_file.name).write_bytes(source_file.read_bytes())
    with (public / "universe.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
        writer.writeheader()
        writer.writerows(rows)
    write_json(public / "lexicon.json", lexicon)
    write_json(public / "context.json", {"schema": SCHEMA, "offsets": "unicode_codepoints_half_open",
                                        "contexts": contexts})
    (public / "POLICY.md").write_text(POLICY, encoding="utf-8")
    hashes = public_hashes(public)
    provenance = {"method": "independent synthetic counterfactual generator",
                  "sampler_revision": 3,
                  "development_assistance": "OpenAI Codex, development-time LLM-assisted code/design",
                  "runtime_llm": False, "official_hooly_evidence": False,
                  "source_files_sha256": source_hashes(),
                  "public_lexicon_original_sha256": sha256(ROOT / "data" / "lexicon.json"),
                  "existing_archive_gold_read": False}
    manifest = {"schema": SCHEMA, "sealed": sealed, "anchors": 1897, "targets": targets,
                "surface_families": 24 if sealed else 12, "additional_heldout_surface_families": 12 if sealed else 0,
                "hashes": hashes, "public_sha256": digest_hashes(hashes), "provenance": provenance}
    write_json(public / "manifest.json", manifest)
    with (private / "gold.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for entry in gold:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    timelines = [{"subject": key[0], "attribute": key[1], "channel": key[2],
                  "segments": [segment.dump() for segment in segments]}
                 for key, segments in world.timelines.items()]
    write_json(private / "world.json", {"schema": SCHEMA, "seed": seed, "timelines": timelines})
    write_json(private / "metadata.json", {**manifest, "gold_sha256": sha256(private / "gold.jsonl"),
                                           "world_sha256": sha256(private / "world.json")})
    if not sealed:
        write_json(private / "development-summary.json", {
            "labels": dict(Counter(entry["label"] for entry in gold)),
            "kinds": dict(Counter(assertion["value"]["kind"] for entry in gold for assertion in entry["assertions"])),
            "operators": dict(Counter(assertion["op"] for entry in gold for assertion in entry["assertions"])),
            "arity": dict(Counter(entry["arity"] for entry in gold)),
            "pronoun_rows": len(contexts),
            "distractor_rows": sum(entry["distractor"] for entry in gold),
        })
    # Never print seeds, gold rows, or sealed class/stratum distributions here.
    result = {"public": str(public), "public_sha256": manifest["public_sha256"],
              "universe_sha256": hashes["universe.csv"], "targets": targets, "anchors": 1897,
              "sealed": sealed}
    if not sealed:
        result["development_gold"] = str(private / "gold.jsonl")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "independent-evaluation-v3")
    parser.add_argument("--split", choices=("development", "sealed-5000", "sealed-20000", "all"), default="all")
    args = parser.parse_args()
    for split, count in (("development", 1000), ("sealed-5000", 5000), ("sealed-20000", 20000)):
        if args.split in (split, "all"):
            print(json.dumps(write_bundle(args.output / split, count, sealed=split != "development"), sort_keys=True))


if __name__ == "__main__":
    main()
