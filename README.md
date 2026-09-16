# OntoME Importer

Generic tooling to audit RDF/OWL ontologies and produce validated OntoME imports. Source ontology knowledge belongs in versioned configuration profiles, not application code.

## Installation

Python 3.10 or newer is required.

```bash
python -m pip install ontome-importer
```

For development:

```bash
python -m pip install -e ".[test]"
```

## Verification

```bash
python tools/validate_phase0.py
python tools/validate_contracts.py
pytest
```

Phase 0 contracts are documented in [docs/phase-0-contracts.md](docs/phase-0-contracts.md).
The supported RDF inventory formats are documented in [docs/phase-2-rdf-inventory.md](docs/phase-2-rdf-inventory.md).
The audit workflow is documented in [docs/phase-3-audit.md](docs/phase-3-audit.md).
Resolution and XML generation are documented in [docs/phase-4-resolution-and-generation.md](docs/phase-4-resolution-and-generation.md).
Final bundle validation is documented in [docs/phase-5-validation.md](docs/phase-5-validation.md).

## CLI

```bash
ontome-importer --help
ontome-importer --version
```

`audit` is available with a version 1.1 import manifest. `generate` and `validate` are available with the complete version 1.0 manifest/capability contracts and mapping profile 2.0.

The complete operational flow is `audit`, `generate`, then `validate`. Validation is documented in [docs/phase-5-validation.md](docs/phase-5-validation.md).

## Operational Workflow

```bash
ontome-importer audit --manifest import-audit.yaml --output-dir build/audit
ontome-importer generate --manifest import.yaml --output-dir build/import
ontome-importer validate \
  --manifest import.yaml \
  --xml build/import/import.xml \
  --trace build/import/generation-trace.json \
  --audit build/import/generation-audit.json \
  --output build/import/validation.json
```

Exit code `0` means success. Code `2` indicates an unavailable or invalid source, profile, XSD, or output location. Code `3` indicates an audit, resolution, generation, or validation block. Archive the XML, trace, generation audit, validation report, manifest, profiles, and selected XSD together.

The full procedure and configuration guidance are in [docs/operational-workflow.md](docs/operational-workflow.md).
The versioned YAML formats are summarized in [docs/configuration.md](docs/configuration.md).

## Legacy Material

The notebooks and files under `input/`, `output/`, `data/`, and `references/` are historical reference material. They are not used by the package or its tests.
