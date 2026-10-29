"""Hand-specified semantic checks, independent of all production code/models."""

from __future__ import annotations

import csv
import itertools
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from .audit import public_world
from .factory import (ROOT, SCHEMA, digest_hashes, make_dataset, make_world,
                      public_hashes, sha256, write_json)
from .grammar import (decimal_text, parse_comparison, parse_number, parse_value,
                      render_number, render_value)
from .oracle import (LABELS, OracleError, World, alias_map, channel, compare,
                     conjunction, rational, resolve_public_context)
from .score import evaluate_bundle, metrics, validate_freeze


LEXICON = {"subjects": [
    {"name": "Hooly", "aliases": ["Hooly Inc."], "attributes": ["employees", "ceo", "founded"]},
    {"name": "Hooly AI Pro", "aliases": ["Pro plan"], "attributes": ["price", "free_trial"]},
    {"name": "Peter Gregori", "aliases": ["Peter"], "attributes": []},
    {"name": "Ron LaFlame", "aliases": [], "attributes": []},
]}
ALIASES = alias_map(LEXICON)


def val(kind: str, value, **rest) -> dict:
    return {"kind": kind, "value": value, **rest}


def timeline(subject="Hooly", attribute="employees", value=None) -> dict:
    value = value or val("quantity", "100", unit="employee")
    return {"subject": subject, "attribute": attribute, "channel": channel(value), "segments": [
        {"start": "2026-01-01", "end": "2026-01-10", "value": value},
        {"start": "2026-01-11", "end": "2026-01-15", "value": None, "reason": "explicit_gap"},
        {"start": "2026-01-16", "end": "2026-01-31", "value": value},
    ]}


class ExactValueTests(unittest.TestCase):
    def test_exact_decimal_has_no_binary_rounding(self):
        self.assertEqual(rational("0.1") + rational("0.2"), rational("0.3"))
        with self.assertRaises(OracleError):
            rational(.1)

    def test_exact_si_and_inch_conversions(self):
        for actual, claim in [
            (val("quantity", "1", unit="GB"), val("quantity", "1000", unit="MB")),
            (val("quantity", "1", unit="in"), val("quantity", "2.54", unit="cm")),
            (val("quantity", "1", unit="mW"), val("quantity", "0.001", unit="W")),
            (val("quantity", "1.2", unit="kg"), val("quantity", "1200", unit="g")),
        ]:
            with self.subTest(actual=actual):
                self.assertEqual(compare(actual, claim, "eq", ALIASES), "true")

    def test_unit_case_and_dimensions_do_not_collapse(self):
        with self.assertRaises(OracleError):
            compare(val("quantity", "1", unit="mW"), val("quantity", "1", unit="MW"), "eq", ALIASES)
        with self.assertRaises(OracleError):
            compare(val("quantity", "1", unit="employee"), val("quantity", "1", unit="customer"), "eq", ALIASES)

    def test_fixed_and_calendar_durations(self):
        self.assertEqual(compare(val("duration", "14", unit="day"), val("duration", "2", unit="week"), "eq", ALIASES), "true")
        self.assertEqual(compare(val("duration", "12", unit="month"), val("duration", "1", unit="year"), "eq", ALIASES), "true")
        with self.assertRaises(OracleError):
            compare(val("duration", "30", unit="day"), val("duration", "1", unit="month"), "eq", ALIASES)

    def test_money_currency_period_once_are_separate(self):
        actual = val("money", "10", currency="EUR", per="month")
        for claim in (val("money", "120", currency="EUR", per="year"),
                      val("money", "10", currency="USD", per="month"),
                      val("money", "10", currency="EUR")):
            with self.assertRaises(OracleError):
                compare(actual, claim, "eq", ALIASES)

    def test_version_precision_follows_contract_not_former_benchmark(self):
        short, long = val("version", "2.3"), val("version", "2.3.0")
        self.assertEqual(compare(short, long, "eq", ALIASES), "false")
        self.assertEqual(compare(short, long, "ne", ALIASES), "true")
        self.assertEqual(compare(val("version", "2.10"), val("version", "2.9"), "gt", ALIASES), "true")
        self.assertEqual(compare(short, long, "lt", ALIASES), "true")

    def test_partial_dates_preserve_precision(self):
        self.assertEqual(compare(val("date", "2026"), val("date", "2026-03"), "eq", ALIASES), "false")
        self.assertEqual(compare(val("date", "2026-04"), val("date", "2026-03"), "gt", ALIASES), "true")
        with self.assertRaises(OracleError):
            compare(val("date", "2026"), val("date", "2026-03"), "le", ALIASES)
        with self.assertRaises(OracleError):
            compare(val("date", "2026-02-29"), val("date", "2026-03-01"), "lt", ALIASES)

    def test_all_six_numeric_operators_hand_expected(self):
        actual = val("percent", "50")
        for number, expected in (("49", (False, True, False, False, True, True)),
                                 ("50", (True, False, False, True, False, True)),
                                 ("51", (False, True, True, True, False, False))):
            for op, answer in zip(("eq", "ne", "lt", "le", "gt", "ge"), expected):
                self.assertEqual(compare(actual, val("percent", number), op, ALIASES), "true" if answer else "false")

    def test_alias_names_and_booleans_are_unordered(self):
        self.assertEqual(compare(val("name", "Peter Gregori"), val("name", "PETER"), "eq", ALIASES), "true")
        self.assertEqual(compare(val("boolean", False), val("boolean", True), "ne", ALIASES), "true")
        with self.assertRaises(OracleError):
            compare(val("boolean", False), val("boolean", True), "lt", ALIASES)


