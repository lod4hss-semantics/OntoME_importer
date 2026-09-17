"""Validate all versioned schemas, XSD assets, and shipped fixture profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _validate(schema: Path, document: Path) -> None:
    errors = list(Draft202012Validator(_json(schema), format_checker=FormatChecker()).iter_errors(_yaml(document)))
    if errors:
        raise ValueError(f"{document}: {errors[0].message}")


def main() -> None:
    for schema in sorted((ROOT / "schemas").rglob("*.json")):
        Draft202012Validator.check_schema(_json(schema))
    xsd = ROOT / "resources/xsd/ontome-import-2026-09-15.xsd"
    metadata = _json(ROOT / "resources/xsd/ontome-import-2026-09-15.metadata.json")
    if hashlib.sha256(xsd.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("XSD checksum does not match its metadata")
    etree.XMLSchema(etree.parse(str(xsd)))

    phase3 = ROOT / "fixtures/phase3"
    _validate(ROOT / "schemas/config/import-manifest-1.1.schema.json", phase3 / "import-manifest.yaml")
    _validate(ROOT / "schemas/config/capability-profile-1.1.schema.json", phase3 / "profiles/capability.yaml")
    _validate(ROOT / "schemas/config/mapping-profile-1.1.schema.json", phase3 / "profiles/mapping.yaml")
    _validate(ROOT / "schemas/config/namespace-registry.schema.json", phase3 / "profiles/namespace-registry.yaml")

    phase4 = ROOT / "fixtures/phase4"
    _validate(ROOT / "schemas/config/import-manifest.schema.json", phase4 / "import-manifest.yaml")
    _validate(ROOT / "schemas/config/capability-profile.schema.json", phase4 / "profiles/capability.yaml")
    _validate(ROOT / "schemas/config/mapping-profile-2.0.schema.json", phase4 / "profiles/mapping.yaml")
    _validate(ROOT / "schemas/config/namespace-registry.schema.json", phase4 / "profiles/namespace-registry.yaml")

    templates = ROOT / "src/ontome_importer/templates"
    _validate(ROOT / "schemas/config/capability-profile-1.1.schema.json", templates / "audit/capability-1.1.yaml")
    _validate(ROOT / "schemas/config/capability-profile.schema.json", templates / "generation/capability-1.0.yaml")
    _validate(ROOT / "schemas/config/namespace-registry.schema.json", templates / "namespace-registry-1.0.yaml")
    print("All versioned contracts are valid.")


if __name__ == "__main__":
    main()
