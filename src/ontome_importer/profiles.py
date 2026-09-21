"""Loading and validation of versioned audit profiles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ontome_importer.constructs import RELATION_FIELDS, SEMANTIC_CONSTRUCTS
from ontome_importer.package_resources import package_resource_path


class ProfileError(ValueError):
    """A manifest or profile is invalid."""


@dataclass(frozen=True)
class AuditProfiles:
    manifest: dict[str, object]
    capability: dict[str, object]
    namespace_registry: dict[str, object]
    mapping: dict[str, object]


@dataclass(frozen=True)
class GenerationProfiles:
    manifest: dict[str, object]
    capability: dict[str, object]
    namespace_registry: dict[str, object]
    mapping: dict[str, object]


def load_audit_profiles(manifest_path: str | Path) -> AuditProfiles:
    manifest_file = Path(manifest_path)
    manifest = _load_and_validate(manifest_file, "schemas/config/import-manifest-1.1.schema.json")
    base = manifest_file.parent
    profiles = manifest["profiles"]
    assert isinstance(profiles, dict)
    capability = _load_and_validate(base / str(profiles["capability"]), "schemas/config/capability-profile-1.1.schema.json")
    _validate_capability_constructs(capability)
    registry = _load_and_validate(base / str(profiles["namespace_registry"]), "schemas/config/namespace-registry.schema.json")
    mapping = _load_and_validate(base / str(profiles["mapping"]), "schemas/config/mapping-profile-1.1.schema.json")
    rule_ids = [rule["id"] for rule in mapping["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise ProfileError("Mapping rule identifiers must be unique")
    return AuditProfiles(manifest, capability, registry, mapping)


def load_generation_profiles(manifest_path: str | Path) -> GenerationProfiles:
    """Load the existing complete manifest/capability contracts with mapping 2.0."""
    manifest_file = Path(manifest_path)
    manifest = _load_and_validate(manifest_file, "schemas/config/import-manifest.schema.json")
    base = manifest_file.parent
    profiles = manifest["profiles"]
    assert isinstance(profiles, dict)
    capability = _load_and_validate(base / str(profiles["capability"]), "schemas/config/capability-profile.schema.json")
    _validate_capability_constructs(capability)
    registry = _load_and_validate(base / str(profiles["namespace_registry"]), "schemas/config/namespace-registry.schema.json")
    mapping = _load_and_validate(base / str(profiles["mapping"]), "schemas/config/mapping-profile-2.0.schema.json")
    rule_ids = [rule["id"] for rule in mapping["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise ProfileError("Mapping rule identifiers must be unique")
    references = mapping["external_references"]
    uris = [reference["uri"] for reference in references]
    if len(uris) != len(set(uris)):
        raise ProfileError("External reference URIs must be unique")
    namespace_ids = [item["ontome_namespace_id"] for item in registry["namespaces"]]
    if len(namespace_ids) != len(set(namespace_ids)):
        raise ProfileError("OntoME namespace identifiers must be unique")
    namespaces = {item["ontome_namespace_id"]: item for item in registry["namespaces"]}
    for reference in references:
        namespace = namespaces.get(reference["reference_namespace"])
        if namespace is None:
            raise ProfileError("External reference namespace is absent from the namespace registry")
        if namespace["status"] == "forbidden":
            raise ProfileError("External reference namespace is forbidden")
        if not str(reference["uri"]).startswith(str(namespace["uri"])):
            raise ProfileError("External reference URI does not belong to its namespace registry entry")
    validate_generation_mapping(mapping, capability)
    return GenerationProfiles(manifest, capability, registry, mapping)


def verify_source_checksum(manifest: dict[str, object], source_path: Path) -> None:
    source = manifest["source"]
    assert isinstance(source, dict)
    expected = source.get("sha256")
    if expected is not None:
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if expected != actual:
            raise ProfileError("Source SHA-256 does not match the import manifest")


def verify_capability_xsd(capability: dict[str, object]) -> Path:
    """Verify the versioned XSD selected by the capability profile."""
    xsd = capability["xsd"]
    assert isinstance(xsd, dict)
    path = package_resource_path(str(xsd["path"]))
    if not path.is_file():
        raise ProfileError(f"Capability XSD does not exist: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != xsd["sha256"]:
        raise ProfileError("Capability XSD SHA-256 does not match the capability profile")
    return path


def _load_and_validate(path: Path, schema_relative_path: str) -> dict[str, object]:
    if not path.is_file():
        raise ProfileError(f"Configuration file does not exist: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ProfileError(f"Cannot parse YAML {path}: {error}") from error
    schema_path = package_resource_path(schema_relative_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document), key=str)
    if errors:
        raise ProfileError(f"{path}: {errors[0].message}")
    assert isinstance(document, dict)
    return document


def _validate_capability_constructs(capability: dict[str, object]) -> None:
    unknown = sorted(set(capability["constructs"]) - SEMANTIC_CONSTRUCTS)
    if unknown:
        raise ProfileError(f"Capability profile declares an unknown semantic construct: {unknown[0]}")


def validate_generation_mapping(mapping: dict[str, object], capability: dict[str, object]) -> None:
    xml = capability["xml"]
    assert isinstance(xml, dict)
    for rule in mapping["rules"]:
        if rule["action"] != "map":
            continue
        target = rule["target"]
        entity_kind = target["entity_kind"]
        fields = set(xml["class_fields"] if entity_kind == "class" else xml["property_fields"])
        mandatory = {"identifierInNamespace", "standardLabel" if entity_kind == "class" else "label"}
        if entity_kind == "property":
            mandatory.update(("hasDomain", "hasRange"))
        if not mandatory <= fields:
            raise ProfileError(f"Capability profile does not permit required {entity_kind} XML fields")
        for relation in target.get("relations", []):
            if relation["field"] not in fields:
                raise ProfileError(f"Mapping rule {rule['id']} targets a field not allowed by the capability profile")
            expected = RELATION_FIELDS.get(relation["predicate"])
            if expected != relation["field"]:
                raise ProfileError(f"Mapping rule {rule['id']} uses an unsupported RDF predicate-to-XML relation mapping")
        if target.get("text_fields") and "textProperties" not in fields:
            raise ProfileError(f"Mapping rule {rule['id']} targets textProperties not allowed by the capability profile")
