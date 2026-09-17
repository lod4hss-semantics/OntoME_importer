# OntoME Importer

Generic tooling to audit RDF/OWL ontologies and produce validated OntoME imports. Source ontology knowledge belongs in versioned configuration profiles, not application code.

## Start Here

Clone the repository, create a Python environment, and install the local tool:

```bash
git clone git@github.com:lod4hss-semantics/OntoME_importer.git
cd OntoME_importer
git switch cli_importer
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

The [User Guide](docs/user-guide.md) starts with `ontome-importer init`, which copies an RDF source and creates the workspace, profiles, and next commands automatically.

## Verification

```bash
python tools/validate_phase0.py
python tools/validate_contracts.py
pytest
```

The operational documentation is the [User Guide](docs/user-guide.md). Versioned configuration details are in the [Configuration Guide](docs/configuration.md).

## CLI

```bash
ontome-importer --help
ontome-importer --version
```

`init` creates a new import workspace. `audit` uses a manifest and mapping profile 1.1. `assist` offers an optional XLSX editing surface and compiles explicit decisions to YAML. `generate` and `validate` use the complete manifest/capability 1.0 contracts with mapping profile 2.0. Follow the [User Guide](docs/user-guide.md) for the full `init → audit → assist → generate → validate` workflow, files produced and exit codes.

## Legacy Material

The notebooks and files under `input/`, `output/`, `data/`, and `references/` are historical reference material. They are not used by the package or its tests.
