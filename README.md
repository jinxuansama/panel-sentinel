# Panel Sentinel

**Inspect a research panel before fitting a statistical model.**

[中文说明](README.zh-CN.md) · [Schema and design](docs/design.md) · [Contributing](CONTRIBUTING.md)

Panel Sentinel validates entity-period CSV data using a small JSON schema.
It finds duplicate keys, missing values, panel gaps, unexpected periods,
non-finite numbers, declared range violations, and explicit unit mismatches.
It also reports entities with no within-entity variation, helping researchers
inspect variables intended for within estimators.

Negative profits are allowed when the schema says so. Currency units and
percentage scales are declared, not guessed. The tool flags issues without
imputing missing observations, deleting rows, or rewriting values.

## Quick start

Python 3.10+, standard-library-only runtime:

```sh
python -m pip install .
panel-sentinel examples/clean.csv --schema examples/schema.json
panel-sentinel examples/broken.csv --schema examples/schema.json
python -m unittest discover -s tests -v
```

`clean.csv` passes with six rows, two entities, and no issues. `broken.csv`
intentionally fails: a duplicate, mixed units, a ratio outside [0,1], negative
assets, missing/NaN values, and panel gaps. All firms and values are synthetic.

```python
import json
from decimal import Decimal
from panel_sentinel.core import audit_csv
with open("examples/schema.json") as f:
    report = audit_csv("examples/clean.csv", json.load(f, parse_float=Decimal))
assert report["ok"]
```

`--output report.json` writes a deterministic JSON report. Reports include
hashes of checked CSV bytes and the canonical schema for reproducibility.
CLI exits 0 on success, 1 on errors, 2 on invalid input/I/O. `--strict` also
exits 1 on warnings such as gaps and no within variation.

## Boundaries

This is validation, not an estimator or a data-cleaning algorithm. It does
not compute DEA/MSBM, establish causality, diagnose statistical power, infer
undisclosed units, or certify that reported financial figures are accurate.
A constant variable warning is a review prompt, not proof of model failure.
Unbalanced panels may be intentional; gaps are warnings by default.
Without an expected-entity registry, the tool cannot discover entities wholly
absent from a CSV. Add an optional `"entities": ["synthetic_A", "synthetic_B"]`
to the schema to check a known population. Missing entities and their missing
periods are warnings (`--strict` fails); entities outside that list are errors.
Observed counts are not inflated by absent entities. Labels are case-sensitive
and trimmed; the registry must come from an independently checked source.

Version 0.2.0; MIT licensed, with original synthetic examples.
AI assisted implementation and tests. No institutional endorsement or
adoption metrics are claimed. [Roadmap](docs/roadmap.md).
