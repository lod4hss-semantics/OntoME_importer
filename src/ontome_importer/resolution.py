"""Resolve typed generation mappings into an XML-ready OntoME model."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

from ontome_importer.audit import AuditReport, audit_inventory
from ontome_importer.constructs import OWL, RDF, RDFS, SKOS
from ontome_importer.external_references import ExternalReferenceError, resolve_external_reference
from ontome_importer.inventory import Inventory, InventoryTriple, RdfTerm


@dataclass(frozen=True)
class ResolvedText:
    value: str
    language: str
    resource: RdfTerm
    triple_ids: tuple[str, ...]
    mapping_rule: str
    origin: str = "rdf"


@dataclass(frozen=True)
class ResolvedReference:
    value: str
    reference_namespace: int | None
    resource: RdfTerm
    triple_ids: tuple[str, ...]
    mapping_rule: str
    origin: str
    reference_rule: str | None = None
    exception_id: str | None = None


@dataclass(frozen=True)
class ResolvedIdentifier:
    value: str
    triple_ids: tuple[str, ...]
    origin: str


@dataclass(frozen=True)
class ResolvedClass:
    resource: RdfTerm
    source_triple_ids: tuple[str, ...]
    mapping_rule: str
    identifier: str
    identifier_triple_ids: tuple[str, ...]
    identifier_origin: str
    identifier_uri: str | None
    labels: tuple[ResolvedText, ...]
    relations: tuple[tuple[str, ResolvedReference], ...]
    texts: tuple[tuple[str, ResolvedText], ...]


@dataclass(frozen=True)
class ResolvedProperty:
    resource: RdfTerm
    source_triple_ids: tuple[str, ...]
    mapping_rule: str
    kind: str
    identifier: str
    identifier_triple_ids: tuple[str, ...]
    identifier_origin: str
    identifier_uri: str | None
    labels: tuple[ResolvedText, ...]
    relations: tuple[tuple[str, ResolvedReference], ...]
    domain: ResolvedReference | None
    range: ResolvedReference | None
    texts: tuple[tuple[str, ResolvedText], ...]


@dataclass(frozen=True)
class ResolvedNamespace:
    labels: tuple[ResolvedText, ...]
    namespace_uri: str
    version: str | None
    published_at: str | None
    contributors: str | None
    descriptions: tuple[ResolvedText, ...]
    reference_namespaces: tuple[int, ...]


@dataclass(frozen=True)
class ResolvedGeneration:
    namespace: ResolvedNamespace
    classes: tuple[ResolvedClass, ...]
    properties: tuple[ResolvedProperty, ...]


@dataclass(frozen=True)
class ResolutionResult:
    generation: ResolvedGeneration | None
    audit: dict[str, object]


def resolve_generation(
    inventory: Inventory,
    manifest: dict[str, object],
    capability: dict[str, object],
    mapping: dict[str, object],
    registry: dict[str, object],
) -> ResolutionResult:
    rdf_audit = audit_inventory(inventory, capability, mapping, registry)
    findings = [dict(item, phase="rdf_audit") for item in rdf_audit.findings]
    if not rdf_audit.to_dict()["strict_ok"]:
        return ResolutionResult(None, _audit_document(inventory, capability, findings))

    triples_by_subject: dict[RdfTerm, list[InventoryTriple]] = {}
    for triple in inventory.triples:
        triples_by_subject.setdefault(triple.subject, []).append(triple)
    bases: list[tuple[RdfTerm, dict[str, object], dict[str, object]]] = []
    for resource in sorted((item.id for item in inventory.resources if item.id.kind == "uri"), key=lambda term: term.value):
        rules = [rule for rule in mapping["rules"] if rule["action"] == "map" and _matches(rule["selector"], resource, inventory)]
        if not rules:
            continue
        if len(rules) != 1:
            findings.append(_issue("invalid", resource, (), None, "More than one generation mapping rule applies.", "invalid_profile"))
            continue
        target = rules[0]["target"]
        bases.append((resource, rules[0], target))

    identifiers: dict[RdfTerm, ResolvedIdentifier] = {}
    for resource, rule, target in bases:
        identifier = _local_identifier(resource, target, triples_by_subject.get(resource, []), rule["id"], findings)
        if identifier is not None:
            identifiers[resource] = identifier
    collisions = Counter(item.value for item in identifiers.values())
    for resource, identifier in identifiers.items():
        if collisions[identifier.value] > 1:
            findings.append(_issue("invalid", resource, (), None, f"Local identifier collision: {identifier.value}", "ambiguous_source_data"))

    resolved_classes: list[ResolvedClass] = []
    resolved_properties: list[ResolvedProperty] = []
    used_namespaces: set[int] = set()
    for resource, rule, target in bases:
        if resource not in identifiers or collisions[identifiers[resource].value] > 1:
            continue
        source_triples = triples_by_subject.get(resource, [])
        _check_entity_type(resource, target, source_triples, rule["id"], findings)
        labels = _texts(source_triples, target["label_predicates"], resource, rule["id"], findings, "label")
        if not labels:
            findings.append(_issue("blocked", resource, (), rule["id"], "At least one localized label is required.", "incomplete_source_data"))
        texts, configured_predicates = _configured_texts(source_triples, target, resource, rule["id"], findings)
        relations, relation_predicates = _relations(
            source_triples, target, resource, rule["id"], identifiers, mapping, registry, findings, used_namespaces
        )
        handled = {f"{RDF}type", *target["label_predicates"], *configured_predicates, *relation_predicates}
        if target["identifier_in_namespace"]["source"] == "literal_predicate":
            handled.add(target["identifier_in_namespace"]["predicate"])
        domain = range_ = None
        if target["entity_kind"] == "property":
            domain_predicate = target["domain_range"]["domain_predicate"]
            range_predicate = target["domain_range"]["range_predicate"]
            handled.update((domain_predicate, range_predicate))
            domain = _single_reference(source_triples, domain_predicate, resource, rule["id"], identifiers, mapping, registry, findings, used_namespaces, "domain", "hasDomain")
            range_ = _single_reference(source_triples, range_predicate, resource, rule["id"], identifiers, mapping, registry, findings, used_namespaces, "range", "hasRange")
        _check_unhandled(source_triples, handled, resource, rule["id"], findings)
        if target["entity_kind"] == "class":
            resolved_classes.append(ResolvedClass(resource, _type_triple_ids(source_triples), rule["id"], identifiers[resource].value, identifiers[resource].triple_ids, identifiers[resource].origin, _identifier_uri(target, resource), labels, relations, texts))
        else:
            resolved_properties.append(ResolvedProperty(resource, _type_triple_ids(source_triples), rule["id"], target["property_kind"], identifiers[resource].value, identifiers[resource].triple_ids, identifiers[resource].origin, _identifier_uri(target, resource), labels, relations, domain, range_, texts))

    if any(finding["status"] in {"blocked", "invalid"} for finding in findings):
        return ResolutionResult(None, _audit_document(inventory, capability, findings))
    target = manifest["target"]
    namespace = ResolvedNamespace(
        tuple(ResolvedText(item["value"], item["lang"], RdfTerm("uri", str(target["namespace_uri"])), (), "manifest", "configuration") for item in target["labels"]),
        str(target["namespace_uri"]), target.get("version"), target.get("published_at"), target.get("contributors"),
        tuple(ResolvedText(item["value"], item["lang"], RdfTerm("uri", str(target["namespace_uri"])), (), "manifest", "configuration") for item in target.get("descriptions", [])),
        tuple(sorted(used_namespaces)),
    )
    generation = ResolvedGeneration(namespace, tuple(sorted(resolved_classes, key=lambda item: item.identifier)), tuple(sorted(resolved_properties, key=lambda item: item.identifier)))
    return ResolutionResult(generation, _audit_document(inventory, capability, findings))


def _local_identifier(resource: RdfTerm, target: dict[str, object], triples: list[InventoryTriple], rule: str, findings: list[dict[str, object]]) -> ResolvedIdentifier | None:
    strategy = target["identifier_in_namespace"]
    source = strategy["source"]
    triple_ids: tuple[str, ...] = ()
    if source == "uri_suffix":
        prefix = strategy["strip_prefix"]
        if not resource.value.startswith(prefix):
            findings.append(_issue("blocked", resource, (), rule, "Identifier URI does not start with the configured strip_prefix.", "missing_profile_rule"))
            return None
        value = resource.value.removeprefix(prefix)
        origin = "identifier_uri_suffix"
    elif source == "regex_capture":
        match = re.fullmatch(strategy["pattern"], resource.value)
        value = match.group(1) if match else ""
        origin = "identifier_regex_capture"
    else:
        matches = [triple for triple in triples if triple.predicate.value == strategy["predicate"]]
        if len(matches) != 1:
            category = "incomplete_source_data" if not matches else "ambiguous_source_data"
            findings.append(_issue("blocked", resource, tuple(item.id for item in matches), rule, "Identifier predicate requires exactly one literal value.", category))
            return None
        match = matches[0]
        if match.object.kind != "literal":
            findings.append(_issue("blocked", resource, (match.id,), rule, "Identifier predicate value must be a literal.", "invalid_source_data"))
            return None
        value = match.object.value
        triple_ids = (match.id,)
        origin = "identifier_literal_predicate"
    if not value or any(character.isspace() for character in value) or "{" in value or "}" in value:
        findings.append(_issue("blocked", resource, triple_ids, rule, "Local identifier is empty or invalid.", "invalid_source_data"))
        return None
    return ResolvedIdentifier(value, triple_ids, origin)


def _matches(selector: dict[str, object], resource: RdfTerm, inventory: Inventory) -> bool:
    if "uri" in selector and resource.value != selector["uri"]:
        return False
    if "uri_prefix" in selector and not resource.value.startswith(str(selector["uri_prefix"])):
        return False
    if "rdf_type" in selector:
        types = next((item.types for item in inventory.resources if item.id == resource), ())
        return any(term.value == selector["rdf_type"] for term in types)
    return True


def _texts(triples: list[InventoryTriple], predicates: list[str], resource: RdfTerm, rule: str, findings: list[dict[str, object]], name: str) -> tuple[ResolvedText, ...]:
    values = []
    for triple in triples:
        if triple.predicate.value not in predicates:
            continue
        if triple.object.kind != "literal" or not triple.object.language:
            findings.append(_issue("blocked", resource, (triple.id,), rule, f"{name} must be a literal with a language.", "invalid_source_data"))
            continue
        values.append(ResolvedText(triple.object.value, triple.object.language, resource, (triple.id,), rule))
    return tuple(sorted(values, key=lambda item: (item.language, item.value, item.triple_ids)))


def _configured_texts(triples: list[InventoryTriple], target: dict[str, object], resource: RdfTerm, rule: str, findings: list[dict[str, object]]) -> tuple[tuple[tuple[str, ResolvedText], ...], set[str]]:
    values: list[tuple[str, ResolvedText]] = []
    predicates: set[str] = set()
    for field in target.get("text_fields", []):
        predicates.update(field["predicates"])
        for text in _texts(triples, field["predicates"], resource, rule, findings, field["field"]):
            values.append((field["field"], text))
    order = {"scopeNote": 0, "example": 1, "contextNote": 2, "bibliographicalNote": 3}
    return tuple(sorted(values, key=lambda item: (order[item[0]], item[1].language, item[1].value, item[1].triple_ids))), predicates


def _relations(triples: list[InventoryTriple], target: dict[str, object], resource: RdfTerm, rule: str, identifiers: dict[RdfTerm, str], mapping: dict[str, object], registry: dict[str, object], findings: list[dict[str, object]], used_namespaces: set[int]) -> tuple[tuple[tuple[str, ResolvedReference], ...], set[str]]:
    values: list[tuple[str, ResolvedReference]] = []
    predicates: set[str] = set()
    for relation in target.get("relations", []):
        predicates.add(relation["predicate"])
        for triple in triples:
            if triple.predicate.value == relation["predicate"]:
                reference = _reference(triple, resource, rule, identifiers, mapping, registry, findings, used_namespaces)
                if reference:
                    values.append((relation["field"], reference))
    return tuple(sorted(values, key=lambda item: (item[0], item[1].reference_namespace or 0, item[1].value))), predicates


def _single_reference(triples: list[InventoryTriple], predicate: str, resource: RdfTerm, rule: str, identifiers: dict[RdfTerm, str], mapping: dict[str, object], registry: dict[str, object], findings: list[dict[str, object]], used_namespaces: set[int], label: str, field: str) -> ResolvedReference | None:
    matches = [triple for triple in triples if triple.predicate.value == predicate]
    if len(matches) != 1:
        if not matches:
            exception = next((item for item in mapping.get("editorial_exceptions", []) if item["resource_uri"] == resource.value and item["field"] == field), None)
            if exception and exception["status"] == "approved":
                target = RdfTerm("uri", exception["reference_uri"])
                if target in identifiers:
                    return ResolvedReference(identifiers[target].value, None, resource, (), rule, "editorial_exception", None, exception["id"])
                try:
                    external = resolve_external_reference(target.value, mapping, registry)
                except ExternalReferenceError as error:
                    findings.append(_issue("blocked", resource, (), rule, str(error), error.category))
                    return None
                used_namespaces.add(external.reference_namespace)
                return ResolvedReference(external.identifier, external.reference_namespace, resource, (), rule, "editorial_exception", external.rule_id, exception["id"])
        findings.append(_issue("blocked", resource, tuple(item.id for item in matches), rule, f"Property requires exactly one named {label}.", "incomplete_source_data" if not matches else "ambiguous_source_data"))
        return None
    return _reference(matches[0], resource, rule, identifiers, mapping, registry, findings, used_namespaces)


def _reference(triple: InventoryTriple, resource: RdfTerm, rule: str, identifiers: dict[RdfTerm, str], mapping: dict[str, object], registry: dict[str, object], findings: list[dict[str, object]], used_namespaces: set[int]) -> ResolvedReference | None:
    if triple.object.kind != "uri":
        findings.append(_issue("blocked", resource, (triple.id,), rule, "Reference target must be a named URI.", "invalid_source_data"))
        return None
    if triple.object in identifiers:
        return ResolvedReference(identifiers[triple.object].value, None, triple.object, (triple.id,), rule, "rdf")
    try:
        external = resolve_external_reference(triple.object.value, mapping, registry)
    except ExternalReferenceError as error:
        findings.append(_issue("blocked", resource, (triple.id,), rule, str(error), error.category))
        return None
    namespace = next(item for item in registry["namespaces"] if item["ontome_namespace_id"] == external.reference_namespace)
    used_namespaces.add(external.reference_namespace)
    if namespace["status"] == "deprecated":
        findings.append(_issue("resolved", resource, (triple.id,), rule, "Deprecated external namespace used.", "mechanical_transformation"))
    return ResolvedReference(external.identifier, external.reference_namespace, triple.object, (triple.id,), rule, external.origin, external.rule_id)


def _check_entity_type(resource: RdfTerm, target: dict[str, object], triples: list[InventoryTriple], rule: str, findings: list[dict[str, object]]) -> None:
    types = {triple.object.value for triple in triples if triple.predicate.value == f"{RDF}type"}
    expected = {"class": {f"{OWL}Class", f"{RDFS}Class"}, "object": {f"{OWL}ObjectProperty"}, "datatype": {f"{OWL}DatatypeProperty"}, "rdf": {f"{RDF}Property"}}
    kind = target.get("property_kind", target["entity_kind"])
    if not types & expected[kind]:
        findings.append(_issue("blocked", resource, (), rule, f"Resource does not have the required {kind} RDF type.", "invalid_source_data"))


def _check_unhandled(triples: list[InventoryTriple], handled: set[str], resource: RdfTerm, rule: str, findings: list[dict[str, object]]) -> None:
    relevant = {f"{RDFS}label", f"{SKOS}prefLabel", f"{RDFS}comment", f"{SKOS}scopeNote", f"{SKOS}example", f"{RDFS}isDefinedBy", f"{RDFS}subClassOf", f"{RDFS}subPropertyOf", f"{OWL}equivalentClass", f"{OWL}equivalentProperty", f"{OWL}inverseOf"}
    for triple in triples:
        if triple.predicate.value in relevant and triple.predicate.value not in handled:
            findings.append(_issue("blocked", resource, (triple.id,), rule, "Supported RDF assertion has no explicit generation mapping.", "missing_profile_rule"))


def _identifier_uri(target: dict[str, object], resource: RdfTerm) -> str | None:
    return resource.value if target.get("identifier_in_uri") == "source_uri" else None


def _type_triple_ids(triples: list[InventoryTriple]) -> tuple[str, ...]:
    return tuple(sorted(triple.id for triple in triples if triple.predicate.value == f"{RDF}type"))


def _issue(status: str, resource: RdfTerm, triple_ids: tuple[str, ...], rule: str | None, reason: str, category: str) -> dict[str, object]:
    result: dict[str, object] = {"status": status, "category": category, "resource": resource.to_dict(), "triple_ids": list(sorted(triple_ids)), "reason": reason}
    if rule:
        result["mapping_rule"] = rule
    return result


def _audit_document(inventory: Inventory, capability: dict[str, object], findings: list[dict[str, object]]) -> dict[str, object]:
    counts = Counter(item["status"] for item in findings)
    xsd = capability["xsd"]
    return {"format_version": "1.1", "source": {"file": inventory.source_file, "sha256": inventory.source_sha256}, "xsd": {"version": xsd["version"], "sha256": xsd["sha256"]}, "strict_ok": not any(item["status"] in {"blocked", "invalid", "configured"} for item in findings), "findings": findings, "counts": dict(sorted(counts.items()))}