class TemporalAndContextTests(unittest.TestCase):
    def setUp(self):
        self.world = World([timeline()], LEXICON)
        self.assertion = {"subject": "Hooly", "attribute": "employees", "value": val("quantity", "100", unit="employee"), "op": "eq"}

    def test_inclusive_endpoints_and_explicit_gap(self):
        expected = {"2026-01-01": "true", "2026-01-10": "true", "2026-01-11": "unsure",
                    "2026-01-15": "unsure", "2026-01-16": "true", "2026-01-31": "true"}
        for at, label in expected.items():
            self.assertEqual(self.world.evaluate(self.assertion, at)[0], label)
        with self.assertRaises(OracleError):
            self.world.evaluate(self.assertion, "2026-02-01")

    def test_undeclared_channel_is_error_never_gold_unsure(self):
        assertion = dict(self.assertion, value=val("quantity", "100", unit="customer"))
        with self.assertRaises(OracleError):
            self.world.evaluate(assertion, "2026-01-12")
        with self.assertRaises(OracleError):
            self.world.evaluate(dict(self.assertion, op="approximately"), "2026-01-12")

    def test_overlap_and_implicit_gap_rejected(self):
        for start in ("2026-01-10", "2026-01-12"):
            raw = timeline()
            raw["segments"][1]["start"] = start
            with self.assertRaises(OracleError):
                World([raw], LEXICON)

    def test_same_attribute_money_lookups_select_explicit_channel(self):
        monthly = timeline("Hooly AI Pro", "price", val("money", "10", currency="EUR", per="month"))
        yearly = timeline("Hooly AI Pro", "price", val("money", "90", currency="EUR", per="year"))
        world = World([yearly, monthly], LEXICON)
        for value, wanted in ((val("money", "90", currency="EUR", per="year"), "true"),
                              (val("money", "120", currency="EUR", per="year"), "false"),
                              (val("money", "10", currency="EUR", per="month"), "true")):
            self.assertEqual(world.evaluate({"subject": "Pro plan", "attribute": "price", "value": value}, "2026-01-01")[0], wanted)

    def test_false_dominates_every_conjunction_permutation(self):
        for size in (1, 2, 3):
            for labels in itertools.product(LABELS, repeat=size):
                expected = "false" if "false" in labels else "unsure" if "unsure" in labels else "true"
                self.assertEqual(conjunction(labels), expected)

    def test_context_uses_public_text_and_actual_bounds(self):
        prefix = "Record subject: Pro plan. "
        text = prefix + "Its free trial is 14 days."
        context = {"declaration_span": [0, len(prefix)]}
        self.assertEqual(resolve_public_context(text, context, LEXICON), "Hooly AI Pro")
        changed = "Record subject: Hooly. "
        self.assertEqual(resolve_public_context(changed + text[len(prefix):],
                                               {"declaration_span": [0, len(changed)]}, LEXICON), "Hooly")
        for bounds in ([0, len(text) + 1], [len(prefix), len(text)], [0, 3]):
            with self.assertRaises(OracleError):
                resolve_public_context(text, {"declaration_span": bounds}, LEXICON)


