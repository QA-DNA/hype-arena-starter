"""Regression checks for development metric normalization, separate from parsing."""
import unittest
from evaluate import normalize


def fact(kind, value, op=None, **channel):
    result = {"subject": "Atlas", "attribute": "field", "value": {"kind": kind, "value": value, **channel}}
    if op is not None:
        result["op"] = op
    return result


class NormalizationTests(unittest.TestCase):
    def test_decimal_strings_and_top_level_gold_operator(self):
        gold = fact("money", "339.940", "ge", currency="EUR", per="month")
        parsed = fact("money", 339.94, currency="EUR", per="month")
        parsed["value"]["op"] = "ge"
        self.assertEqual(normalize(gold, {}), normalize(parsed, {}))

    def test_default_eq_and_distinct_ne(self):
        self.assertEqual(normalize(fact("boolean", False), {}), normalize(fact("boolean", False, "eq"), {}))
        self.assertNotEqual(normalize(fact("boolean", False), {}), normalize(fact("boolean", False, "ne"), {}))

    def test_physical_units_and_case(self):
        self.assertEqual(normalize(fact("quantity", "1", unit="kW"), {}), normalize(fact("quantity", 1000, unit="W"), {}))
        self.assertNotEqual(normalize(fact("quantity", 1, unit="mW"), {}), normalize(fact("quantity", 1, unit="MW"), {}))

    def test_calendar_and_fixed_duration_channels(self):
        self.assertEqual(normalize(fact("duration", 1, unit="year"), {}), normalize(fact("duration", 12, unit="month"), {}))
        self.assertNotEqual(normalize(fact("duration", 1, unit="month"), {}), normalize(fact("duration", 30, unit="day"), {}))

    def test_billing_currency_precision_and_written_versions(self):
        self.assertNotEqual(normalize(fact("money", 12, currency="USD"), {}), normalize(fact("money", 12, currency="USD", per="month"), {}))
        self.assertNotEqual(normalize(fact("money", 12, currency="EUR"), {}), normalize(fact("money", 12, currency="USD"), {}))
        self.assertNotEqual(normalize(fact("date", "2026-03"), {}), normalize(fact("date", "2026-03-01"), {}))
        self.assertNotEqual(normalize(fact("version", "2.3"), {}), normalize(fact("version", "2.3.0"), {}))


if __name__ == "__main__":
    unittest.main()
