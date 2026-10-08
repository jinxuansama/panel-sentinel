"""Schema-driven CSV panel validation using exact decimal parsing."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


def _decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def validate_schema(schema: object) -> dict:
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object")
    allowed = {"version", "entity", "entities", "period", "periods", "numeric", "units", "missing_tokens"}
    if set(schema) - allowed:
        raise ValueError(f"unknown schema fields: {sorted(set(schema) - allowed)}")
    if schema.get("version") != 1:
        raise ValueError("schema version must be 1")
    for key in ("entity", "period"):
        if not isinstance(schema.get(key), str) or not schema[key].strip():
            raise ValueError(f"{key} must name a column")
    if schema["entity"] == schema["period"]:
        raise ValueError("entity and period columns must differ")
    periods = schema.get("periods")
    if not isinstance(periods, list) or not periods or any(not isinstance(p, str) or not p.strip() for p in periods):
        raise ValueError("periods must be a non-empty list of strings")
    periods = [p.strip() for p in periods]
    if len(set(periods)) != len(periods):
        raise ValueError("periods must be unique after trimming")
    numeric = schema.get("numeric")
    if not isinstance(numeric, dict) or not numeric:
        raise ValueError("numeric must map at least one column to its rules")
    if {schema["entity"], schema["period"]} & set(numeric):
        raise ValueError("numeric columns cannot be entity or period keys")
    for column, rules in numeric.items():
        if not column or not isinstance(rules, dict) or set(rules) - {"min", "max", "allow_negative"}:
            raise ValueError(f"invalid numeric rules for {column}")
        if "allow_negative" in rules and type(rules["allow_negative"]) is not bool:
            raise ValueError(f"{column}.allow_negative must be boolean")
        bounds = {k: _decimal(v, f"{column}.{k}") for k, v in rules.items() if k in ("min", "max")}
        if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
            raise ValueError(f"{column}: min exceeds max")
    units = schema.get("units", {})
    if not isinstance(units, dict) or any(not k or not isinstance(v, str) or not v for k, v in units.items()):
        raise ValueError("units must map unit-column names to exact unit labels")
    tokens = schema.get("missing_tokens", ["", "NA", "N/A", "null"])
    if not isinstance(tokens, list) or any(not isinstance(t, str) for t in tokens):
        raise ValueError("missing_tokens must be a list of strings")
    if set(periods) & {t.strip() for t in tokens}:
        raise ValueError("periods cannot contain missing tokens")
    if "entities" in schema:
        registry = schema["entities"]
        if not isinstance(registry, list) or not registry or any(
            not isinstance(e, str) or not e.strip() for e in registry
        ):
            raise ValueError("entities must be a non-empty list of strings")
        labels = [e.strip() for e in registry]
        if len(set(labels)) != len(labels):
            raise ValueError("entities must be unique after trimming")
        if set(labels) & {t.strip() for t in tokens}:
            raise ValueError("entities cannot contain missing tokens")
    return schema


def audit_csv(csv_path: str | Path, schema: dict) -> dict:
    """Report key collisions, gaps, bounds, unit mismatches, and variation."""
    validate_schema(schema)
    path = Path(csv_path)
    blob = path.read_bytes()
    # Decode once so the reported digest identifies precisely the checked bytes.
    import io
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig"), newline=""))
    headers = reader.fieldnames
    if not headers or len(set(headers)) != len(headers):
        raise ValueError("CSV must have non-duplicate column headers")
    required = {schema["entity"], schema["period"]} | set(schema["numeric"]) | set(schema.get("units", {}))
    absent = required - set(headers)
    if absent:
        raise ValueError(f"CSV is missing required columns: {sorted(absent)}")

    issues, keys, entities = [], {}, defaultdict(set)
    values = defaultdict(lambda: defaultdict(list))
    missing = Counter()
    missing_tokens = {t.strip() for t in schema.get("missing_tokens", ["", "NA", "N/A", "null"])}
    period_labels = [p.strip() for p in schema["periods"]]
    expected_periods = set(period_labels)
    expected_entities = {e.strip() for e in schema["entities"]} if "entities" in schema else None
    row_count = 0

    def issue(code, message, row=None, column=None, entity=None, severity="error"):
        issues.append(dict(code=code, message=message, row=row, column=column, entity=entity, severity=severity))

    for record in reader:
        row_count += 1
        row = reader.line_num
        if None in record or any(v is None for v in record.values()):
            issue("malformed_row", "row width does not match header width", row)
            continue
        entity = record[schema["entity"]].strip()
        period = record[schema["period"]].strip()
        if expected_entities is not None and entity not in missing_tokens and entity not in expected_entities:
            issue("unexpected_entity", "entity is outside the declared panel", row, schema["entity"], entity)
        if entity in missing_tokens or period in missing_tokens:
            issue("missing_key", "entity and period must be present", row)
        else:
            key = entity, period
            if key in keys:
                issue("duplicate_key", f"duplicate entity-period key; first ends at line {keys[key]}", row, entity=entity)
            else:
                keys[key] = row
            entities[entity].add(period)
        if period not in expected_periods:
            issue("unexpected_period", "period is outside the declared panel", row, schema["period"], entity)
        for column, unit in schema.get("units", {}).items():
            if record[column].strip() != unit:
                issue("unit_mismatch", f"expected unit {unit!r}", row, column, entity)
        for column, rules in schema["numeric"].items():
            raw = record[column].strip()
            if raw in missing_tokens:
                missing[column] += 1
                issue("missing_numeric", "numeric value is missing", row, column, entity)
                continue
            try:
                value = _decimal(raw, column)
            except ValueError:
                issue("invalid_numeric", "value is not a finite number", row, column, entity)
                continue
            if not rules.get("allow_negative", True) and value < 0:
                issue("negative_value", "negative value is prohibited by the schema", row, column, entity)
            for bound, compare in (("min", lambda a, b: a < b), ("max", lambda a, b: a > b)):
                if bound in rules and compare(value, _decimal(rules[bound], bound)):
                    issue("out_of_bounds", f"value violates {bound}={rules[bound]}", row, column, entity)
            if entity not in missing_tokens and period in expected_periods:
                values[column][entity].append(value)

    if not row_count:
        issue("empty_panel", "CSV contains no data rows")
    gaps = {}
    gap_entities = set(entities) | (expected_entities or set())
    for entity in sorted(gap_entities):
        observed_periods = entities.get(entity, set())
        gaps[entity] = [p for p in period_labels if p not in observed_periods]
        if entity not in entities:
            issue("missing_entity", "no valid entity-period keys for expected entity",
                  entity=entity, severity="warning")
        if gaps[entity]:
            issue("panel_gap", f"missing periods: {', '.join(gaps[entity])}", entity=entity, severity="warning")
    variation = {}
    for column in schema["numeric"]:
        group = values[column]
        eligible = sorted(e for e, v in group.items() if len(v) >= 2)
        constant = sorted(e for e in eligible if len(set(group[e])) == 1)
        variation[column] = dict(entities_with_two_observations=len(eligible), constant_entities=constant)
        if constant:
            issue("no_within_variation", f"constant for {len(constant)} entities; inspect suitability for within estimators",
                  column=column, severity="warning")
    canonical_schema = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return dict(version=1, ok=not any(i["severity"] == "error" for i in issues),
                csv_sha256=hashlib.sha256(blob).hexdigest(), schema_sha256=hashlib.sha256(canonical_schema).hexdigest(),
                row_count=row_count, entity_count=len(entities), unique_key_count=len(keys),
                missing_numeric={c: missing[c] for c in schema["numeric"]}, gaps=gaps,
                within_variation=variation, issues=issues)
