"""Development-only generated-claim semantics, separate from schema/text checks.

No production imports and no page-date ordering. Missing declared world facts or
ambiguous channels are unsupported, not invented false/unsure answers. Only
explicit world gaps can produce an unsure semantic verdict.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .audit import public_world
from .factory import assert_ignored_artifact, write_json
from .grammar import parse_comparison, parse_value
from .oracle import (DURATION_UNITS, KINDS, OracleError, World, canonical_name,
                     channel, compare, normalized, partial_date, rational)
from .score import read_csv, verify_public


AS_OF = "2026-10-29"
CLAIM_SCORER_REVISION = "independent-claims-3-unit-aliases-bounded-facts"
CLAIM_TYPES = ("fact", "compare", "change", "at_event", "relation")


class WorldUnavailable(OracleError):
    """Legal form outside the independent world's declared coverage/domain."""


def exact_keys(value: dict, required: set, optional: set | None = None) -> bool:
    return isinstance(value, dict) and required <= set(value) <= required | (optional or set())


def value_shape(value: dict) -> list[str]:
    """Explicit structural subset of the official claimed_value schema, no deps."""
    if not isinstance(value, dict) or value.get("kind") not in KINDS:
        return ["value.kind"]
    kind = value["kind"]
    required = {"kind", "value"} | ({"unit"} if kind in ("quantity", "duration") else set())
    required |= {"currency"} if kind == "money" else set()
    if not exact_keys(value, required, {"per"} if kind == "money" else set()):
        return ["value.fields (submission values cannot have op)"]
    raw, errors = value["value"], []
    if kind in ("quantity", "money", "duration", "percent"):
        if isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
            errors.append("value.number")
        else:
            try:
                number = rational(Decimal(str(raw)))
                if kind in ("money", "duration") and number < 0:
                    errors.append("value.minimum")
            except OracleError:
                errors.append("value.finite_number")
    elif kind == "boolean" and type(raw) is not bool:
        errors.append("value.boolean")
    elif kind == "name" and (not isinstance(raw, str) or not raw.strip() or len(raw) > 200):
        errors.append("value.name")
    elif kind == "date" and (not isinstance(raw, str) or not re.fullmatch(
            r"\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?", raw)):
        errors.append("value.date_pattern")
    elif kind == "version" and (not isinstance(raw, str) or not re.fullmatch(r"\d+(?:\.\d+){0,3}", raw)):
        errors.append("value.version_pattern")
    if kind == "quantity" and (not isinstance(value["unit"], str) or len(value["unit"]) > 40 or
                               not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value["unit"]) or
                               value["unit"] in DURATION_UNITS):
        errors.append("value.quantity_unit")
    if kind == "duration" and (not isinstance(value["unit"], str) or value["unit"] not in DURATION_UNITS):
        errors.append("value.duration_unit")
    if kind == "money":
        if not isinstance(value["currency"], str) or not re.fullmatch(r"[A-Z]{3}", value["currency"]):
            errors.append("value.currency")
        if "per" in value and value["per"] not in ("day", "week", "month", "year"):
            errors.append("value.period")
    return errors


def form_shape(kind: str, form: dict) -> list[str]:
    fields = {"fact": {"subject", "attribute", "value"},
              "compare": {"left", "right", "op"},
              "change": {"subject", "attribute", "from", "to"},
              "at_event": {"subject", "attribute", "event", "value"},
              "relation": {"subject", "link", "target", "attribute", "value"}}
    if kind not in fields or not exact_keys(form, fields[kind]):
        return ["form.fields"]
    errors = []
    if kind == "compare":
        if form["op"] not in ("gt", "lt", "eq"):
            errors.append("form.compare_op")
        for side in ("left", "right"):
            if not exact_keys(form[side], {"subject", "attribute"}):
                errors.append(f"form.{side}.fields")
            else:
                errors.extend(ref_shape(form[side]))
    else:
        errors.extend(ref_shape(form))
        for field in ("event", "target", "link"):
            if field in form and (not isinstance(form[field], str) or not form[field].strip()):
                errors.append(f"form.{field}")
            elif field in form and ((field != "link" and len(form[field]) > 120) or
                                   (field == "link" and not re.fullmatch(r"[a-z][a-z0-9_]*", form[field]))):
                errors.append(f"form.{field}")
        for field in ("value", "from", "to"):
            if field in form:
                errors.extend(f"{field}.{error}" for error in value_shape(form[field]))
    return errors


