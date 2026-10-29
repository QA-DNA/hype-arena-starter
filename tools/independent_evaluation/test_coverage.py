"""Hand-authored contract regressions; no generated gold or production imports."""

import json
import unittest
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from .claims import ClaimOracle, score_claim_rows, text_check
from .coverage_audit import audit_coverage, compare_reports
from .grammar import parse_value
from .oracle import OracleError, World, channel, compare, normalized


LEXICON = {"subjects": [
    {"name": "Aster", "aliases": [], "attributes": ["employees"]},
    {"name": "Aster Mini 2026", "aliases": ["Mini"], "attributes": [
        "screen_size", "price", "encryption_at_rest", "storage", "released",
        "stable_version", "latency", "market_share", "lead", "employees",
    ]},
    {"name": "Jo Vale", "aliases": ["Jo"], "attributes": ["joined"]},
], "events": []}


def val(kind, raw, **fields):
    return {"kind": kind, "value": raw, **fields}


def form(attribute="screen_size", value=None):
    return {"subject": "Aster Mini 2026", "attribute": attribute,
            "value": value if value is not None else val("quantity", 5, unit="inch")}


def world(unknown=False):
    return World([{
        "subject": "Aster Mini 2026", "attribute": "screen_size", "channel": "quantity:length",
        "segments": [
            {"start": "2026-01-01", "end": "2026-06-30", "value": val("quantity", 127, unit="mm")},
            {"start": "2026-07-01", "end": "2026-12-31",
             "value": None if unknown else val("quantity", 254, unit="mm"),
             "reason": "explicit_gap" if unknown else ""},
        ],
    }], LEXICON)


class PhysicalUnitCoverageTests(unittest.TestCase):
    def test_public_word_aliases_have_hand_computed_dimensions_and_factors(self):
        cases = [
            ("inch", "1", "cm", "2.54"), ("inches", "5", "mm", "127"),
            ("INCHES", "0.1", "m", "0.00254"),
            ("millimetres", "1000", "m", "1"), ("Millimeters", "10", "cm", "1"),
            ("centimeter", "250", "m", "2.5"), ("metres", "3", "cm", "300"),
            ("kilometers", "2", "m", "2000"),
            ("bytes", "3000", "KB", "3"), ("kilobytes", "2", "B", "2000"),
            ("megabyte", "2", "KB", "2000"), ("Gigabytes", "1", "MB", "1000"),
            ("gigs", "2", "MB", "2000"), ("terabytes", "1", "GB", "1000"),
            ("kB", "1", "B", "1000"), ("kb", "1", "B", "1000"),
            ("mb", "1", "B", "1000000"), ("gb", "1", "MB", "1000"),
            ("tb", "1", "GB", "1000"),
            ("grammes", "1000", "kg", "1"), ("grams", "3000", "kg", "3"),
            ("kilograms", "2", "g", "2000"), ("KILOS", "2", "g", "2000"),
            ("hertz", "1000", "kHz", "1"), ("kilohertz", "2", "Hz", "2000"),
            ("megahertz", "1", "kHz", "1000"), ("gigahertz", "1", "MHz", "1000"),
            ("milliwatts", "3000", "W", "3"), ("watts", "1000", "kW", "1"),
            ("kilowatt", "1", "W", "1000"),
        ]
        for alias, amount, unit, expected in cases:
            with self.subTest(alias=alias):
                self.assertEqual(compare(val("quantity", amount, unit=alias),
                                         val("quantity", expected, unit=unit), "eq", {}), "true")
                parsed = parse_value(amount + " " + alias, "quantity", {})
                self.assertEqual(compare(parsed, val("quantity", expected, unit=unit), "eq", {}), "true")

    def test_exact_inch_factor_has_no_tolerance_or_float_rounding(self):
        inch = val("quantity", "1", unit="inch")
        self.assertEqual(channel(inch), "quantity:length")
        self.assertEqual(normalized(inch, {}), Fraction(127, 5000))
        self.assertEqual(compare(inch, val("quantity", "2.5400000000000001", unit="cm"), "eq", {}), "false")
        self.assertEqual(compare(inch, val("quantity", "2.5400000000000001", unit="cm"), "lt", {}), "true")

    def test_case_sensitive_symbols_unknown_units_and_dimensions_do_not_collapse(self):
        for unit in ("MW", "mw", "Kw", "KHz", "b", "kibibyte", "inchworm"):
            with self.subTest(unit=unit), self.assertRaises(OracleError):
                compare(val("quantity", 1, unit=unit), val("quantity", 1, unit="W"), "eq", {})
        for unit in ("employee", "customer", "kg", "GB"):
            with self.subTest(unit=unit), self.assertRaises(OracleError):
                compare(val("quantity", 1, unit="inch"), val("quantity", 1, unit=unit), "eq", {})

    def test_alias_fact_true_false_and_gap_are_semantic_results(self):
        oracle = ClaimOracle(world())
        for amount, expected in ((10, "true"), (5, "false")):
            with self.subTest(amount=amount):
                self.assertEqual(oracle.evaluate("fact", form(value=val("quantity", amount, unit="inch")))["status"], expected)
        self.assertEqual(ClaimOracle(world(unknown=True)).evaluate("fact", form())["status"], "unsure")
        self.assertEqual(oracle.evaluate("fact", form(value=val("quantity", 10, unit="inchworm")))["status"], "unsupported")

    def test_alias_change_witness_and_reverse_false(self):
        oracle = ClaimOracle(world())
        claim = {"subject": "Mini", "attribute": "screen_size",
                 "from": val("quantity", 5, unit="inches"), "to": val("quantity", 10, unit="inch")}
        result = oracle.evaluate("change", claim)
        self.assertEqual(result["status"], "true")
        self.assertEqual(result["witness_dates"], ["2026-01-01", "2026-07-01"])
        self.assertEqual(oracle.evaluate("change", dict(claim, **{"from": claim["to"], "to": claim["from"]}))["status"], "false")


