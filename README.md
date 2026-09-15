# OntoME Importer

Generic tooling to audit RDF/OWL ontologies and produce validated OntoME imports. Source ontology knowledge belongs in versioned configuration profiles, not application code.

## Development Installation

Python 3.10 or newer is required.

```bash
python -m pip install -e ".[test]"
```

## Verification

```bash
python tools/validate_phase0.py
pytest
```

Phase 0 contracts are documented in [docs/phase-0-contracts.md](docs/phase-0-contracts.md).
The supported RDF inventory formats are documented in [docs/phase-2-rdf-inventory.md](docs/phase-2-rdf-inventory.md).

## CLI

```bash
ontome-importer --help
ontome-importer --version
```

The public commands are `audit`, `generate`, and `validate`. They are declared in the CLI but intentionally unavailable until their respective implementation phases.

## Legacy Material

The notebooks and files under `input/`, `output/`, `data/`, and `references/` are historical reference material. They are not used by the package or its tests.
