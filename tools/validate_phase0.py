"""Validate versioned Phase 0 contracts and fixtures without application code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate(schema_path: Path, document_path: Path) -> None:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(load_yaml(document_path)), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"{document_path}: {errors[0].message}")


def main() -> None:
    xsd_path = ROOT / "resources/xsd/ontome-import-2026-09-15.xsd"
    metadata = load_json(ROOT / "resources/xsd/ontome-import-2026-09-15.metadata.json")
    actual_digest = hashlib.sha256(xsd_path.read_bytes()).hexdigest()
    if metadata["sha256"] != actual_digest:
        raise ValueError("XSD checksum does not match its metadata")
    etree.XMLSchema(etree.parse(str(xsd_path)))

    config = ROOT / "fixtures/phase0/config"
    schemas = ROOT / "schemas/config"
    validate(schemas / "import-manifest.schema.json", config / "import-manifest.yaml")
    validate(schemas / "namespace-registry.schema.json", config / "namespace-registry.yaml")
    validate(schemas / "mapping-profile.schema.json", config / "mapping-profile.yaml")
    validate(schemas / "capability-profile.schema.json", ROOT / "profiles/capabilities/ontome-import-2026-09-15.yaml")

    invalid_schema = load_json(schemas / "mapping-profile.schema.json")
    invalid = Draft202012Validator(invalid_schema, format_checker=FormatChecker())
    if not list(invalid.iter_errors(load_yaml(config / "invalid-exclusion.yaml"))):
        raise ValueError("Invalid exclusion fixture was accepted")

    for name in ("inventory", "coverage", "generation-trace", "validation"):
        schema = load_json(ROOT / "schemas/reports" / f"{name}.schema.json")
        document = load_json(ROOT / "fixtures/phase0/expected" / f"{name}.json")
        errors = list(Draft202012Validator(schema).iter_errors(document))
        if errors:
            raise ValueError(f"{name} fixture: {errors[0].message}")

    print("Phase 0 contracts are valid.")


if __name__ == "__main__":
    main()
