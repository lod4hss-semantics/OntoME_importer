"""Capability and mapping audit for generic RDF construct occurrences."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from ontome_importer.constructs import ConstructOccurrence, RELATION_FIELDS, RDF, RDFS, OWL, SKOS, XSD, detect_constructs
from ontome_importer.external_references import ExternalReferenceError, resolve_external_reference
from ontome_importer.inventory import Inventory, RdfTerm


@dataclass(frozen=True)
class AuditReport:
    inventory: Inventory
    findings: tuple[dict[str, object], ...]
    observations: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        counts = Counter(finding["status"] for finding in self.findings)
        return {
            "format_version": "1.1",
            "inventory": {"file": self.inventory.source_file, "format": self.inventory.source_format, "sha256": self.inventory.source_sha256},
            "strict_ok": not any(finding["generation_impact"] == "blocks_generation" for finding in self.findings),
            "findings": list(self.findings),
            "observations": list(self.observations),
            "counts": dict(sorted(counts.items())),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def to_markdown(self) -> str:
        data = self.to_dict()
        lines = ["# RDF Audit", "", f"Strict result: {'pass' if data['strict_ok'] else 'blocked'}", f"Out-of-scope observations: {len(self.observations)}", "", "| Status | Count |", "| --- | ---: |"]
        lines.extend(f"| {status} | {count} |" for status, count in data["counts"].items())
        grouped = Counter((finding["status"], finding["category"], finding["construct"]) for finding in self.findings)
        lines.extend(["", "## Decision Summary", "", "Findings are grouped below. A group may be covered by one explicit mapping rule; it does not imply one rule per finding.", "", "| Status | Category | Construct | Count |", "| --- | --- | --- | ---: |"])
        lines.extend(f"| {status} | `{category}` | `{construct}` | {count} |" for (status, category, construct), count in sorted(grouped.items()))
        external = _external_reference_groups(self.inventory, self.findings)
        if external:
            lines.extend(["", "## External References", "", "These URI prefixes occur outside the import scope. The current mapping contract requires an exact external reference for each URI used.", "", "| URI prefix | Assertions |", "| --- | ---: |"])
            lines.extend(f"| `{prefix}` | {count} |" for prefix, count in external)
        lines.extend(["", "## Detailed Decisions", ""])
        for finding in self.findings:
            if finding["status"] != "mapped":
                lines.append(f"- `{finding['status']}` / `{finding['category']}` `{finding['construct']}` on `{finding['resource']['value']}`: {finding.get('decision_needed') or finding.get('reason') or 'decision required'}")
        return "\n".join(lines) + "\n"


def audit_inventory(
    inventory: Inventory,
    capability: dict[str, object],
    mapping: dict[str, object],
    namespace_registry: dict[str, object] | None = None,
) -> AuditReport:
    findings = []
    observations = []
    triples = {triple.id: triple for triple in inventory.triples}
    occurrences = list(detect_constructs(inventory))
    for triple in inventory.triples:
        if triple.object.kind != "uri" or _is_local(triple.object, inventory, mapping):
            continue
        if _is_standard(triple.object) and not _standard_reference_predicate(triple.predicate.value):
            continue
        status = _registered_namespace_status(triple.object.value, namespace_registry)
        if status == "forbidden":
            occurrences.append(ConstructOccurrence("forbidden_namespace", triple.subject, (triple.id,)))
            continue
        if not _configured_external_reference(triple.object.value, mapping, namespace_registry):
            occurrences.append(ConstructOccurrence("missing_external_reference", triple.subject, (triple.id,)))
        if status is None and not _is_standard(triple.object):
            occurrences.append(ConstructOccurrence("unknown_namespace", triple.subject, (triple.id,)))
    for occurrence in sorted(set(occurrences), key=lambda item: item.id):
        base = _base_record(occurrence, triples, inventory.source_file)
        effective_resource = occurrence.scope_resource or occurrence.resource
        if not _in_scope(effective_resource, inventory, mapping):
            observations.append(base)
            continue
        matching_rules = [rule for rule in mapping["rules"] if _matches(rule["selector"], effective_resource, inventory)]
        capability_result = capability["constructs"].get(occurrence.construct, capability["unknown_construct_policy"])
        if _editorial_exception_covers(occurrence, effective_resource, mapping):
            capability_result = "supported"
        if occurrence.construct == "unknown_predicate" and len(matching_rules) == 1 and _generation_mapping_covers(occurrence, matching_rules[0], triples):
            capability_result = "supported"
        finding = dict(base, capability=capability_result)
        if occurrence.construct == "forbidden_namespace":
            finding.update(status="blocked", category="forbidden_external_namespace", generation_impact="blocks_generation", decision_needed="Remove the reference to the forbidden namespace.")
        elif len(matching_rules) > 1:
            finding.update(status="invalid", category="invalid_profile", generation_impact="blocks_generation", decision_needed="Resolve ambiguous mapping rules.")
        elif matching_rules and matching_rules[0]["action"] == "exclude":
            finding.update(status="excluded", category="intentional_exclusion", generation_impact="excluded", mapping_rule=matching_rules[0]["id"], reason=matching_rules[0]["reason"])
        elif capability_result == "blocked":
            category = "missing_external_data" if occurrence.construct == "unknown_namespace" else "missing_profile_rule" if occurrence.construct == "missing_external_reference" else "unsupported_rdf_construct"
            finding.update(status="blocked", category=category, generation_impact="blocks_generation", mapping_rule=matching_rules[0]["id"] if matching_rules else None, decision_needed="Add a supported capability and mapping decision.")
        elif not matching_rules:
            finding.update(status="blocked", category="missing_profile_rule", generation_impact="blocks_generation", decision_needed="Add a mapping rule.")
        elif matching_rules[0]["action"] == "configure":
            finding.update(status="configured", category="configuration_required", generation_impact="blocks_generation", mapping_rule=matching_rules[0]["id"], decision_needed=matching_rules[0]["decision_needed"])
        else:
            if mapping.get("format_version") == "7.0" and (_generation_mapping_covers(occurrence, matching_rules[0], triples) or _editorial_exception_covers(occurrence, effective_resource, mapping)):
                finding.update(status="mapped", category="mechanical_transformation", generation_impact="included", mapping_rule=matching_rules[0]["id"])
            elif mapping.get("format_version") == "7.0":
                finding.update(
                    status="blocked",
                    category="missing_profile_rule",
                    generation_impact="blocks_generation",
                    mapping_rule=matching_rules[0]["id"],
                    decision_needed="Add an explicit generation mapping for this RDF assertion.",
                )
            else:
                finding.update(
                    status="configured",
                    category="configuration_required",
                    generation_impact="blocks_generation",
                    mapping_rule=matching_rules[0]["id"],
                    decision_needed="Validate a concrete XML representation in a generation mapping profile.",
                )
        if finding.get("mapping_rule") is None:
            finding.pop("mapping_rule", None)
        decision = _decision_for(finding, mapping)
        if decision is not None:
            finding["decision_id"] = decision["id"]
            finding["decision_status"] = decision["status"]
            if decision["status"] != "approved" and finding["generation_impact"] == "included":
                finding.update(status="configured", category="decision_approval_required", generation_impact="blocks_generation", decision_needed="Approve or remove the linked decision before generation.")
        findings.append(finding)
    return AuditReport(inventory, tuple(sorted(findings, key=lambda item: item["id"])), tuple(sorted(observations, key=lambda item: item["id"])))


def _in_scope(resource: RdfTerm, inventory: Inventory, mapping: dict[str, object]) -> bool:
    return any(_matches(selector, resource, inventory) for selector in mapping["scope"]["resource_selectors"])


def _matches(selector: dict[str, object], resource: RdfTerm, inventory: Inventory) -> bool:
    if "uri" in selector and (resource.kind != "uri" or resource.value != selector["uri"]):
        return False
    if "uri_prefix" in selector and (resource.kind != "uri" or not resource.value.startswith(str(selector["uri_prefix"]))):
        return False
    if "rdf_type" in selector:
        types = next((item.types for item in inventory.resources if item.id == resource), ())
        if not any(term.value == selector["rdf_type"] for term in types):
            return False
    return True


def _base_record(occurrence: ConstructOccurrence, triples: dict[str, object], source_file: str) -> dict[str, object]:
    example = "(missing assertion)"
    if occurrence.triple_ids:
        triple = triples[occurrence.triple_ids[0]]
        example = _serialize_triple(triple)
    record = {"id": occurrence.id, "construct": occurrence.construct, "resource": occurrence.resource.to_dict(), "triple_ids": list(occurrence.triple_ids), "example": example, "provenance": {"file": source_file}}
    if occurrence.scope_resource is not None:
        record["scope_resource"] = occurrence.scope_resource.to_dict()
    return record


def _is_local(resource: RdfTerm, inventory: Inventory, mapping: dict[str, object]) -> bool:
    return _in_scope(resource, inventory, mapping)


def _is_standard(resource: RdfTerm) -> bool:
    return resource.value.startswith((RDF, RDFS, OWL, SKOS, XSD))


def _configured_external_reference(uri: str, mapping: dict[str, object], registry: dict[str, object] | None) -> bool:
    if mapping.get("format_version") != "7.0" or registry is None:
        return False
    try:
        resolve_external_reference(uri, mapping, registry)
    except ExternalReferenceError:
        return False
    return True


def _standard_reference_predicate(predicate: str) -> bool:
    return predicate in {
        f"{RDFS}subClassOf", f"{RDFS}subPropertyOf", f"{RDFS}domain", f"{RDFS}range",
        f"{OWL}equivalentClass", f"{OWL}equivalentProperty", f"{OWL}inverseOf",
    }


def _generation_mapping_covers(
    occurrence: ConstructOccurrence, rule: dict[str, object], triples: dict[str, object]
) -> bool:
    """A resource rule is not enough: each supported assertion needs an XML mapping."""
    target = rule.get("target", {})
    construct = occurrence.construct
    if construct in {"rdfs_class", "owl_class"}:
        return target.get("entity_kind") == "class"
    if construct in {"rdf_property", "object_property", "datatype_property"}:
        kinds = {"rdf_property": "rdf", "object_property": "object", "datatype_property": "datatype"}
        return target.get("entity_kind") == "property" and target.get("property_kind") == kinds[construct]
    if not occurrence.triple_ids:
        return False
    predicate = triples[occurrence.triple_ids[0]].predicate.value
    if construct == "label":
        return predicate in target.get("label_predicates", [])
    if construct in {"comment", "scope_note", "example"}:
        return any(predicate in field.get("predicates", []) for field in target.get("text_fields", []))
    if construct == "unknown_predicate":
        identifier = target.get("identifier_in_namespace", {})
        return (identifier.get("source") == "literal_predicate" and predicate == identifier.get("predicate")) or any(predicate in field.get("predicates", []) for field in target.get("text_fields", []))
    if construct in {"subclass_of", "subproperty_of", "equivalent_class", "equivalent_property", "inverse_of", "disjointness"}:
        return any(predicate == relation.get("predicate") and RELATION_FIELDS.get(predicate) == relation.get("field") for relation in target.get("relations", []))
    if construct == "named_domain":
        return predicate == target.get("domain_range", {}).get("domain_predicate")
    if construct == "named_range":
        return predicate == target.get("domain_range", {}).get("range_predicate")
    return False


def _editorial_exception_covers(occurrence: ConstructOccurrence, resource: RdfTerm, mapping: dict[str, object]) -> bool:
    field = {"missing_domain": "hasDomain", "missing_range": "hasRange"}.get(occurrence.construct)
    return bool(field and any(item["resource_uri"] == resource.value and item["field"] == field and item["status"] == "approved" for item in mapping.get("editorial_exceptions", [])))


def _decision_for(finding: dict[str, object], mapping: dict[str, object]) -> dict[str, object] | None:
    resource = finding["resource"]
    assert isinstance(resource, dict)
    matches = [
        item for item in mapping.get("decisions", [])
        if item["resource_uri"] == resource["value"] and item["construct"] == finding["construct"]
        and ("mapping_rule" not in item or item["mapping_rule"] == finding.get("mapping_rule"))
    ]
    return matches[0] if len(matches) == 1 else None


def _registered_namespace_status(uri: str, namespace_registry: dict[str, object] | None) -> str | None:
    if not namespace_registry:
        return None
    matches = [
        item for item in namespace_registry["namespaces"]
        if uri.startswith(str(item["uri"]))
    ]
    if not matches:
        return None
    return str(max(matches, key=lambda item: len(str(item["uri"])))["status"])


def _serialize_triple(triple: object) -> str:
    subject = getattr(triple, "subject")
    predicate = getattr(triple, "predicate")
    object_ = getattr(triple, "object")
    return f"{_serialize_term(subject)} {_serialize_term(predicate)} {_serialize_term(object_)} ."


def _serialize_term(term: RdfTerm) -> str:
    if term.kind == "uri":
        return f"<{term.value}>"
    if term.kind == "blank_node":
        return f"_:{term.value}"
    escaped = json.dumps(term.value, ensure_ascii=False)
    if term.language:
        return f"{escaped}@{term.language}"
    if term.datatype:
        return f"{escaped}^^<{term.datatype}>"
    return escaped


def _external_reference_groups(inventory: Inventory, findings: tuple[dict[str, object], ...]) -> list[tuple[str, int]]:
    finding_ids = {triple_id for finding in findings for triple_id in finding["triple_ids"] if finding["construct"] in {"unknown_namespace", "forbidden_namespace", "missing_external_reference"}}
    counts: Counter[str] = Counter()
    for triple in inventory.triples:
        if triple.id not in finding_ids or triple.object.kind != "uri":
            continue
        prefix = triple.object.value.rsplit("#", 1)[0] + "#" if "#" in triple.object.value else triple.object.value.rsplit("/", 1)[0] + "/"
        counts[prefix] += 1
    return sorted(counts.items())
