import tempfile
import unittest
from pathlib import Path

from panel_sentinel.core import audit_csv, validate_schema


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "panel.csv"
        self.schema = dict(version=1, entity="firm", period="year", periods=["2021", "2022"],
                           numeric={"profit": {"allow_negative": True}, "ratio": {"min": 0, "max": 1}},
                           units={"unit": "CNY_million"})

    def audit(self, body):
        self.file.write_text("firm,year,profit,ratio,unit\n" + body, encoding="utf-8")
        return audit_csv(self.file, self.schema)

    def codes(self, report):
        return {i["code"] for i in report["issues"]}

    def test_negative_profit_allowed(self):
        self.assertTrue(self.audit("A,2021,-2,0.1,CNY_million\nA,2022,3,0.2,CNY_million\n")["ok"])

    def test_unit_mismatch_is_explicit(self):
        self.assertIn("unit_mismatch", self.codes(self.audit("A,2021,2,0.1,CNY_yuan\n")))

    def test_duplicate_and_gap(self):
        self.assertTrue({"duplicate_key", "panel_gap"} <= self.codes(self.audit("A,2021,2,0.1,CNY_million\nA,2021,3,0.2,CNY_million\n")))

    def test_nonfinite_and_decimal_bounds(self):
        codes = self.codes(self.audit("A,2021,NaN,1.000000000000000000001,CNY_million\n"))
        self.assertTrue({"invalid_numeric", "out_of_bounds"} <= codes)

    def test_missing_cells(self):
        self.assertIn("missing_numeric", self.codes(self.audit("A,2021,,0.1,CNY_million\n")))

    def test_malformed_row(self):
        self.assertIn("malformed_row", self.codes(self.audit("A,2021,2,0.1,CNY_million,extra\n")))

    def test_duplicate_header_raises(self):
        self.file.write_text("firm,year,profit,ratio,unit,firm\n")
        with self.assertRaises(ValueError):
            audit_csv(self.file, self.schema)

    def test_unknown_rule_rejected(self):
        self.schema["numeric"]["profit"]["allow_negatve"] = True
        with self.assertRaises(ValueError):
            validate_schema(self.schema)

    def test_constant_within_entity_warns(self):
        report = self.audit("A,2021,2,0.1,CNY_million\nA,2022,2,0.2,CNY_million\n")
        self.assertTrue(report["ok"])
        self.assertEqual(report["within_variation"]["profit"]["constant_entities"], ["A"])

    def test_schema_and_data_digest_change(self):
        a = self.audit("A,2021,2,0.1,CNY_million\n")
        self.schema["numeric"]["profit"]["min"] = -100
        b = self.audit("A,2021,2,0.1,CNY_million\n")
        self.assertEqual(a["csv_sha256"], b["csv_sha256"])
        self.assertNotEqual(a["schema_sha256"], b["schema_sha256"])

    def test_empty_panel(self):
        self.assertFalse(self.audit("")["ok"])

    def test_unexpected_period(self):
        self.assertIn("unexpected_period", self.codes(self.audit("A,2030,2,0.1,CNY_million\n")))


if __name__ == "__main__":
    unittest.main()
