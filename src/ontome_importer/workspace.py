"""Create a reproducible audit and generation workspace from an RDF source."""

from __future__ import annotations

import hashlib
from importlib import resources
import json
from pathlib import Path
import os
import shutil
import tempfile
from urllib.parse import urlparse

from ontome_importer.loader import load_inventory
from ontome_importer.profiles import load_audit_profiles, verify_capability_xsd


SUPPORTED_FORMATS = {"turtle", "rdfxml", "ntriples"}
FORMAT_EXTENSIONS = {".ttl": "turtle", ".nt": "ntriples", ".rdf": "rdfxml", ".xml": "rdfxml", ".owl": "rdfxml"}


class WorkspaceError(ValueError):
    """Workspace initialization cannot be completed safely."""


def initialize_workspace(
    source: Path,
    workspace: Path,
    source_format: str | None,
    scope_prefixes: list[str],
    target_namespace_uri: str,
    target_label: str,
    target_label_lang: str,
) -> str:
    if not source.is_file():
        raise WorkspaceError(f"Source RDF file does not exist: {source}")
    if workspace.exists():
        raise WorkspaceError(f"Workspace already exists: {workspace}")
    format_name = _resolve_format(source, source_format)
    if not scope_prefixes:
        raise WorkspaceError("At least one --scope-uri-prefix is required")
    if not all(_is_uri(value) for value in scope_prefixes):
        raise WorkspaceError("Every --scope-uri-prefix must be an absolute URI")
    if not _is_uri(target_namespace_uri):
        raise WorkspaceError("--target-namespace-uri must be an absolute URI")
    if not target_label.strip():
        raise WorkspaceError("--target-label must not be empty")
    if not target_label_lang.strip():
        raise WorkspaceError("--target-label-lang must not be empty")

    workspace.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ontome-importer-init-", dir=workspace.parent))
    try:
        source_name = f"ontology{source.suffix.lower() or '.rdf'}"
        copied_source = staging / "source" / source_name
        copied_source.parent.mkdir()
        shutil.copyfile(source, copied_source)
        checksum = hashlib.sha256(copied_source.read_bytes()).hexdigest()
        load_inventory(copied_source, format_name)

        profiles = staging / "config" / "profiles"
        profiles.mkdir(parents=True)
        _write_template("templates/audit/capability-1.1.yaml", profiles / "capability-audit.yaml")
        _write_template("templates/generation/capability-1.0.yaml", profiles / "capability-generation.yaml")
        _write_template("templates/namespace-registry-1.1.yaml", profiles / "namespace-registry.yaml")
        (profiles / "mapping-audit.yaml").write_text(_audit_mapping(scope_prefixes), encoding="utf-8")
        (profiles / "mapping-generation.yaml").write_text(_generation_mapping(scope_prefixes), encoding="utf-8")
        config = staging / "config"
        (config / "audit.yaml").write_text(_audit_manifest(source_name, format_name, checksum, target_namespace_uri), encoding="utf-8")
        (config / "generation.yaml").write_text(_generation_manifest(source_name, format_name, checksum, target_namespace_uri, target_label, target_label_lang), encoding="utf-8")
        (staging / "build").mkdir()
        (staging / "README.md").write_text(_workspace_readme(source_name), encoding="utf-8")

        profiles_loaded = load_audit_profiles(config / "audit.yaml")
        verify_capability_xsd(profiles_loaded.capability)
        os.replace(staging, workspace)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return f"ontome-importer audit --manifest {workspace / 'config/audit.yaml'} --output-dir {workspace / 'build/audit'}"


def _resolve_format(source: Path, source_format: str | None) -> str:
    if source_format is not None:
        if source_format not in SUPPORTED_FORMATS:
            raise WorkspaceError(f"Unsupported RDF format: {source_format}")
        return source_format
    inferred = FORMAT_EXTENSIONS.get(source.suffix.lower())
    if inferred is None:
        raise WorkspaceError("Cannot infer RDF format; provide --format")
    return inferred


def _is_uri(value: str) -> bool:
    parsed = urlparse(value)
    return not any(character.isspace() for character in value) and bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))


def _write_template(template: str, destination: Path) -> None:
    destination.write_text(resources.files("ontome_importer").joinpath(template).read_text(encoding="utf-8"), encoding="utf-8")


def _audit_manifest(source_name: str, source_format: str, checksum: str, namespace_uri: str) -> str:
    return f'''# Created by ontome-importer init. Replace the target namespace before generation.
format_version: "1.1"
source:
  file: {_yaml_string(f'../source/{source_name}')}
  format: {source_format}
  sha256: {checksum}
target:
  namespace_uri: {_yaml_string(namespace_uri)}
profiles:
  capability: profiles/capability-audit.yaml
  namespace_registry: profiles/namespace-registry.yaml
  mapping: profiles/mapping-audit.yaml
strict: true
'''


def _generation_manifest(source_name: str, source_format: str, checksum: str, namespace_uri: str, target_label: str, target_label_lang: str) -> str:
    return f'''# Created by ontome-importer init.
format_version: "1.0"
source:
  file: {_yaml_string(f'../source/{source_name}')}
  format: {source_format}
  sha256: {checksum}
target:
  namespace_uri: {_yaml_string(namespace_uri)}
  labels:
    - lang: {_yaml_string(target_label_lang)}
      value: {_yaml_string(target_label)}
profiles:
  capability: profiles/capability-generation.yaml
  namespace_registry: profiles/namespace-registry.yaml
  mapping: profiles/mapping-generation.yaml
strict: true
'''


def _audit_mapping(scope_prefixes: list[str]) -> str:
    selectors = "".join(f"    - uri_prefix: {_yaml_string(prefix)}\n" for prefix in scope_prefixes)
    return f'''# No rules are created automatically. Use the audit report to make decisions.
format_version: "1.1"
scope:
  resource_selectors:
{selectors}rules: []
'''


def _generation_mapping(scope_prefixes: list[str]) -> str:
    selectors = "".join(f"    - uri_prefix: {_yaml_string(prefix)}\n" for prefix in scope_prefixes)
    return f'''# Generated by ontome-importer init and completed by review finalize.
format_version: "7.0"
scope:
  resource_selectors:
{selectors}external_references: []
external_reference_rules: []
editorial_exceptions: []
decisions: []
rules: []
'''


def _workspace_readme(source_name: str) -> str:
    return f'''# Espace de travail d'import

Votre source RDF copiée est `source/{source_name}`.

## Prochaine étape : audit

```bash
ontome-importer audit --manifest config/audit.yaml --output-dir build/audit
```

L'audit crée `build/audit/review-queue.json`. Le premier audit signale normalement des blocages : aucune décision de publication n'a encore été prise.

## Revue terminale

```bash
ontome-importer review start --manifest config/generation.yaml --session decisions/review.json
ontome-importer review resources --session decisions/review.json
ontome-importer review check --session decisions/review.json
ontome-importer review finalize --manifest config/generation.yaml --session decisions/review.json
```

Répétez `review resources` jusqu'à ce que toutes les décisions soient prises. Si une dépendance externe est détectée, la revue vous demande de confirmer sa version et télécharge son catalogue OntoME localement.

## Générer et valider

```bash
ontome-importer generate --manifest config/generation.yaml --output-dir build/import
ontome-importer validate --manifest config/generation.yaml --xml build/import/import.xml --trace build/import/generation-trace.json --audit build/import/generation-audit.json --output build/import/validation.json
```
'''


def _yaml_string(value: str) -> str:
    """JSON strings are valid YAML scalars and cannot alter its document structure."""
    return json.dumps(value, ensure_ascii=False)