class BoundedFactCoverageTests(unittest.TestCase):
    def setUp(self):
        self.world = world()

    def test_record_template_all_eight_kinds_with_independent_expected_values(self):
        cases = [
            ("screen_size", "12.7 centimeters", val("quantity", 5, unit="inch")),
            ("price", "EUR 12.50 per month", val("money", Decimal("12.5"), currency="EUR", per="month")),
            ("market_share", "72.105%", val("percent", Decimal("72.105"))),
            ("released", "2026-10-14", val("date", "2026-10-14")),
            ("stable_version", "v2.10.0", val("version", "2.10.0")),
            ("latency", "2 min", val("duration", 120, unit="s")),
            ("lead", "Jo", val("name", "Jo Vale")),
            ("encryption_at_rest", "not", val("boolean", False)),
        ]
        for attribute, text_value, value in cases:
            with self.subTest(attribute=attribute):
                text = "Aster Mini 2026 " + attribute.replace("_", " ") + " is " + text_value + "."
                self.assertEqual(text_check("fact", form(attribute, value), text, self.world)["status"], "supported_valid")

    def test_currency_prefix_is_exact_and_preserves_currency_and_period(self):
        expected = val("money", Decimal("12.50"), currency="EUR", per="month")
        for text in ("EUR 12.50 per month", "12.50 EUR per month", "€12.50 per month"):
            self.assertEqual(compare(parse_value(text, "money", {}), expected, "eq", {}), "true")
        for text in ("USD 12.50 per month", "EUR 12.50", "EUR 12.50 per year"):
            with self.subTest(text=text), self.assertRaises(OracleError):
                compare(parse_value(text, "money", {}), expected, "eq", {})

    def test_boolean_literal_polarity_must_match_and_name_the_attribute(self):
        for token, polarity in (("yes", True), ("no", False), ("not", False)):
            text = "Aster Mini 2026 encryption at rest is " + token + "."
            self.assertEqual(text_check("fact", form("encryption_at_rest", val("boolean", polarity)), text, self.world)["status"], "supported_valid")
            self.assertEqual(text_check("fact", form("encryption_at_rest", val("boolean", not polarity)), text, self.world)["status"], "invalid")
        result = text_check("fact", form("encryption_at_rest", val("boolean", False)),
                            "Aster Mini 2026 has not.", self.world)
        self.assertEqual(result["status"], "invalid")

    def test_supported_template_detects_wrong_number_and_version_precision(self):
        cases = [
            (form(), "Aster Mini 2026 screen size is 5.1 inch."),
            (form("stable_version", val("version", "2.3.0")), "Aster Mini 2026 stable version is v2.3."),
        ]
        for claim, text in cases:
            self.assertEqual(text_check("fact", claim, text, self.world)["status"], "invalid")

    def test_extra_values_dates_negation_approximation_and_unmatched_attribute_never_certify(self):
        for text in (
            "Aster Mini 2026 screen size is 5 inch or 6 inch.",
            "Aster Mini 2026 screen size is 5 inch in March 2026.",
            "Aster Mini 2026 screen size is 5 inch in March.",
            "Aster Mini 2026 screen size is not 5 inch.",
            "Aster Mini 2026 screen size is about 5 inch.",
            "Aster Mini 2026 screen size is 5 inch, up from 4 inch.",
            "Aster Mini 2026 screen size is 5 inch. It used to be larger.",
            "Aster Mini 2026 weight is 5 inch.",
            "Aster Mini 2026 screen size is 5\u200b inch.",
        ):
            with self.subTest(text=text):
                self.assertNotEqual(text_check("fact", form(), text, self.world)["status"], "supported_valid")
        for prefix in ("over", "at least", "under", "no more than"):
            result = text_check("fact", form(), "Aster Mini 2026 screen size is " + prefix + " 5 inch.", self.world)
            self.assertEqual(result["status"], "invalid")

    def test_longer_subject_and_separate_sentence_cannot_lend_the_name(self):
        claim = {"subject": "Aster", "attribute": "employees", "value": val("quantity", 5, unit="employee")}
        result = text_check("fact", claim, "Aster Mini 2026 employees is 5 employee.", self.world)
        self.assertEqual(result["status"], "invalid")
        self.assertNotEqual(text_check("fact", form(), "Aster Mini 2026 is compact. Its screen size is 5 inch.", self.world)["status"], "supported_valid")

    def test_false_world_and_text_mismatch_stay_separate(self):
        rows = []
        for index, (amount, text) in enumerate(((5, "5 inch"), (10, "11 inch"), (10, "10 inch"))):
            rows.append({"id": "claim-" + str(index), "type": "fact", "form": json.dumps(form(value=val("quantity", amount, unit="inch"))),
                         "text": "Aster Mini 2026 screen size is " + text + ".", "confidence": ".9", "label": "true"})
        result = score_claim_rows(rows, [], self.world)
        self.assertEqual(result["world_truth"], {"false": 1, "true": 2})
        self.assertEqual(result["text_grammar"], {"supported_valid": 2, "invalid": 1})
        self.assertEqual(result["false_claims"], 1)
        self.assertEqual(result["unsupported_world_claims"], 0)
        self.assertEqual(result["certified_by_bounded_checks"], 1)