class GrammarTests(unittest.TestCase):
    def test_hand_written_surface_cases(self):
        cases = [
            ("1,200 employees", "quantity", val("quantity", "1200", unit="employee")),
            ("twenty-four languages", "quantity", val("quantity", "24", unit="language")),
            ("10k users", "quantity", val("quantity", "10000", unit="user")),
            ("1.5 GB", "quantity", val("quantity", "1.5", unit="GB")),
            ("€49,99 per month", "money", val("money", "49.99", currency="EUR", per="month")),
            ("120 USD/year", "money", val("money", "120", currency="USD", per="year")),
            ("99.999%", "percent", val("percent", "99.999")),
            ("50 per cent", "percent", val("percent", "50")),
            ("March 2026", "date", val("date", "2026-03")),
            ("12 March 2026", "date", val("date", "2026-03-12")),
            ("March 12, 2026", "date", val("date", "2026-03-12")),
            ("2026", "date", val("date", "2026")),
            ("version 2.3.0", "version", val("version", "2.3.0")),
            ("v2.3", "version", val("version", "2.3")),
            ("fourteen days", "duration", val("duration", "14", unit="day")),
            ("PETER", "name", val("name", "Peter Gregori")),
            ("no", "boolean", val("boolean", False)),
        ]
        for text, kind, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_value(text, kind, ALIASES), expected)

    def test_ambiguous_unsupported_forms_are_errors_not_unsure(self):
        for text, kind in (("1,5 GB", "quantity"), ("1.500 mAh", "quantity"),
                           ("99,9%", "percent"), ("12/03/2026", "date"),
                           ("Q4 2026", "date"), ("about 10 GB", "quantity"),
                           ("10-20 GB", "quantity"), ("1\u200b GB", "quantity")):
            with self.subTest(text=text), self.assertRaises(OracleError):
                parse_value(text, kind, ALIASES)

    def test_comparator_negations_have_operator_semantics(self):
        expected = {"no more than 10 GB": ("le", "10 GB"),
                    "not less than 10 GB": ("ge", "10 GB"),
                    "not equal to v2.3": ("ne", "v2.3"),
                    "exactly 50%": ("eq", "50%"),
                    "below 1 GB": ("lt", "1 GB"),
                    "above 1 GB": ("gt", "1 GB")}
        for text, result in expected.items():
            self.assertEqual(parse_comparison(text), result)

    def test_finite_decimal_and_nonambiguous_scales(self):
        self.assertEqual(decimal_text(Fraction(127, 5000)), "0.0254")
        with self.assertRaises(OracleError):
            decimal_text(Fraction(1, 3))
        self.assertEqual(render_number("10041", 3), "10.0410 thousand")
        self.assertEqual(parse_number(render_number("10041", 3)), Fraction(10041))

    def test_value_render_roundtrip_has_independent_semantic_assertion(self):
        cases = [val("quantity", "10041", unit="MB"), val("money", "49.99", currency="EUR", per="month"),
                 val("percent", "99.999"), val("date", "2026-03-12"), val("version", "2.3.0"),
                 val("duration", "14", unit="day"), val("name", "Peter Gregori"), val("boolean", False)]
        for value in cases:
            for style in range(42):
                text = render_value(value, style)
                self.assertEqual(compare(parse_value(text, value["kind"], ALIASES), value, "eq", ALIASES), "true")


