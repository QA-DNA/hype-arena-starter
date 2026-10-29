"""Hand-authored generated-claim temporal witnesses, no production fixtures."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from .claims import ClaimOracle, evaluate_claims, form_shape, score_claim_rows, text_check, value_shape
from .oracle import OracleError, World, channel


def value(kind, raw, **rest):
    return {"kind": kind, "value": raw, **rest}


LEXICON = {"subjects": [
    {"name": "Hooly", "aliases": ["Hooly Inc."], "attributes": ["employees", "ceo", "founded"]},
    {"name": "Holdan", "aliases": [], "attributes": ["team_size"]},
    {"name": "Hooly AI Pro", "aliases": [], "attributes": ["price"]},
    {"name": "Peter Gregori", "aliases": ["Peter"], "attributes": ["joined"]},
    {"name": "Ron LaFlame", "aliases": [], "attributes": ["joined"]},
    {"name": "Gemini Launch Night", "aliases": ["Launch Night"], "attributes": ["date"]},
], "events": ["Gemini Launch Night"]}


def history(subject, attribute, first, second=None):
    segments = [{"start": "2026-01-01", "end": "2026-06-30" if second else "2026-12-31", "value": first}]
    if second:
        segments.append({"start": "2026-07-01", "end": "2026-12-31", "value": second})
    return {"subject": subject, "attribute": attribute, "channel": channel(first), "segments": segments}


def world_raw():
    return [
        history("Hooly", "employees", value("quantity", 100, unit="employee"), value("quantity", 200, unit="employee")),
        history("Holdan", "team_size", value("quantity", 150, unit="employee")),
        history("Hooly", "ceo", value("name", "Peter Gregori"), value("name", "Ron LaFlame")),
        history("Peter Gregori", "joined", value("date", "2026-03-03"), value("date", "2026-04-04")),
        history("Ron LaFlame", "joined", value("date", "2026-05-05")),
        history("Gemini Launch Night", "date", value("date", "2026-05-01")),
        history("Hooly AI Pro", "price", value("money", 10, currency="EUR", per="month")),
        history("Hooly AI Pro", "price", value("money", 100, currency="EUR", per="year")),
    ]


def claim_row(row_id="c1", *, form=None, text="Hooly's employees is 200 employees."):
    return {"id": row_id, "type": "fact", "text": text, "form": json.dumps(form or {
        "subject": "Hooly", "attribute": "employees", "value": value("quantity", 200, unit="employee")}),
        "label": "true", "confidence": ".9"}


class ClaimSemanticTests(unittest.TestCase):
    def setUp(self):
        self.world = World(world_raw(), LEXICON)
        self.oracle = ClaimOracle(self.world)

    def test_fact_as_of_not_publication_order(self):
        for amount, wanted in ((200, "true"), (100, "false")):
            form = {"subject": "Hooly", "attribute": "employees", "value": value("quantity", amount, unit="employee")}
            result = self.oracle.evaluate("fact", form)
            self.assertEqual(result["status"], wanted)
            self.assertEqual(result["witness_date"], "2026-10-29")

    def test_compare_as_of_and_same_fact_invalid(self):
        form = {"left": {"subject": "Hooly", "attribute": "employees"},
                "right": {"subject": "Holdan", "attribute": "team_size"}, "op": "gt"}
        self.assertEqual(self.oracle.evaluate("compare", form)["status"], "true")
        self.assertEqual(self.oracle.evaluate("compare", dict(form, op="lt"))["status"], "false")
        self.assertEqual(self.oracle.evaluate("compare", dict(form, right=form["left"]))["status"], "invalid_semantics")

    def test_money_fact_selects_period_compare_reports_ambiguity(self):
        form = {"subject": "Hooly AI Pro", "attribute": "price", "value": value("money", 100, currency="EUR", per="year")}
        self.assertEqual(self.oracle.evaluate("fact", form)["status"], "true")
        form = {"left": {"subject": "Hooly AI Pro", "attribute": "price"},
                "right": {"subject": "Hooly", "attribute": "employees"}, "op": "gt"}
        result = self.oracle.evaluate("compare", form)
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("ambiguous_world_channels", result["reason"])

    def test_change_needs_strictly_ordered_value_witness(self):
        form = {"subject": "Hooly", "attribute": "employees", "from": value("quantity", 100, unit="employee"),
                "to": value("quantity", 200, unit="employee")}
        result = self.oracle.evaluate("change", form)
        self.assertEqual(result["status"], "true")
        self.assertLess(result["witness_dates"][0], result["witness_dates"][1])
        self.assertEqual(self.oracle.evaluate("change", dict(form, **{"from": form["to"], "to": form["from"]}))["status"], "false")

    def test_at_event_uses_event_day_not_as_of_fact(self):
        form = {"subject": "Hooly", "attribute": "employees", "event": "Launch Night",
                "value": value("quantity", 100, unit="employee")}
        result = self.oracle.evaluate("at_event", form)
        self.assertEqual(result["status"], "true")
        self.assertEqual(result["witness_date"], "2026-05-01")
        self.assertEqual(self.oracle.evaluate("fact", {k: v for k, v in form.items() if k != "event"})["status"], "false")

    def test_at_event_partial_date_is_unsupported_not_unsure(self):
        raw = world_raw()
        raw[5]["segments"][0]["value"]["value"] = "2026-05"
        oracle = ClaimOracle(World(raw, LEXICON))
        form = {"subject": "Hooly", "attribute": "employees", "event": "Launch Night",
                "value": value("quantity", 100, unit="employee")}
        self.assertEqual(oracle.evaluate("at_event", form)["status"], "unsupported")

    def test_relation_requires_contemporaneous_link_target_value(self):
        form = {"subject": "Hooly", "link": "ceo", "target": "Peter", "attribute": "joined", "value": value("date", "2026-03-03")}
        self.assertEqual(self.oracle.evaluate("relation", form)["status"], "true")
        # Both the link and requested date occur, but in disjoint intervals.
        self.assertEqual(self.oracle.evaluate("relation", dict(form, value=value("date", "2026-04-04")))["status"], "false")
        self.assertEqual(self.oracle.evaluate("relation", dict(form, target="Ron LaFlame", value=value("date", "2026-05-05")))["status"], "true")

    def test_explicit_gap_can_hide_change_or_relation_witness(self):
        raw = world_raw()
        for index in (0, 2):
            raw[index]["segments"].insert(1, {"start": "2026-06-01", "end": "2026-06-30", "value": None, "reason": "explicit_gap"})
            raw[index]["segments"][0]["end"] = "2026-05-31"
        raw[4] = history("Ron LaFlame", "joined", value("date", "2026-05-05"), value("date", "2026-06-06"))
        oracle = ClaimOracle(World(raw, LEXICON))
        change = {"subject": "Hooly", "attribute": "employees", "from": value("quantity", 777, unit="employee"),
                  "to": value("quantity", 888, unit="employee")}
        self.assertEqual(oracle.evaluate("change", change)["status"], "unsure")
        relation = {"subject": "Hooly", "link": "ceo", "target": "Ron LaFlame", "attribute": "joined", "value": value("date", "2026-05-05")}
        self.assertEqual(oracle.evaluate("relation", relation)["status"], "unsure")

    def test_undeclared_world_fact_is_unsupported_not_false(self):
        form = {"subject": "Hooly", "attribute": "founded", "value": value("date", "2020")}
        self.assertEqual(self.oracle.evaluate("fact", form)["status"], "unsupported")

    def test_mixed_precision_date_ordering_is_unsupported_not_invalid(self):
        raw = world_raw()
        raw[4]["segments"][0]["value"]["value"] = "2026-05"
        oracle = ClaimOracle(World(raw, LEXICON))
        form = {"left": {"subject": "Peter Gregori", "attribute": "joined"},
                "right": {"subject": "Ron LaFlame", "attribute": "joined"}, "op": "gt"}
        self.assertEqual(oracle.evaluate("compare", form)["status"], "unsupported")
        self.assertEqual(oracle.evaluate("compare", dict(form, op="eq"))["status"], "false")


class ClaimOutputTests(unittest.TestCase):
    def setUp(self):
        self.world = World(world_raw(), LEXICON)

    def test_world_truth_is_distinct_from_text_mismatch_and_unsupported_text(self):
        result = score_claim_rows([
            claim_row(text="Hooly's employees is 201 employees."),
            claim_row("c2", text="Hooly employs two hundred people."),
            claim_row("c3"),
        ], [], self.world)
        self.assertEqual(result["world_truth"], {"true": 3})
        self.assertEqual(result["text_grammar"], {"invalid": 1, "unsupported": 1, "supported_valid": 1})
        self.assertEqual(result["certified_by_bounded_checks"], 1)
        self.assertEqual(result["missing_claims"], 997)

    def test_schema_invalid_false_world_missing_duplicate_and_newness_separate(self):
        false_form = {"subject": "Hooly", "attribute": "employees", "value": value("quantity", 100, unit="employee")}
        bad = claim_row("bad")
        bad["form"] = "{invalid"
        duplicate = claim_row("bad")
        result = score_claim_rows([bad, duplicate, claim_row("false", form=false_form), claim_row("same")],
                                  [{"text": "Hooly's employees is 200 employees."}], self.world)
        self.assertEqual(result["schema"], {"invalid": 2, "valid": 2})
        self.assertEqual(result["world_truth"], {"not_evaluated": 2, "false": 1, "true": 1})
        self.assertEqual(result["not_new"], 4)
        self.assertEqual(result["missing_claims"], 996)

    def test_submission_values_have_no_op_and_numeric_json_types(self):
        self.assertTrue(value_shape(value("quantity", "200", unit="employee")))
        self.assertTrue(value_shape(value("quantity", 200, unit="employee", op="eq")))
        self.assertTrue(value_shape(value("duration", 1, unit=[])))
        self.assertTrue(form_shape("compare", {"left": {"subject": "Hooly", "attribute": "employees"},
                                                "right": {"subject": "Holdan", "attribute": "team_size"}, "op": "ge"}))

    def test_longest_subject_matching_rejects_company_inside_plan_name(self):
        form = {"subject": "Hooly", "attribute": "employees", "value": value("quantity", 200, unit="employee")}
        self.assertEqual(text_check("fact", form, "Hooly AI Pro has 200 employees.", self.world)["status"], "invalid")

    def test_claim_evaluation_refuses_sealed_before_accessing_data(self):
        with patch("tools.independent_evaluation.claims.verify_public", return_value={"sealed": True}):
            with self.assertRaisesRegex(OracleError, "development-only"):
                evaluate_claims(Path("unused"), Path("unused.csv"), Path("unused.json"))


if __name__ == "__main__":
    unittest.main()
