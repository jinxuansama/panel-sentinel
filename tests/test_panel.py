import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from panel_sentinel.core import audit_csv, validate_schema
from panel_sentinel.cli import main


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

    def test_periods_match_trimmed_labels_without_mutating_schema(self):
        self.schema["periods"] = [" 2021 ", "\t2022 "]
        original = json.dumps(self.schema)
        report = self.audit("A, 2021 ,2,0.1,CNY_million\nA,2022,3,0.2,CNY_million\n")
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["within_variation"]["profit"]["entities_with_two_observations"], 1)
        self.assertEqual(json.dumps(self.schema), original)
        self.assertEqual(report, audit_csv(self.file, self.schema))
        self.schema["periods"] = ["2021", "2022"]
        normalized = audit_csv(self.file, self.schema)
        self.assertNotEqual(report.pop("schema_sha256"), normalized.pop("schema_sha256"))
        self.assertEqual(report, normalized)

    def test_period_gaps_use_trimmed_labels_in_schema_order(self):
        self.schema["periods"] = [" 2023 ", " 2022 ", "2021"]
        self.schema["entities"] = ["A", "B"]
        report = self.audit("A,2021,2,0.1,CNY_million\n")
        self.assertEqual(report["gaps"], {"A": ["2023", "2022"], "B": ["2023", "2022", "2021"]})
        self.assertTrue(report["ok"])

    def test_periods_reject_duplicates_after_trimming(self):
        for periods in (["2021", " 2021 "], ["2021", "\t2021\n"]):
            with self.subTest(periods=periods), self.assertRaisesRegex(ValueError, "unique after trimming"):
                validate_schema(dict(self.schema, periods=periods))

    def test_periods_reject_default_and_custom_missing_tokens(self):
        for label in ("NA", " N/A ", "null"):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "periods cannot contain missing tokens"):
                validate_schema(dict(self.schema, periods=[label]))
        with self.assertRaisesRegex(ValueError, "periods cannot contain missing tokens"):
            validate_schema(dict(self.schema, periods=[" missing "], missing_tokens=["\tmissing "]))

    def test_period_missing_tokens_are_case_sensitive_and_overridable(self):
        self.schema["periods"] = ["na"]
        self.assertEqual(self.audit("A,na,2,0.1,CNY_million\n")["issues"], [])
        self.schema["periods"] = ["NA"]
        self.schema["missing_tokens"] = []
        self.assertEqual(self.audit("A,NA,2,0.1,CNY_million\n")["issues"], [])

    def test_invalid_period_schema_cli_exits_two_without_report(self):
        self.schema["periods"] = ["NA"]
        self.file.write_text("firm,year,profit,ratio,unit\nA,NA,2,0.1,CNY_million\n", encoding="utf-8")
        schema_file = Path(self.temp.name) / "schema.json"
        schema_file.write_text(json.dumps(self.schema), encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main([str(self.file), "--schema", str(schema_file)]), 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("periods cannot contain missing tokens", stderr.getvalue())

    def test_wholly_absent_entity_has_all_gaps_without_inflating_count(self):
        self.schema["entities"] = ["A", "B"]
        report = self.audit("A,2021,2,0.1,CNY_million\nA,2022,3,0.2,CNY_million\n")
        self.assertTrue(report["ok"])
        self.assertEqual(report["entity_count"], 1)
        self.assertEqual(report["gaps"], {"A": [], "B": ["2021", "2022"]})
        missing = [i for i in report["issues"] if i["code"] == "missing_entity"]
        self.assertEqual([i["entity"] for i in missing], ["B"])
        self.assertEqual(missing[0]["severity"], "warning")

    def test_unexpected_entity_is_error_and_kept_in_observed_counts(self):
        self.schema["entities"] = ["B"]
        report = self.audit("A,2021,2,0.1,CNY_million\n")
        self.assertFalse(report["ok"])
        self.assertEqual(report["entity_count"], 1)
        self.assertIn("unexpected_entity", self.codes(report))

    def test_registry_matches_trimmed_labels_without_mutating_schema(self):
        self.schema["entities"] = [" A "]
        report = self.audit(" A ,2021,2,0.1,CNY_million\nA,2022,3,0.2,CNY_million\n")
        self.assertEqual(report["issues"], [])
        self.assertEqual(self.schema["entities"], [" A "])

    def test_invalid_registries_rejected(self):
        for registry in (None, "A", [], [1], [""], [" "], ["A", " A "], ["NA"]):
            with self.subTest(registry=registry), self.assertRaises(ValueError):
                validate_schema(dict(self.schema, entities=registry))

    def test_registry_rejects_custom_missing_token(self):
        with self.assertRaises(ValueError):
            validate_schema(dict(self.schema, entities=[" missing "], missing_tokens=["missing"]))

    def test_invalid_key_does_not_satisfy_registry(self):
        self.schema["entities"] = ["A"]
        report = self.audit("A,,2,0.1,CNY_million\n")
        self.assertIn("missing_entity", self.codes(report))
        self.assertEqual(report["entity_count"], 0)

    def test_registry_cli_strict_exit_and_reproducibility(self):
        self.schema["entities"] = ["A", "B"]
        report = self.audit("A,2021,2,0.1,CNY_million\nA,2022,3,0.2,CNY_million\n")
        self.assertEqual(report, audit_csv(self.file, self.schema))
        schema_file = Path(self.temp.name) / "schema.json"
        schema_file.write_text(json.dumps(self.schema), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.file), "--schema", str(schema_file)]), 0)
            self.assertEqual(main([str(self.file), "--schema", str(schema_file), "--strict"]), 1)


class ExactBoundsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv = Path(self.temp.name) / "panel.csv"
        self.schema_file = Path(self.temp.name) / "schema.json"

    def run_cli(self, schema_text, value="1"):
        self.csv.write_text(f"firm,year,profit\nA,2021,{value}\n", encoding="utf-8")
        self.schema_file.write_text(schema_text, encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(self.csv), "--schema", str(self.schema_file), "--strict"])
        return code, stdout.getvalue(), stderr.getvalue()

    def bound_schema(self, bound, literal):
        return ('{"version":1,"entity":"firm","period":"year","periods":["2021"],'
                '"numeric":{"profit":{"' + bound + '":' + literal + '}}}')

    def test_cli_exact_lower_and_upper_bounds_are_inclusive(self):
        threshold = "1.000000000000000000001"
        for bound, value, expected in (
            ("min", "1", 1), ("min", threshold, 0), ("min", "1.000000000000000000002", 0),
            ("max", "1", 0), ("max", threshold, 0), ("max", "1.000000000000000000002", 1),
        ):
            with self.subTest(bound=bound, value=value):
                code, output, error = self.run_cli(self.bound_schema(bound, threshold), value)
                self.assertEqual(code, expected, error)
                report = json.loads(output)
                self.assertEqual(report["ok"], expected == 0)
                self.assertEqual([issue["code"] for issue in report["issues"]],
                                 ["out_of_bounds"] if expected else [])

    def test_cli_exact_number_forms_and_string_bounds(self):
        for bound, literal, value, expected in (
            ("min", "-1.000000000000000000001", "-1.000000000000000000002", 1),
            ("max", "-1.000000000000000000001", "-1.000000000000000000001", 0),
            ("min", "1.000000000000000000001e-1", "0.1", 1),
            ("max", "1.000000000000000000001E+1", "10.00000000000000000001", 0),
            ("min", "1e-400", "0", 1),
            ("min", "1e-400", "1e-400", 0),
            ("max", "1e400", "1e400", 0),
            ("max", "1e400", "1.0001e400", 1),
            ("max", "9007199254740993", "9007199254740993", 0),
            ("max", "9007199254740993", "9007199254740994", 1),
            ("max", '"1.000000000000000000001"', "1.000000000000000000001", 0),
        ):
            with self.subTest(bound=bound, literal=literal, value=value):
                code, output, error = self.run_cli(self.bound_schema(bound, literal), value)
                self.assertEqual(code, expected, error)
                self.assertEqual(json.loads(output)["ok"], expected == 0)

    def test_exact_schema_hash_preserves_numbers_and_precision(self):
        reports = []
        for literal in ("1.000000000000000000001", "1.000000000000000000002",
                        '"1.000000000000000000001"'):
            code, output, error = self.run_cli(self.bound_schema("max", literal))
            self.assertEqual(code, 0, error)
            report = json.loads(output)
            self.assertEqual(output, self.run_cli(self.bound_schema("max", literal))[1])
            reports.append(report)
        self.assertEqual(len({report["schema_sha256"] for report in reports}), 3)
        canonical = ('{"entity":"firm","numeric":{"profit":{"max":1.000000000000000000001}},'
                     '"period":"year","periods":["2021"],"version":1}')
        self.assertEqual(reports[0]["schema_sha256"], hashlib.sha256(canonical.encode()).hexdigest())

    def test_json_numbers_do_not_become_string_labels(self):
        schema = json.loads(self.bound_schema("max", "2"))
        for field, value in (("periods", [2021.0]), ("entities", [1.1]),
                             ("missing_tokens", [0.1]), ("units", {"unit": 0.1})):
            with self.subTest(field=field):
                code, output, error = self.run_cli(json.dumps(dict(schema, **{field: value})))
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertTrue(error.startswith("panel-sentinel:"))
        code, output, error = self.run_cli(json.dumps(dict(schema, version=1.0)))
        self.assertEqual(code, 0, error)
        self.assertTrue(json.loads(output)["ok"])

    def test_invalid_numeric_bounds_remain_invalid_input(self):
        for literal in ("true", "false", "null", "NaN", "Infinity", "-Infinity", '"invalid"',
                        "1e999999999999999999999999999999"):
            with self.subTest(literal=literal):
                code, output, error = self.run_cli(self.bound_schema("max", literal))
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertTrue(error.startswith("panel-sentinel:"))

    def test_api_decimal_bounds_and_legacy_schema_hash(self):
        schema = json.loads(self.bound_schema("max", "2.5"))
        self.csv.write_text("firm,year,profit\nA,2021,1.000000000000000000001\n", encoding="utf-8")
        canonical = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(audit_csv(self.csv, schema)["schema_sha256"], hashlib.sha256(canonical.encode()).hexdigest())
        bound = Decimal("1.000000000000000000001")
        schema["numeric"]["profit"]["max"] = bound
        report = audit_csv(self.csv, schema)
        self.assertTrue(report["ok"])
        self.assertIs(schema["numeric"]["profit"]["max"], bound)
        self.assertEqual(json.loads(json.dumps(report)), report)


if __name__ == "__main__":
    unittest.main()