def ref_shape(ref: dict) -> list[str]:
    errors = []
    if not isinstance(ref.get("subject"), str) or not ref["subject"].strip() or len(ref["subject"]) > 120:
        errors.append("form.subject")
    if not isinstance(ref.get("attribute"), str) or not re.fullmatch(r"[a-z][a-z0-9_]*", ref["attribute"]):
        errors.append("form.attribute")
    return errors


def lexicon_errors(kind: str, form: dict, world: World) -> list[str]:
    legal = {subject["name"]: set(subject["attributes"]) for subject in world.lexicon["subjects"]}
    refs = [form["left"], form["right"]] if kind == "compare" else [form]
    if kind == "relation":
        refs = [{"subject": form["subject"], "attribute": form["link"]},
                {"subject": form["target"], "attribute": form["attribute"]}]
    errors = []
    for ref in refs:
        try:
            subject = canonical_name(ref["subject"], world.aliases)
            if ref["attribute"] not in legal[subject]:
                errors.append("unpublished_attribute")
        except OracleError:
            errors.append("unpublished_subject")
    if kind == "at_event":
        try:
            event = canonical_name(form["event"], world.aliases)
            if event not in world.lexicon.get("events", []):
                errors.append("unpublished_event")
        except OracleError:
            errors.append("unpublished_event")
    for field in ("value", "from", "to"):
        if field in form and form[field]["kind"] == "name":
            try:
                canonical_name(form[field]["value"], world.aliases)
            except OracleError:
                errors.append("unpublished_name_value")
    return errors


