"""Capability and mapping audit for generic RDF construct occurrences."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from ontome_importer.constructs import ConstructOccurrence, RDF, RDFS, OWL, SKOS, XSD, detect_constructs
from ontome_importer.inventory import Inventory, RdfTerm


@dataclass(frozen=True)
class AuditReport:
    inventory: Inventory
    findings: tuple[dict[str, object], ...]
    observations: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        counts = Counter(finding["status"] for finding in self.findings)
        return {
            "format_version": "1.0",
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
        lines = ["# RDF Audit", "", f"Strict result: {'pass' if data['strict_ok'] else 'blocked'}", "", "| Status | Count |", "| --- | ---: |"]
        lines.extend(f"| {status} | {count} |" for status, count in data["counts"].items())
        grouped = Counter((finding["status"], finding["construct"]) for finding in self.findings)
        lines.extend(["", "## Decision Summary", "", "Findings are grouped below. A group may be covered by one explicit mapping rule; it does not imply one rule per finding.", "", "| Status | Construct | Count |", "| --- | --- | ---: |"])
        lines.extend(f"| {status} | `{construct}` | {count} |" for (status, construct), count in sorted(grouped.items()))
        external = _external_reference_groups(self.inventory, self.findings)
        if external:
            lines.extend(["", "## External References", "", "These URI prefixes occur outside the import scope. Registering a namespace classifies references; generation still requires an exact external reference for each URI used.", "", "| URI prefix | Assertions |", "| --- | ---: |"])
            lines.extend(f"| `{prefix}` | {count} |" for prefix, count in external)
        lines.extend(["", "## Detailed Decisions", ""])
        for finding in self.findings:
            if finding["status"] != "mapped":
                lines.append(f"- `{finding['status']}` `{finding['construct']}` on `{finding['resource']['value']}`: {finding.get('decision_needed') or finding.get('reason') or 'decision required'}")
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
        if triple.object.kind != "uri" or _is_local_or_standard(triple.object, inventory, mapping):
            continue
        status = _registered_namespace_status(triple.object.value, namespace_registry)
        if status == "forbidden":
            occurrences.append(ConstructOccurrence("forbidden_namespace", triple.subject, (triple.id,)))
        elif status is None:
            occurrences.append(ConstructOccurrence("unknown_namespace", triple.subject, (triple.id,)))
    for occurrence in sorted(set(occurrences), key=lambda item: item.id):
        base = _base_record(occurrence, triples, inventory.source_file)
        effective_resource = occurrence.scope_resource or occurrence.resource
        if not _in_scope(effective_resource, inventory, mapping):
            observations.append(base)
            continue
        matching_rules = [rule for rule in mapping["rules"] if _matches(rule["selector"], effective_resource, inventory)]
        capability_result = capability["constructs"].get(occurrence.construct, capability["unknown_construct_policy"])
        finding = dict(base, capability=capability_result)
        if occurrence.construct == "forbidden_namespace":
            finding.update(status="blocked", generation_impact="blocks_generation", decision_needed="Remove the reference to the forbidden namespace.")
        elif len(matching_rules) > 1:
            finding.update(status="invalid", generation_impact="blocks_generation", decision_needed="Resolve ambiguous mapping rules.")
        elif matching_rules and matching_rules[0]["action"] == "exclude":
            finding.update(status="excluded", generation_impact="excluded", mapping_rule=matching_rules[0]["id"], reason=matching_rules[0]["reason"])
        elif capability_result == "blocked":
            finding.update(status="blocked", generation_impact="blocks_generation", mapping_rule=matching_rules[0]["id"] if matching_rules else None, decision_needed="Add a supported capability and mapping decision.")
        elif not matching_rules:
            finding.update(status="blocked", generation_impact="blocks_generation", decision_needed="Add a mapping rule.")
        elif matching_rules[0]["action"] == "configure":
            finding.update(status="configured", generation_impact="blocks_generation", mapping_rule=matching_rules[0]["id"], decision_needed=matching_rules[0]["decision_needed"])
        else:
            if mapping.get("format_version") == "2.0":
                finding.update(status="mapped", generation_impact="included", mapping_rule=matching_rules[0]["id"])
            else:
                finding.update(
                    status="configured",
                    generation_impact="blocks_generation",
                    mapping_rule=matching_rules[0]["id"],
                    decision_needed="Validate a concrete XML representation in a generation mapping profile.",
                )
        if finding.get("mapping_rule") is None:
            finding.pop("mapping_rule", None)
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


def _is_local_or_standard(resource: RdfTerm, inventory: Inventory, mapping: dict[str, object]) -> bool:
    if _in_scope(resource, inventory, mapping):
        return True
    return resource.value.startswith((RDF, RDFS, OWL, SKOS, XSD))


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
    finding_ids = {triple_id for finding in findings for triple_id in finding["triple_ids"] if finding["construct"] in {"unknown_namespace", "forbidden_namespace"}}
    counts: Counter[str] = Counter()
    for triple in inventory.triples:
        if triple.id not in finding_ids or triple.object.kind != "uri":
            continue
        prefix = triple.object.value.rsplit("#", 1)[0] + "#" if "#" in triple.object.value else triple.object.value.rsplit("/", 1)[0] + "/"
        counts[prefix] += 1
    return sorted(counts.items())
