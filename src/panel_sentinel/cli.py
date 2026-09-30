import argparse
import csv
import json
import sys
from pathlib import Path

from .core import audit_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description="Schema-driven panel CSV validation")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="also fail on warnings")
    args = parser.parse_args(argv)
    try:
        report = audit_csv(args.csv, json.loads(args.schema.read_text(encoding="utf-8")))
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0 if report["ok"] and not (args.strict and report["issues"]) else 1
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"panel-sentinel: {exc}", file=sys.stderr)
        return 2
