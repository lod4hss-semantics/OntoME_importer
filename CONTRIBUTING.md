# Contributing

Keep ontology-specific URI, datatype, and mapping knowledge in versioned configuration, never in the Python core.

Before proposing a change, run:

```bash
python tools/validate_phase0.py
python tools/validate_contracts.py
pytest
```

Changes to schemas, XSD assets, profiles, or XML output require fixtures and deterministic regression tests. Do not alter generated release artifacts manually.
