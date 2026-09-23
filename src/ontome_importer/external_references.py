"""Deterministic, profile-declared resolution of external RDF URI references."""

from __future__ import annotations

from dataclasses import dataclass
import re


class ExternalReferenceError(ValueError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class ExternalReferenceResolution:
    identifier: str
    reference_namespace: int
    origin: str
    rule_id: str | None = None


def validate_external_reference_configuration(mapping: dict[str, object], registry: dict[str, object]) -> None:
    namespaces = {item["ontome_namespace_id"]: item for item in registry["namespaces"]}
    references = mapping["external_references"]
    if len({item["uri"] for item in references}) != len(references):
        raise ExternalReferenceError("invalid_profile", "External reference URIs must be unique")
    rules = mapping["external_reference_rules"]
    if len({item["id"] for item in rules}) != len(rules):
        raise ExternalReferenceError("invalid_profile", "External reference rule identifiers must be unique")
    prefixes: set[str] = set()
    for item in [*references, *rules]:
        namespace = namespaces.get(item["reference_namespace"])
        if namespace is None:
            raise ExternalReferenceError("invalid_profile", "External reference namespace is absent from the namespace registry")
        if namespace["status"] == "forbidden":
            raise ExternalReferenceError("invalid_profile", "External reference namespace is forbidden")
        uri = item.get("uri", item.get("uri_prefix"))
        if not str(uri).startswith(str(namespace["uri"])):
            raise ExternalReferenceError("invalid_profile", "External reference URI does not belong to its namespace registry entry")
        if "identifier_extraction" not in item:
            continue
        if item["uri_prefix"] in prefixes:
            raise ExternalReferenceError("invalid_profile", "External reference rule URI prefixes must be unique")
        prefixes.add(item["uri_prefix"])
        extraction = item["identifier_extraction"]
        if extraction["source"] == "regex_capture":
            try:
                pattern = re.compile(extraction["pattern"])
            except re.error as error:
                raise ExternalReferenceError("invalid_profile", f"External reference pattern is invalid: {error}") from error
            if pattern.groups != 1:
                raise ExternalReferenceError("invalid_profile", "External reference regex_capture requires exactly one capture group")


def resolve_external_reference(uri: str, mapping: dict[str, object], registry: dict[str, object]) -> ExternalReferenceResolution:
    validate_external_reference_configuration(mapping, registry)
    exception = next((item for item in mapping["external_references"] if item["uri"] == uri), None)
    if exception is not None:
        return ExternalReferenceResolution(exception["identifier"], exception["reference_namespace"], "external_exception")
    rules = [item for item in mapping["external_reference_rules"] if uri.startswith(item["uri_prefix"])]
    if not rules:
        raise ExternalReferenceError("missing_profile_rule", "External reference has no matching exception or rule")
    rule = max(rules, key=lambda item: len(item["uri_prefix"]))
    extraction = rule["identifier_extraction"]
    if extraction["source"] == "uri_suffix":
        identifier = uri.removeprefix(rule["uri_prefix"])
    else:
        match = re.fullmatch(extraction["pattern"], uri)
        identifier = match.group(1) if match else ""
    if not identifier or any(character.isspace() for character in identifier):
        raise ExternalReferenceError("invalid_source_data", "External reference URI does not produce a valid identifier")
    return ExternalReferenceResolution(identifier, rule["reference_namespace"], "external_rule", rule["id"])