class ClaimOracle:
    def __init__(self, world: World, as_of: str = AS_OF):
        self.world, self.as_of = world, as_of

    def fact_key(self, ref: dict, value: dict | None = None, *, kind: str | None = None) -> tuple:
        subject = canonical_name(ref["subject"], self.world.aliases)
        options = [key for key in self.world.timelines if key[:2] == (subject, ref["attribute"])]
        if value is not None:
            options = [key for key in options if key[2] == channel(value)]
        if kind:
            options = [key for key in options if key[2] == kind or key[2].startswith(kind + ":")]
        if not options:
            raise WorldUnavailable("undeclared_world_fact_or_channel")
        if len(options) != 1:
            raise WorldUnavailable("ambiguous_world_channels (form does not select currency/period)")
        return options[0]

    def snapshot(self, key: tuple, at: str):
        day = date.fromisoformat(at)
        for segment in self.world.timelines[key]:
            if segment.start <= day <= segment.end:
                return segment
        raise WorldUnavailable("date_outside_explicit_world_scope")

    def matches(self, actual: dict | None, expected: dict) -> bool | None:
        return None if actual is None else compare(actual, expected, "eq", self.world.aliases) == "true"

    def evaluate(self, kind: str, form: dict) -> dict:
        try:
            return self._evaluate(kind, form)
        except WorldUnavailable as exc:
            return {"status": "unsupported", "reason": str(exc)}
        except OracleError as exc:
            return {"status": "invalid_semantics", "reason": str(exc)}

    def _evaluate(self, kind: str, form: dict) -> dict:
        for field in ("value", "from", "to"):
            if field in form:
                normalized(form[field], self.world.aliases)
        if kind == "fact":
            key = self.fact_key(form, form["value"])
            segment = self.snapshot(key, self.as_of)
            if segment.value is None:
                return {"status": "unsure", "reason": "explicit_gap_at_as_of"}
            return {"status": compare(segment.value, form["value"], "eq", self.world.aliases),
                    "reason": "as_of_value", "witness_date": self.as_of}
        if kind == "compare":
            left_key, right_key = self.fact_key(form["left"]), self.fact_key(form["right"])
            if left_key == right_key:
                raise OracleError("a fact cannot compare with itself")
            # Channel identities validate comparability even for fully unknown
            # timelines; no hidden example value is needed.
            if (form["op"] not in ("gt", "lt", "eq") or left_key[2] in ("name", "boolean") or
                    left_key[2] != right_key[2]):
                raise OracleError("facts are not a comparable ordered kind/dimension")
            left, right = self.snapshot(left_key, self.as_of), self.snapshot(right_key, self.as_of)
            if left.value is None or right.value is None:
                return {"status": "unsure", "reason": "explicit_gap_at_as_of"}
            if (left.value["kind"] == "date" and form["op"] != "eq" and
                    len(partial_date(left.value["value"])) != len(partial_date(right.value["value"]))):
                raise WorldUnavailable("mixed_precision_date_ordering_outside_declared_policy")
            return {"status": compare(left.value, right.value, form["op"], self.world.aliases),
                    "reason": "as_of_comparison", "witness_date": self.as_of}
        if kind == "change":
            if channel(form["from"]) != channel(form["to"]):
                raise WorldUnavailable("change_across_simultaneous_channels_is_not_declared")
            key = self.fact_key(form, form["from"])
            possible = False
            for before in self.world.timelines[key]:
                old = self.matches(before.value, form["from"])
                if old is False:
                    continue
                for after in self.world.timelines[key]:
                    new = self.matches(after.value, form["to"])
                    # Strictly earlier full calendar day; publication dates do
                    # not enter the oracle or this witness test.
                    if new is False or not before.start < after.end:
                        continue
                    if old is True and new is True:
                        later = max(after.start, before.start + timedelta(days=1))
                        return {"status": "true", "reason": "ordered_value_witness",
                                "witness_dates": [str(before.start), str(later)]}
                    possible = True
            return {"status": "unsure" if possible else "false",
                    "reason": "explicit_gap_may_contain_ordered_witness" if possible else "no_ordered_witness"}
        if kind == "at_event":
            event = canonical_name(form["event"], self.world.aliases)
            event_key = self.fact_key({"subject": event, "attribute": "date"}, kind="date")
            event_date = self.snapshot(event_key, self.as_of)
            if event_date.value is None:
                return {"status": "unsure", "reason": "explicit_unknown_event_date"}
            if len(partial_date(event_date.value["value"])) != 3:
                raise WorldUnavailable("event_date_has_only_partial_precision")
            at = event_date.value["value"]
            key = self.fact_key(form, form["value"])
            actual = self.snapshot(key, at)
            if actual.value is None:
                return {"status": "unsure", "reason": "explicit_gap_at_event"}
            return {"status": compare(actual.value, form["value"], "eq", self.world.aliases),
                    "reason": "event_date_witness", "witness_date": at}
        if kind == "relation":
            link = self.fact_key({"subject": form["subject"], "attribute": form["link"]}, kind="name")
            target = canonical_name(form["target"], self.world.aliases)
            fact = self.fact_key({"subject": target, "attribute": form["attribute"]}, form["value"])
            possible = False
            for link_segment in self.world.timelines[link]:
                linked = self.matches(link_segment.value, {"kind": "name", "value": target})
                if linked is False:
                    continue
                for fact_segment in self.world.timelines[fact]:
                    lo, hi = max(link_segment.start, fact_segment.start), min(link_segment.end, fact_segment.end)
                    if lo > hi:
                        continue
                    matches = self.matches(fact_segment.value, form["value"])
                    if matches is False:
                        continue
                    if linked is True and matches is True:
                        return {"status": "true", "reason": "contemporaneous_link_target_witness", "witness_date": str(lo)}
                    possible = True
            return {"status": "unsure" if possible else "false",
                    "reason": "explicit_gap_may_contain_link_witness" if possible else "no_contemporaneous_link_witness"}
        raise OracleError("unknown claim type")


