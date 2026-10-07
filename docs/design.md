# Schema and validation semantics

Schema version 1 requires `entity`, `period`, `periods` (unique non-empty
strings), and `numeric` (column-to-rule mappings). Unknown schema fields or
numeric rules are rejected to catch spelling errors.

| Field | Example | Semantics |
| --- | --- | --- |
| periods | ["2021", "2022"] | Expected labels; not inferred from observed dates |
| entities | ["synthetic_A", "synthetic_B"] | Optional known population; unique non-empty strings after trimming, excluding missing tokens |
| numeric | {"profit": {"allow_negative": true}} | All declared columns must be finite decimal values |
| min / max | 0 / 1 | Inclusive bounds, compared using Decimal |
| allow_negative | false | Explicit negative-value prohibition; default true |
| units | {"money_unit": "CNY_million"} | Every row must match the declared unit label exactly after trimming |
| missing_tokens | ["", "NA", "N/A", "null"] | Case-sensitive, trimmed missing markers; these are the defaults |

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
JSON. Reports contain no current timestamps and are reproducible. The CSV
is read into memory. This version offers no database connectors or Excel parsing.
