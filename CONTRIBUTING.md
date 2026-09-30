# Contributing

Install Python 3.10 or newer, clone this repository, and run:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Open an issue describing a reproducible problem, expected behaviour, and
a small synthetic example. Do not attach confidential data. Pull requests
should include a regression test for changed numerical or audit behaviour.
Keep the runtime dependency-free and document changed assumptions.

AI-assisted contributions are welcome. Contributors remain responsible
for reviewing code, checking provenance, and running tests. No generated
numbers should be presented as empirical research results.