def spellings(subject: str, world: World) -> list[str]:
    canonical = canonical_name(subject, world.aliases)
    record = next(record for record in world.lexicon["subjects"] if record["name"] == canonical)
    return [record["name"], *record.get("aliases", [])]


def name_pattern(subject: str, world: World) -> str:
    return "(?:" + "|".join(r"\s*".join(re.escape(part) for part in name.split())
                               for name in sorted(spellings(subject, world), key=len, reverse=True)) + ")"


def mentions(text: str, subject: str, world: World) -> bool:
    matches = []
    for item in world.lexicon["subjects"]:
        for match in re.finditer(r"(?<!\w)" + name_pattern(item["name"], world) + r"(?!\w)", text, re.I):
            matches.append((match.start(), match.end(), item["name"]))
    canonical = canonical_name(subject, world.aliases)
    return any(name == canonical and not any(lo2 <= lo and hi <= hi2 and (lo2, hi2) != (lo, hi)
                                               for lo2, hi2, _ in matches) for lo, hi, name in matches)


def text_check(kind: str, form: dict, text: str, world: World) -> dict:
    """Necessary rules plus certification of a small explicit template subset.

    Unrecognized wording is unsupported, never silently called valid/invalid by
    the world oracle. This does not implement the organizer's private referee.
    """
    subjects = [form["left"]["subject"], form["right"]["subject"]] if kind == "compare" else [form["subject"]]
    if any(not mentions(text, subject, world) for subject in subjects):
        return {"status": "invalid", "reason": "required_subject_not_named (longest-name matching)"}
    if kind == "relation":
        words = form["link"].replace("_", " ")
        if not re.search(r"[\s-]*".join(map(re.escape, words.split())), text, re.I):
            return {"status": "invalid", "reason": "relation_words_not_present"}
    if kind != "fact":
        return {"status": "unsupported", "reason": "world_semantics_scored_separately; full_text_referee_not_implemented"}
    attribute = form["attribute"].replace("_", " ")
    subject = name_pattern(form["subject"], world)
    patterns = [rf"{subject}'s {re.escape(attribute)} is (.+)\.",
                rf"{subject} {re.escape(attribute)} is (.+)\.",
                rf"{subject} costs (.+)\.", rf"{subject} has (.+)\."]
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if not match:
            continue
        if form["value"]["kind"] == "boolean" and not re.search(re.escape(attribute), text, re.I):
            return {"status": "invalid", "reason": "boolean_attribute_words_required"}
        op, _ = parse_comparison(match.group(1))
        if op != "eq":
            return {"status": "invalid", "reason": "submission_fact_must_state_an_exact_value"}
        _, isolated = parse_comparison(match.group(1))
        try:
            actual = parse_value(isolated, form["value"]["kind"], world.aliases)
            equal = compare(actual, form["value"], "eq", world.aliases) == "true"
        except OracleError:
            return {"status": "unsupported", "reason": "isolated_value_outside_bounded_text_checker"}
        return {"status": "supported_valid" if equal else "invalid", "reason": "exact_fact_template_value_match" if equal else "text_form_value_mismatch"}
    return {"status": "unsupported", "reason": "fact_wording_outside_bounded_text_checker"}


def reject_constant(value: str):
    raise OracleError(f"non-finite JSON constant: {value}")


