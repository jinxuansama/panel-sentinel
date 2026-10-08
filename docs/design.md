# Schema and validation semantics

Schema version 1 requires `entity`, `period`, `periods` (unique non-empty
strings after trimming, excluding missing tokens), and `numeric`
(column-to-rule mappings). Unknown schema fields or
numeric rules are rejected to catch spelling errors.

| Field | Example | Semantics |
| --- | --- | --- |
| periods | ["2021", "2022"] | Expected labels, compared after trimming; not inferred from observed dates |
| entities | ["synthetic_A", "synthetic_B"] | Optional known population; unique non-empty strings after trimming, excluding missing tokens |
| numeric | {"profit": {"allow_negative": true}} | All declared columns must be finite decimal values |
| min / max | 0 / 1 | Inclusive bounds, compared using Decimal |
| allow_negative | false | Explicit negative-value prohibition; default true |
| units | {"money_unit": "CNY_million"} | Every row must match the declared unit label exactly after trimming |
| missing_tokens | ["", "NA", "N/A", "null"] | Case-sensitive, trimmed missing markers; these are the defaults |

Period labels are case-sensitive. Leading and trailing whitespace is ignored
in both the schema and CSV; internal whitespace is preserved. Labels that
become duplicates after trimming, or match a configured missing token, are
invalid schema input. Gap lists use trimmed labels in schema order. These
comparisons do not modify the input schema or its digest.

The CLI reads JSON fractional and exponent-form numbers as exact Decimals,
so inclusive numeric bounds retain their stated precision. The Python API
also accepts Decimal or numeric-string bounds; when loading JSON, use
`json.load(file, parse_float=Decimal)`. A Python float has already been rounded
and the audit cannot recover its original decimal digits. Numeric JSON values
remain numbers for schema type validation.

Expected periods refer to each observed entity and, when `entities` is given,
each registered entity. An expected entity with no valid entity-period key gets
a `missing_entity` warning and a `panel_gap` listing all expected periods.
An entity outside the registry gets an `unexpected_entity` error at its CSV line.
Registry labels are case-sensitive and compared after trimming; validation does
not modify the input schema. `entity_count` remains the count of entities with
observed valid keys, including unexpected entities. No rows are fabricated.
Without a registry, wholly absent entities cannot be detected.

Gaps, missing entities, and constant variables are warnings; other data
violations are errors. `--strict` treats warnings as failure. Two or more finite values
are required for a constant-within-entity warning. Duplicates are not removed
before variation summaries; inspect and fix errors before interpreting them.
Additional CSV columns are allowed and ignored unless declared in the schema.

Diagnostics report the CSV physical line at which a record ends, which can
differ from its logical row for quoted multiline fields. Duplicate headers
are invalid input, and short/long records are errors. Empty panels fail.
The unit check validates a label, not the arithmetic scale of its numbers.

CSV digest covers exact bytes; schema digest covers sorted compact UTF-8
JSON. Decimal values are emitted as unquoted JSON numbers using their Decimal
string form, preserving precision, scale, and the distinction from strings.
Compared with earlier CLI versions, schema hashes can change for decimal or
exponent-form bounds previously rounded or reformatted as binary floats.
Reports contain no current timestamps and are reproducible. The CSV
is read into memory. This version offers no database connectors or Excel parsing.