class ScoringTests(unittest.TestCase):
    def test_hand_computed_confusion_macro_f1_and_confidence_brier(self):
        gold = {"a": "true", "b": "false", "c": "unsure", "d": "true"}
        predictions = [{"id": "a", "label": "true", "confidence": ".8"},
                       {"id": "b", "label": "true", "confidence": ".6"},
                       {"id": "d", "label": "unsure", "confidence": ""}]
        result = metrics(gold, predictions)
        self.assertEqual(result["target_accuracy"], .5)
        self.assertAlmostEqual(result["macro_f1"], (1/2 + 0 + 2/3) / 3)
        self.assertEqual(result["coverage"], .5)
        self.assertEqual(result["covered_accuracy"], .5)
        self.assertAlmostEqual(result["confidence_brier_correctness"]["score"], .2)
        self.assertEqual(result["confidence_brier_correctness"]["n"], 2)

    def test_first_duplicate_counts_claims_and_other_ids_ignored(self):
        rows = [{"id": "a", "label": "false", "confidence": "1"},
                {"id": "a", "label": "true", "confidence": "1"},
                {"id": "claim", "type": "fact", "label": "true", "confidence": "1"},
                {"id": "anchor", "label": "true", "confidence": "1"}]
        result = metrics({"a": "true"}, rows)
        self.assertEqual(result["target_accuracy"], 0)
        self.assertEqual(result["diagnostics"]["duplicate_target_rows_ignored"], 1)
        self.assertEqual(result["diagnostics"]["generated_claims_ignored"], 1)
        self.assertEqual(result["diagnostics"]["non_target_rows_ignored"], 1)

    def test_missing_is_unsure_invalid_confidence_cannot_hide_classification_error(self):
        result = metrics({"a": "true", "b": "unsure", "c": "false"}, [
            {"id": "a", "label": "false", "confidence": "NaN"},
            {"id": "c", "label": "false", "confidence": "0,9"}])
        self.assertAlmostEqual(result["target_accuracy"], 2 / 3)
        self.assertEqual(result["confidence_brier_correctness"]["n"], 1)
        self.assertEqual(result["confidence_brier_correctness"]["invalid"], 1)
        self.assertEqual(result["diagnostics"]["missing_targets"], 1)

    def test_sealed_requires_explicit_coordinator_freeze(self):
        with self.assertRaises(OracleError):
            validate_freeze(None, {"sealed": True}, Path("unused.csv"))

    def test_sealed_gate_does_not_read_gold_before_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "private").mkdir()
            (root / "private" / "metadata.json").write_text(json.dumps({"sealed": True, "public_sha256": "digest"}))
            with patch("tools.independent_evaluation.score.assert_ignored_artifact"), patch(
                "tools.independent_evaluation.score.verify_public", return_value={"sealed": True, "public_sha256": "digest"}
            ):
                with self.assertRaisesRegex(OracleError, "freeze receipt"):
                    evaluate_bundle(root, root / "output.csv", root / "report.json")
            self.assertFalse((root / "private" / "one-shot-evaluation.json").exists())

    def test_real_csv_sealed_one_shot_with_hand_authored_fixture(self):
        # This tiny fixture is NOT a held-out test world and has hand-set gold.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            public, private = root / "public", root / "private"
            public.mkdir()
            private.mkdir()
            (public / "universe.csv").write_text("id,text,date,label\na,Fixture one,2026-01-01,\nb,Fixture two,2026-01-01,\n")
            write_json(public / "lexicon.json", LEXICON)
            write_json(public / "context.json", {"contexts": []})
            (public / "POLICY.md").write_text("Hand-authored scorer test fixture, not a held-out world.\n")
            hashes = public_hashes(public)
            manifest = {"schema": SCHEMA, "sealed": True, "targets": 2,
                        "hashes": hashes, "public_sha256": digest_hashes(hashes)}
            write_json(public / "manifest.json", manifest)
            gold = [{"id": "a", "label": "true", "style": 0, "context": "explicit_subject", "distractor": False, "arity": 1,
                     "assertions": [{"value": val("percent", "50"), "op": "eq"}]},
                    {"id": "b", "label": "false", "style": 1, "context": "explicit_subject", "distractor": False, "arity": 1,
                     "assertions": [{"value": val("percent", "51"), "op": "eq"}]}]
            (private / "gold.jsonl").write_text("\n".join(json.dumps(row) for row in gold) + "\n")
            write_json(private / "metadata.json", {**manifest, "gold_sha256": sha256(private / "gold.jsonl")})
            executable = root / "fixture-solver.bin"
            executable.write_bytes(b"this is a scorer fixture, not an actual solver")
            output = root / "output.csv"
            output.write_text("id,type,text,form,label,confidence\na,,,,true,0.8\nb,,,,true,0.6\n")
            receipt = {"freeze_id": "fixture-only", "confirmed_by": "coordinator",
                       "confirmed_at_utc": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
                       "source_commit": "fixture-only", "source_tree_sha256": "a" * 64,
                       "training_and_selection_finished": True,
                       "evaluation_public_sha256": [manifest["public_sha256"]],
                       "solver_artifacts": [{"path": str(executable), "sha256": sha256(executable), "role": "solver"}]}
            receipt_path = root / "freeze.json"
            write_json(receipt_path, receipt)
            with patch("tools.independent_evaluation.score.assert_ignored_artifact"):
                result = evaluate_bundle(root, output, root / "report.json", receipt_path)
                self.assertEqual(result["target_accuracy"], .5)
                self.assertAlmostEqual(result["confidence_brier_correctness"]["score"], .2)
                self.assertEqual(json.loads((private / "one-shot-evaluation.json").read_text())["status"], "completed")
                with self.assertRaisesRegex(OracleError, "already has a scoring attempt"):
                    evaluate_bundle(root, output, root / "repeat-report.json", receipt_path)
            executable.write_bytes(b"changed")
            with self.assertRaisesRegex(OracleError, "changed"):
                validate_freeze(receipt_path, manifest, output)


class FactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lexicon = json.loads((ROOT / "data" / "lexicon.json").read_text(encoding="utf-8"))

    def test_factory_public_coverage_and_gold_semantics(self):
        world = make_world("ab12", self.lexicon)
        rows, gold, contexts = make_dataset(world, "ab12", 300)
        self.assertEqual(len(rows), 2197)
        self.assertEqual(sum(row["label"] == "true" for row in rows), 1897)
        self.assertEqual({tuple(row) for row in rows}, {("id", "text", "date", "label")})
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        self.assertTrue(all(row["text"].startswith("From ") and " through " in row["text"] for row in rows[:1897]))
        reconstructed, evidence = public_world(rows, self.lexicon)
        self.assertEqual(evidence["channels"], 96)
        self.assertEqual(evidence["unique_intervals"], 1440)
        self.assertEqual({a["value"]["kind"] for row in gold for a in row["assertions"]},
                         {"quantity", "money", "percent", "date", "version", "duration", "name", "boolean"})
        self.assertEqual({a["op"] for row in gold for a in row["assertions"]}, {"eq", "ne", "lt", "le", "gt", "ge"})
        primary_labels = {}
        for row in gold:
            primary = row["assertions"][0]
            key = (primary["subject"], primary["attribute"], channel(primary["value"]))
            primary_labels.setdefault(key, set()).add(row["label"])
        self.assertTrue(all(labels == set(LABELS) for labels in primary_labels.values()),
                        "primary subject/attribute/channel must never encode a constant row label")
        for feature in ("style", "context", "distractor", "arity"):
            feature_labels = {}
            for row in gold:
                feature_labels.setdefault(row[feature], set()).add(row["label"])
            self.assertTrue(all(labels == set(LABELS) for labels in feature_labels.values()), feature)
        by_id = {row["id"]: row for row in rows}
        for row in gold:
            label, parts = world.evaluate_all(row["assertions"], row["date"])
            self.assertEqual(label, row["label"])
            self.assertEqual(parts, row["components"])
            self.assertEqual(reconstructed.evaluate_all(row["assertions"], row["date"]), (label, parts))
            self.assertTrue(all(part["reason"] == "explicit_gap" for part in parts if part["label"] == "unsure"))
        for context in contexts:
            target = by_id[context["row_id"]]
            self.assertEqual(context["row_ids"], [target["id"]])
            self.assertEqual(context["scope"], "same_row_only")
            subject = resolve_public_context(target["text"], context, self.lexicon)
            self.assertIn(subject, {item["name"] for item in self.lexicon["subjects"]})

    def test_fresh_seeds_change_facts_not_just_row_order(self):
        a, b = make_world("ab12", self.lexicon), make_world("cd34", self.lexicon)
        self.assertEqual(set(a.timelines), set(b.timelines))
        self.assertTrue(any(a.timelines[key] != b.timelines[key] for key in a.timelines))

    def test_heldout_adds_unreleased_families_and_unknown_three_clause_rows(self):
        world = make_world("beef1234", self.lexicon)
        _, development, _ = make_dataset(world, "beef1234", 300)
        _, heldout, _ = make_dataset(world, "beef1234", 300, heldout=True)
        self.assertTrue(all(row["style"] < 12 for row in development))
        self.assertTrue(any(row["style"] >= 12 for row in heldout))
        self.assertTrue(any(row["arity"] == 3 and row["label"] == "unsure" for row in heldout))


if __name__ == "__main__":
    unittest.main()