def score_claim_rows(rows: list[dict], public_rows: list[dict], world: World, limit: int = 1000) -> dict:
    oracle, records, seen = ClaimOracle(world), [], set()
    source_texts = {" ".join(row["text"].casefold().split()) for row in public_rows}
    for row in rows:
        duplicate = row.get("id", "") in seen
        seen.add(row.get("id", ""))
        kind = (row.get("type") or "").strip()
        if not kind or len(records) >= limit:
            continue
        errors, form = [], None
        row_id, text = row.get("id") or "", row.get("text") or ""
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", row_id):
            errors.append("entry.id")
        if duplicate:
            errors.append("entry.duplicate_id")
        if kind not in CLAIM_TYPES:
            errors.append("entry.type")
        if not text.strip() or len(text) > 300:
            errors.append("entry.text")
        if (row.get("label") or "").strip() not in ("", "true"):
            errors.append("entry.claim_label_must_be_true_or_empty")
        try:
            confidence = Decimal((row.get("confidence") or "").replace(",", "."))
            if not confidence.is_finite() or not Decimal(".5") <= confidence <= 1:
                errors.append("entry.confidence")
        except ArithmeticError:
            errors.append("entry.confidence")
        try:
            form = json.loads(row.get("form") or "", parse_float=Decimal, parse_constant=reject_constant)
            errors.extend(form_shape(kind, form))
        except (ValueError, OracleError, TypeError):
            errors.append("entry.form_json")
        newness = "not_new" if " ".join(text.casefold().split()) in source_texts else "new"
        result = {"id": row_id, "type": kind, "schema": {"status": "invalid" if errors else "valid", "errors": errors},
                  "newness": newness, "text_grammar": {"status": "not_evaluated"},
                  "world_truth": {"status": "not_evaluated"}}
        if not errors:
            lex_errors = lexicon_errors(kind, form, world)
            result["lexicon"] = {"status": "invalid" if lex_errors else "valid", "errors": lex_errors}
            if not lex_errors:
                result["text_grammar"] = text_check(kind, form, text, world)
                result["world_truth"] = oracle.evaluate(kind, form)
        result["certified_by_bounded_checks"] = (not errors and result.get("lexicon", {}).get("status") == "valid" and
                                                 newness == "new" and result["text_grammar"]["status"] == "supported_valid" and
                                                 result["world_truth"]["status"] == "true")
        records.append(result)
    return {"evaluator_revision": CLAIM_SCORER_REVISION,
            "requested_claims": limit, "claim_rows_judged": len(records), "missing_claims": limit - len(records),
            "extra_claim_rows_ignored": max(0, sum(bool((row.get("type") or "").strip()) for row in rows) - limit),
            "schema": dict(Counter(record["schema"]["status"] for record in records)),
            "lexicon": dict(Counter(record.get("lexicon", {}).get("status", "not_evaluated") for record in records)),
            "text_grammar": dict(Counter(record["text_grammar"]["status"] for record in records)),
            "world_truth": dict(Counter(record["world_truth"]["status"] for record in records)),
            "not_new": sum(record["newness"] != "new" for record in records),
            "invalid_claims": sum(record["schema"]["status"] == "invalid" or
                                  record.get("lexicon", {}).get("status") == "invalid" or
                                  record["text_grammar"]["status"] == "invalid" or
                                  record["world_truth"]["status"] == "invalid_semantics" or
                                  record["newness"] != "new" for record in records),
            "false_claims": sum(record["world_truth"]["status"] == "false" for record in records),
            "unsure_claims": sum(record["world_truth"]["status"] == "unsure" for record in records),
            "unsupported_world_claims": sum(record["world_truth"]["status"] == "unsupported" for record in records),
            "certified_by_bounded_checks": sum(record["certified_by_bounded_checks"] for record in records),
            "as_of": AS_OF, "records": records,
            "scope": "development-only independent semantics; explicit structural validation, bounded fact text grammar, not official private referee"}


def evaluate_claims(bundle: Path, predictions: Path, report: Path) -> dict:
    manifest = verify_public(bundle)
    if manifest["sealed"]:
        raise OracleError("generated-claim scoring is development-only; sealed worlds remain gated and private")
    assert_ignored_artifact(report)
    rows = read_csv(bundle / "public" / "universe.csv")
    lexicon = json.loads((bundle / "public" / "lexicon.json").read_text(encoding="utf-8"))
    world, _ = public_world(rows, lexicon)
    result = score_claim_rows(read_csv(predictions), rows, world)
    result.update(public_sha256=manifest["public_sha256"], sealed=False)
    report.parent.mkdir(parents=True, exist_ok=True)
    write_json(report, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate_claims(args.bundle.resolve(), args.predictions.resolve(), args.report.resolve())
    except (OracleError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"claim evaluation refused: {exc}\n")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, sort_keys=True))


if __name__ == "__main__":
    main()
