# Changelog

## 0.2.0 — 2026-10-07

Add an optional expected-entity registry to detect entities wholly absent from
the CSV and entities outside a known population. Missing entities remain
warnings; strict mode fails on them. Preserve observed entity counts and
existing schemas without a registry. Add seven regression tests for registry
validation, absent/unknown entities, CLI exit codes, and reproducibility.

## 0.1.0 — 2026-09-30

Initial implementation with a Python API, command-line interface,
synthetic examples, regression tests, and a GitHub Actions test workflow.
This is an early release; community adoption has not been measured.