class CoverageAuditTests(unittest.TestCase):
    def test_exact_changed_rows_include_text_forms_and_both_reasons(self):
        row = {"id": "c1", "type": "fact", "text": "Mini screen size is 10 inch.",
               "form": json.dumps(form(value=val("quantity", 10, unit="inch")))}
        before = score_claim_rows([dict(row, label="true", confidence=".9")], [], world())
        after = deepcopy(before)
        before["records"][0]["world_truth"] = {"status": "unsupported", "reason": "undeclared_world_fact_or_channel"}
        before["records"][0]["text_grammar"] = {"status": "unsupported", "reason": "fact_wording_outside_bounded_text_checker"}
        before["records"][0]["certified_by_bounded_checks"] = False
        result = compare_reports(before, after, [row])
        self.assertEqual(result["world_changed_ids"], ["c1"])
        self.assertEqual(result["text_changed_ids"], ["c1"])
        self.assertEqual(result["changed_rows"][0]["text"], row["text"])
        self.assertEqual(result["changed_rows"][0]["form_json"], row["form"])
        self.assertEqual(result["changed_rows"][0]["after"]["world_truth"]["reason"], "as_of_value")

    def test_audit_refuses_to_hide_any_existing_false_world_verdict(self):
        row = {"id": "c1", "type": "fact", "text": "Mini screen size is 5 inch.",
               "form": json.dumps(form()), "confidence": ".9", "label": "true"}
        before = score_claim_rows([row], [], world())
        self.assertEqual(before["records"][0]["world_truth"]["status"], "false")
        for status in ("unsupported", "true", "unsure"):
            after = deepcopy(before)
            after["records"][0]["world_truth"] = {"status": status, "reason": "regression"}
            with self.subTest(status=status), self.assertRaisesRegex(OracleError, "existing world verdict"):
                compare_reports(before, after, [row])

    def test_audit_refuses_sealed_before_reading_predictions_or_baseline(self):
        with patch("tools.independent_evaluation.coverage_audit.verify_public", return_value={"sealed": True}), \
                patch("tools.independent_evaluation.coverage_audit.read_csv") as read:
            with self.assertRaisesRegex(OracleError, "development-only"):
                audit_coverage(Path("unused"), Path("unused.csv"), Path("unused.json"), Path("unused-output"))
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
