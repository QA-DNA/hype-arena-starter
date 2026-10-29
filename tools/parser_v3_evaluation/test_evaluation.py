"""Hand-authored oracle sentinels, factory audits and scorer boundary tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import audit, factory, oracle, score
from .io import ROOT, digest, load_json, load_jsonl, public_digest, public_hashes, write_json, write_jsonl


def value(kind, raw, **extra):
    return {"kind": kind, "value": raw, **extra}


def atom(raw="17", op="eq", subject="Hooly Docs", attribute="languages"):
    result = value("quantity", raw, unit="language")
    if op != "eq": result["op"] = op
    return {"type": "atom", "fact": {"subject": subject, "attribute": attribute, "value": result}}


class TypedOracleTests(unittest.TestCase):
    def test_eight_kinds(self):
        examples = [value("quantity", "17", unit="language"), value("money", "17.25", currency="RON", per="year"),
                    value("percent", "99.999"), value("date", "2034-02-12"), value("version", "12.10.4"),
                    value("duration", "14", unit="day"), value("name", "Ron LaFlame"), value("boolean", True)]
        self.assertEqual({oracle.typed(item)[0] for item in examples}, oracle.KINDS)
        self.assertTrue(all(oracle.compare(item, item) for item in examples))

    def test_raw_decimal_precision_above_binary_float_integer_range(self):
        a = value("quantity", "9007199254740993.0001", unit="seat")
        b = value("quantity", "9007199254740993.0002", unit="seat")
        self.assertFalse(oracle.compare(a, b))
        self.assertTrue(oracle.compare(b, a, "gt"))
        self.assertFalse(oracle.compare(a, value("quantity", float(a["value"]), unit="seat")))

    def test_trailing_zero_equivalence(self):
        self.assertTrue(oracle.compare(value("percent", "17.23000"), value("percent", "17.23")))

    def test_nonfinite_and_boolean_numerics_rejected(self):
        for raw in (True, False, None, "NaN", "Infinity", "-Infinity"):
            with self.subTest(raw=raw), self.assertRaises(ValueError): oracle.rational(raw)

    def test_exact_data_conversion(self):
        self.assertTrue(oracle.compare(value("quantity", "1.25", unit="GB"), value("quantity", "1250", unit="MB")))
        self.assertFalse(oracle.compare(value("quantity", "1", unit="GB"), value("quantity", "1024", unit="MB")))

    def test_physical_units_and_case(self):
        self.assertTrue(oracle.compare(value("quantity", "1", unit="in"), value("quantity", "0.0254", unit="m")))
        self.assertFalse(oracle.compare(value("quantity", "1", unit="mW"), value("quantity", "1", unit="W")))
        self.assertIsNone(oracle.compare(value("quantity", "1", unit="m"), value("quantity", "1", unit="M")))

    def test_duration_calendar_dimension_is_separate(self):
        self.assertTrue(oracle.compare(value("duration", "14", unit="day"), value("duration", "2", unit="week")))
        self.assertTrue(oracle.compare(value("duration", "12", unit="month"), value("duration", "1", unit="year")))
        self.assertIsNone(oracle.compare(value("duration", "30", unit="day"), value("duration", "1", unit="month")))

    def test_currency_and_billing_channels_are_separate(self):
        a = value("money", "17", currency="EUR", per="month")
        self.assertIsNone(oracle.compare(a, value("money", "17", currency="USD", per="month")))
        self.assertIsNone(oracle.compare(a, value("money", "204", currency="EUR", per="year")))
        self.assertIsNone(oracle.compare(a, value("money", "17", currency="EUR")))

    def test_versions_numeric_components_and_arity(self):
        self.assertTrue(oracle.compare(value("version", "2.10"), value("version", "2.9"), "gt"))
        self.assertFalse(oracle.compare(value("version", "2.3"), value("version", "2.3.0")))
        self.assertTrue(oracle.compare(value("version", "2.3.0"), value("version", "2.3"), "ne"))

    def test_date_precision_is_equality_not_coercion(self):
        self.assertFalse(oracle.compare(value("date", "2034"), value("date", "2034-01")))
        self.assertTrue(oracle.compare(value("date", "2034"), value("date", "2034-01"), "ne"))
        self.assertIsNone(oracle.compare(value("date", "2034"), value("date", "2034-01"), "lt"))
        self.assertTrue(oracle.compare(value("date", "2034-02-12"), value("date", "2034-02-13"), "lt"))
        with self.assertRaises(ValueError): oracle.typed(value("date", "2034-02-30"))

    def test_boolean_and_names_not_numeric_orderings(self):
        self.assertIsNone(oracle.compare(value("boolean", True), value("quantity", "1", unit="seat")))
        self.assertIsNone(oracle.compare(value("boolean", True), value("boolean", False), "gt"))
        self.assertIsNone(oracle.compare(value("name", "Holdan"), value("name", "Hoovar"), "lt"))

    def test_all_six_operators(self):
        a, b = value("percent", "41.25"), value("percent", "41.26")
        expected = {"eq": False, "ne": True, "lt": True, "le": True, "gt": False, "ge": False}
        for op, truth in expected.items(): self.assertIs(oracle.compare(a, b, op), truth)


class ScopeTests(unittest.TestCase):
    def world(self, truth_a, truth_b):
        entries = []
        for subject, truth in (("Hooly Docs", truth_a), ("Hooly Gemini", truth_b)):
            threshold = value("quantity", "17", unit="language")
            actual = None if truth is None else value("quantity", "17" if truth else "18", unit="language")
            entries.append({"subject": subject, "attribute": "languages", "channel": threshold, "value": actual})
        return entries

    def test_exhaustive_kleene_connectives(self):
        a, b = atom(), atom(subject="Hooly Gemini")
        for left, right in product((True, False, None), repeat=2):
            world = self.world(left, right)
            expected_all = False if False in (left, right) else None if None in (left, right) else True
            expected_any = True if True in (left, right) else None if None in (left, right) else False
            self.assertIs(oracle.evaluate(factory.connective("all", a, b), world), expected_all)
            self.assertIs(oracle.evaluate(factory.connective("any", a, b), world), expected_any)
            self.assertIs(oracle.evaluate(factory.neg(a), world), None if left is None else not left)

    def test_nested_scope_is_not_a_flat_leaf_set(self):
        a, b, c = atom(), atom(subject="Hooly Gemini"), atom(subject="Hooly Translate", attribute="languages_supported")
        left = factory.connective("all", factory.connective("any", a, b), c)
        right = factory.connective("any", a, factory.connective("all", b, c))
        self.assertNotEqual(oracle.canonical_ast(left), oracle.canonical_ast(right))
        self.assertEqual({oracle.canonical_fact(x) for x in oracle.assertions(left)}, {oracle.canonical_fact(x) for x in oracle.assertions(right)})

    def test_demorgan_and_operator_inversion(self):
        a, b = atom(op="gt"), atom(subject="Hooly Gemini", op="le")
        left = factory.neg(factory.connective("all", a, b))
        right = factory.connective("any", atom(op="le"), atom(subject="Hooly Gemini", op="gt"))
        self.assertEqual(oracle.canonical_ast(left), oracle.canonical_ast(right))

    def test_boolean_negative_equivalence(self):
        a = factory.node(factory.Slot("Hooly", "fully_remote", "boolean"), value("boolean", True))
        b = factory.node(factory.Slot("Hooly", "fully_remote", "boolean"), value("boolean", False))
        self.assertEqual(oracle.canonical_ast(factory.neg(a)), oracle.canonical_ast(b))

    def test_comparison_references_without_invented_constants(self):
        ast = {"type": "compare", "left": {"subject": "Hooly Docs", "attribute": "languages"}, "op": "lt",
               "right": {"subject": "Hooly Gemini", "attribute": "languages"}}
        world = self.world(True, False)
        self.assertIs(oracle.evaluate(ast, world), True)
        self.assertEqual(oracle.assertions(ast), [])


class FactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.gold = factory.build_cases("development", "test-only-20261029")
        cls.lexicon = load_json(ROOT / "data/lexicon.json")

    def test_balanced_families_all_kinds_and_internal_labels(self):
        result = audit.audit_cases(self.rows, self.gold, self.lexicon)
        self.assertEqual(result["rows"], 512)
        self.assertEqual(set(result["family_counts"].values()), {32})
        self.assertEqual(set(result["typed_assertion_counts"]), oracle.KINDS)
        self.assertEqual(result["truth_only_metamorphic_pairs"], 16)
        for family in ("typed_exact", "multi_entity", "multi_clause", "nested_scope"):
            counts = {name: sum(x["family"] == family and x["semantic_truth"] == name for x in self.gold) for name in ("true", "false", "unsure")}
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_exposed_inputs_have_no_prebound_owner_candidates_or_gold(self):
        for row in self.rows:
            self.assertEqual(set(row), {"id", "document_id", "text", "context"})
            self.assertNotIn("candidates", row)
            self.assertNotIn("family", row)
            self.assertNotIn("expected", row)

    def test_pronouns_only_resolve_under_same_explicit_document(self):
        by_id = {row["id"]: row for row in self.rows}
        for item in self.gold:
            row = by_id[item["id"]]
            if item["family"] == "pronouns_enabled":
                self.assertTrue(row["context"]["enabled"])
                self.assertEqual(row["document_id"], row["context"]["document_id"])
                self.assertIsNotNone(item["ast"])
            elif item["family"] == "document_bounds":
                self.assertIsNone(item["ast"])
                self.assertEqual(item["assertions"], [])

    def test_ambiguous_language_never_selects_a_source_id(self):
        for item in self.gold:
            if item["family"] == "ambiguous_ownership":
                self.assertIsNone(item["ast"])
                self.assertEqual(item["assertions"], [])
                self.assertIn("unresolved", item["acceptable_statuses"])

    def test_most_cases_have_distinct_wordings_and_only_declared_pairs_duplicate(self):
        self.assertGreaterEqual(len({row["text"] for row in self.rows}), 450)

    def test_gold_tampering_is_detected(self):
        gold = deepcopy(self.gold)
        item = next(x for x in gold if x["semantic_truth"] in {"true", "false"})
        item["semantic_truth"] = "false" if item["semantic_truth"] == "true" else "true"
        with self.assertRaises(ValueError): audit.audit_cases(self.rows, gold, self.lexicon)


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.gold = factory.build_cases("development", "scorer-sentinels")
        cls.lexicon = load_json(ROOT / "data/lexicon.json")
        cls.perfect = {item["id"]: {"id": item["id"], "status": item["acceptable_statuses"][0], "ast": item["ast"],
                        "assertions": item["assertions"], "notes": list(item["note_categories"])} for item in cls.gold}

    def test_independently_supplied_gold_predictions_score_exactly(self):
        report = score.score_cases(self.rows, self.gold, self.perfect, self.lexicon)
        self.assertEqual(report["parse_exact_accuracy"], 1)
        self.assertEqual(report["assertion_set_exact_accuracy"], 1)
        self.assertEqual(report["full_contract_accuracy"], 1)
        self.assertEqual(report["semantic_truth_accuracy"], 1)

    def test_abstention_is_correct_only_where_expected(self):
        predictions = {row["id"]: {"id": row["id"], "status": "unresolved", "ast": None, "assertions": [], "notes": ["missing_subject unknown approximate"]} for row in self.rows}
        report = score.score_cases(self.rows, self.gold, predictions, self.lexicon)
        self.assertLess(report["parse_exact_accuracy"], .25)
        self.assertEqual(report["ast_coverage"], 0)
        self.assertIsNone(report["semantic_with_ast_accuracy"])

    def test_scope_error_does_not_hide_behind_correct_assertions(self):
        gold = next(item for item in self.gold if item["ast"] and item["ast"]["type"] == "any")
        prediction = deepcopy(self.perfect[gold["id"]])
        prediction["ast"]["type"] = "all"
        report = score.score_cases([], [gold], {gold["id"]: prediction}, self.lexicon)
        self.assertEqual(report["assertion_set_exact_accuracy"], 1)
        self.assertEqual(report["ast_scope_exact_accuracy"], 0)

    def test_numeric_rounding_changes_assertion_score(self):
        item = next(x for x in self.gold if x["family"] == "raw_precision")
        prediction = deepcopy(self.perfect[item["id"]])
        prediction["assertions"][0]["value"]["value"] = "42"
        report = score.score_cases([], [item], {item["id"]: prediction}, self.lexicon)
        self.assertEqual(report["assertion_set_exact_accuracy"], 0)

    def test_gold_or_label_fields_in_predictions_do_not_override_oracle(self):
        predictions = deepcopy(self.perfect)
        for item in predictions.values(): item.update(gold=True, semantic_truth="false", label="false")
        report = score.score_cases(self.rows, self.gold, predictions, self.lexicon)
        self.assertEqual(report["semantic_truth_accuracy"], 1)

    def test_nuisance_run_comparison_catches_changed_owner(self):
        variant = deepcopy(self.perfect)
        identity = next(item["id"] for item in self.gold if item["assertions"])
        variant[identity]["assertions"][0]["subject"] = "Hooly Translate"
        report = score.score_cases(self.rows, self.gold, self.perfect, self.lexicon, {"reverse_candidates": variant})
        self.assertEqual(report["metamorphic"]["adapter_variants"]["reverse_candidates"]["ownership_stable"], 511)

    def test_malformed_ast_is_invalid_not_a_scorer_crash(self):
        identity = self.gold[0]["id"]
        predictions = {identity: {"id": identity, "status": "parsed", "ast": [], "assertions": [], "notes": []}}
        report = score.score_cases(self.rows, self.gold, predictions, self.lexicon)
        self.assertEqual(report["counts"]["invalid_predictions"], 1)


class BundleBoundaryTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "artifacts").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="parser-v3-unit-", dir=ROOT / "artifacts")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "development"
        factory.write_bundle(self.bundle, "development", "bundle-test-only")
        self.rows = load_jsonl(self.bundle / "public/input.jsonl")
        self.gold = load_jsonl(self.bundle / "private/gold.jsonl")
        self.prediction_path = self.root / "predictions.jsonl"
        write_jsonl(self.prediction_path, [{"id": x["id"], "status": x["acceptable_statuses"][0], "ast": x["ast"],
                    "assertions": x["assertions"], "notes": x["note_categories"]} for x in self.gold])

    def final_fixture(self):
        # This is development data relabeled for gate tests, never real final data.
        manifest = load_json(self.bundle / "manifest.json")
        manifest["split"] = "final"
        write_json(self.bundle / "manifest.json", manifest)
        return manifest

    def freeze_fixture(self, manifest):
        snapshot, solver = self.root / "source.txt", self.root / "solver.txt"
        snapshot.write_text("test source snapshot", encoding="utf-8")
        solver.write_text("test solver artifact", encoding="utf-8")
        receipt = self.root / "freeze.json"
        write_json(receipt, {"freeze_id": "unit-test-only", "confirmed_by": "coordinator", "training_and_selection_finished": True,
            "source_commit": "unit-test-fixture", "source_tree_sha256": digest(snapshot), "confirmed_at_utc": "2020-01-01T00:00:00Z",
            "evaluation_public_sha256": [manifest["public_bundle_sha256"]],
            "solver_artifacts": [{"path": str(solver), "role": "solver", "sha256": digest(solver)},
                                 {"path": str(snapshot), "role": "source_snapshot", "sha256": digest(snapshot)}]})
        return receipt

    def test_existing_bundle_and_reports_are_never_overwritten(self):
        with self.assertRaises(ValueError): factory.write_bundle(self.bundle, "development", "another")
        report = self.root / "score.json"
        score.score_bundle(self.bundle, self.prediction_path, report)
        with self.assertRaises(ValueError): score.score_bundle(self.bundle, self.prediction_path, report)

    def test_final_seed_cannot_be_chosen(self):
        with self.assertRaises(ValueError): factory.write_bundle(self.root / "reserved", "final", "chosen")

    def test_public_tampering_detected(self):
        with (self.bundle / "public/input.jsonl").open("a", encoding="utf-8") as output: output.write("{}\n")
        with self.assertRaises(ValueError): audit.audit_bundle(self.bundle)

    def test_duplicate_prediction_ids_rejected(self):
        first = load_jsonl(self.prediction_path)[0]
        write_jsonl(self.prediction_path, [first, first])
        with self.assertRaises(ValueError): score.predictions_by_id(self.prediction_path, self.rows)

    def test_final_public_audit_cannot_open_gold(self):
        self.final_fixture()
        original = audit.load_jsonl
        def guarded(path):
            self.assertNotIn("private", str(path))
            return original(path)
        with patch.object(audit, "load_jsonl", guarded): self.assertFalse(audit.audit_bundle(self.bundle)["gold_opened"])
        with self.assertRaises(ValueError): audit.audit_bundle(self.bundle, include_gold=True)

    def test_final_without_freeze_never_reads_gold(self):
        self.final_fixture()
        original = score.load_jsonl
        def guarded(path):
            self.assertNotIn("private", str(path))
            return original(path)
        with patch.object(score, "load_jsonl", guarded), self.assertRaises(ValueError):
            score.score_bundle(self.bundle, self.prediction_path, self.root / "score.json")
        self.assertFalse((self.bundle / "private/one-shot-evaluation.json").exists())

    def test_final_marker_precedes_gold_and_second_score_is_refused(self):
        receipt = self.freeze_fixture(self.final_fixture())
        original = score.load_jsonl
        def guarded(path):
            if "private" in str(path): self.assertTrue((self.bundle / "private/one-shot-evaluation.json").exists())
            return original(path)
        with patch.object(score, "load_jsonl", guarded):
            self.assertEqual(score.score_bundle(self.bundle, self.prediction_path, self.root / "score.json", receipt)["parse_exact_accuracy"], 1)
        with self.assertRaises(FileExistsError): score.score_bundle(self.bundle, self.prediction_path, self.root / "score-second.json", receipt)

    def test_final_rejects_changed_solver_and_late_freeze(self):
        manifest = self.final_fixture()
        receipt_path = self.freeze_fixture(manifest)
        receipt = load_json(receipt_path)
        receipt["confirmed_at_utc"] = "2099-01-01T00:00:00Z"
        write_json(receipt_path, receipt)
        with self.assertRaises(ValueError): score.validate_freeze(self.bundle, receipt_path, [self.prediction_path])
        receipt["confirmed_at_utc"] = "2020-01-01T00:00:00Z"
        Path(receipt["solver_artifacts"][0]["path"]).write_text("changed", encoding="utf-8")
        write_json(receipt_path, receipt)
        with self.assertRaises(ValueError): score.validate_freeze(self.bundle, receipt_path, [self.prediction_path])


if __name__ == "__main__": unittest.main()
