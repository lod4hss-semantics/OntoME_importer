"""Round-trip XLSX assistance for explicit OntoME mapping decisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ontome_importer.audit import audit_inventory
from ontome_importer.constructs import RDF, RDFS, OWL, SKOS, XSD
from ontome_importer.inventory import Inventory
from ontome_importer.package_resources import package_resource_path
from ontome_importer.external_references import ExternalReferenceError, resolve_external_reference, validate_external_reference_configuration
from ontome_importer.profiles import GenerationProfiles, ProfileError, validate_generation_mapping


WORKBOOK_VERSION = "1.7"
RULE_COLUMNS = (
    "id", "selector_uri", "selector_uri_prefix", "selector_rdf_type", "action", "entity_kind", "property_kind",
    "identifier_source", "identifier_strip_prefix", "identifier_predicate", "identifier_pattern", "label_predicates", "identifier_in_uri", "relations_json", "text_fields_json",
    "domain_predicate", "range_predicate", "reason", "decision_needed",
)
NAMESPACE_COLUMNS = ("uri", "ontome_namespace_id", "status", "source", "verified_at")
EXCEPTION_COLUMNS = ("uri", "reference_namespace", "identifier", "source", "notes")
EXTERNAL_RULE_COLUMNS = ("id", "uri_prefix", "reference_namespace", "identifier_source", "identifier_pattern")
EDITORIAL_EXCEPTION_COLUMNS = ("id", "resource_uri", "field", "reference_uri", "status", "rationale", "approved_by", "approved_at", "decision_reference")
DECISION_COLUMNS = ("id", "resource_uri", "construct", "action", "status", "rationale", "approved_by", "approved_at", "decision_reference", "mapping_rule", "exception_id")
RESOURCE_COLUMNS = ("uri", "rdf_types", "labels", "relations", "rule_id", "status", "notes", "finding_ids")
EXTERNAL_USAGE_COLUMNS = ("uri", "uri_prefix", "used_by", "predicates", "resolution_status", "resolution_origin", "reference_rule", "reference_namespace", "identifier", "category", "finding_ids", "next_action")
METADATA_COLUMNS = ("resource_uri", "construct", "example", "action", "reason", "status", "finding_id")
RED = PatternFill("solid", fgColor="FECACA")
ORANGE = PatternFill("solid", fgColor="FED7AA")
GREEN = PatternFill("solid", fgColor="BBF7D0")
GREY = PatternFill("solid", fgColor="E5E7EB")
BLUE = PatternFill("solid", fgColor="BFDBFE")


class AssistantError(ValueError):
    """The workbook is missing or contains invalid mapping decisions."""


def export_workbook(
    path: Path,
    profiles: GenerationProfiles,
    inventory: Inventory,
    catalog: Inventory | None = None,
    catalog_identifier_predicate: str | None = None,
    catalog_namespace_id: int | None = None,
) -> None:
    catalog_identifiers = _catalog_identifiers(catalog, catalog_identifier_predicate) if catalog else {}
    report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
    workbook = Workbook()
    readme = workbook.active
    readme.title = "SUMMARY"
    _append_rows(readme, [
        ("Mapping assistant", ""),
        ("Version", WORKBOOK_VERSION),
        ("Source SHA-256", inventory.source_sha256),
        ("Source format", inventory.source_format),
        ("Catalog", catalog.source_file if catalog else "Not supplied"),
        ("Instructions", "Edit only RULES, EXTERNAL_REFERENCE_RULES, EXTERNAL_EXCEPTIONS, EDITORIAL_EXCEPTIONS, DECISIONS, and NAMESPACE_REGISTRY. Red derived rows block compilation."),
        ("Authority", "Derived sheets never compile into mappings."),
    ])
    project = workbook.create_sheet("PROJECT")
    _append_rows(project, [
        ("target_namespace_uri", profiles.manifest["target"]["namespace_uri"]),
        ("publication_intent", "new_namespace"),
        ("note", "Existing published namespace updates require an official OntoME import contract."),
    ])
    rules = workbook.create_sheet("RULES")
    rules.append(RULE_COLUMNS)
    for rule in profiles.mapping["rules"]:
        rules.append(_rule_to_row(rule))
    namespaces = workbook.create_sheet("NAMESPACE_REGISTRY")
    namespaces.append(NAMESPACE_COLUMNS)
    for item in profiles.namespace_registry["namespaces"]:
        namespaces.append(tuple(item.get(column, "") for column in NAMESPACE_COLUMNS))
    exceptions = workbook.create_sheet("EXTERNAL_EXCEPTIONS")
    exceptions.append(EXCEPTION_COLUMNS)
    existing_references = {item["uri"]: item for item in profiles.mapping["external_references"]}
    detected_external_uris = _external_uris(inventory, profiles.mapping)
    ordered_external_uris = [item["uri"] for item in profiles.mapping["external_references"]]
    ordered_external_uris.extend(uri for uri in detected_external_uris if uri not in existing_references)
    for reference in profiles.mapping["external_references"]:
        exceptions.append((reference["uri"], reference["reference_namespace"], reference["identifier"], "mapping", ""))
    for uri, identifier in catalog_identifiers.items():
        if uri in detected_external_uris and uri not in existing_references:
            exceptions.append((uri, catalog_namespace_id, identifier, f"catalog:{catalog.source_file}", ""))
    external_rules = workbook.create_sheet("EXTERNAL_REFERENCE_RULES")
    external_rules.append(EXTERNAL_RULE_COLUMNS)
    for rule in profiles.mapping["external_reference_rules"]:
        extraction = rule["identifier_extraction"]
        external_rules.append((rule["id"], rule["uri_prefix"], rule["reference_namespace"], extraction["source"], extraction.get("pattern", "")))
    editorial = workbook.create_sheet("EDITORIAL_EXCEPTIONS")
    editorial.append(EDITORIAL_EXCEPTION_COLUMNS)
    for item in profiles.mapping["editorial_exceptions"]:
        editorial.append(tuple(item[column] for column in EDITORIAL_EXCEPTION_COLUMNS))
    decisions = workbook.create_sheet("DECISIONS")
    decisions.append(DECISION_COLUMNS)
    for item in profiles.mapping["decisions"]:
        decisions.append(tuple(item.get(column, "") for column in DECISION_COLUMNS))
    if catalog_namespace_id and catalog_identifiers:
        registered = {item["uri"] for item in profiles.namespace_registry["namespaces"]}
        for prefix in sorted({_uri_prefix(uri) for uri in catalog_identifiers if uri in detected_external_uris}):
            if prefix not in registered:
                namespaces.append((prefix, catalog_namespace_id, "active", f"catalog:{catalog.source_file}", ""))
    classes = workbook.create_sheet("CLASSES")
    properties = workbook.create_sheet("PROPERTIES")
    for sheet in (classes, properties):
        sheet.append(RESOURCE_COLUMNS)
    findings_by_resource: dict[str, list[dict[str, object]]] = {}
    for finding in report.findings:
        value = str(finding["resource"]["value"])
        findings_by_resource.setdefault(value, []).append(finding)
    triples_by_subject: dict[object, list[object]] = {}
    for triple in inventory.triples:
        triples_by_subject.setdefault(triple.subject, []).append(triple)
    for resource in inventory.resources:
        if resource.id.kind != "uri" or not _in_scope(resource.id.value, profiles.mapping, inventory):
            continue
        outgoing = triples_by_subject.get(resource.id, [])
        labels = [triple.object.value for triple in outgoing if triple.object.kind == "literal"]
        relations = [f"{triple.predicate.value} -> {triple.object.value}" for triple in outgoing if triple.object.kind == "uri"]
        findings = findings_by_resource.get(resource.id.value, [])
        row = (resource.id.value, " | ".join(term.value for term in resource.types), " | ".join(labels), "\n".join(relations), "", "blocked" if findings else "unreviewed", "", " | ".join(str(item["id"]) for item in findings))
        types = {term.value for term in resource.types}
        if "http://www.w3.org/2002/07/owl#Class" in types or "http://www.w3.org/2000/01/rdf-schema#Class" in types:
            classes.append(row)
        elif types & {"http://www.w3.org/2002/07/owl#ObjectProperty", "http://www.w3.org/2002/07/owl#DatatypeProperty", "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"}:
            properties.append(row)
    external = workbook.create_sheet("EXTERNAL_USAGE")
    external.append(EXTERNAL_USAGE_COLUMNS)
    uses = _external_uses(inventory, profiles.mapping)
    for uri in ordered_external_uris:
        usage = uses.get(uri, {"subjects": set(), "predicates": set(), "finding_ids": []})
        reference = existing_references.get(uri, {})
        try:
            resolved = resolve_external_reference(uri, profiles.mapping, profiles.namespace_registry)
        except ExternalReferenceError:
            resolved = None
        identifier = reference.get("identifier", resolved.identifier if resolved else catalog_identifiers.get(uri, ""))
        namespace_id = reference.get("reference_namespace", resolved.reference_namespace if resolved else catalog_namespace_id if identifier else "")
        origin = "exception" if reference else "rule" if resolved else "catalog" if uri in catalog_identifiers else ""
        category = "" if identifier else "missing_profile_rule"
        external.append((uri, _uri_prefix(uri), " | ".join(sorted(usage["subjects"])), " | ".join(sorted(usage["predicates"])), "resolved" if identifier else "blocked", origin, resolved.rule_id if resolved and resolved.rule_id else "", namespace_id, identifier, category, " | ".join(usage["finding_ids"]), "" if identifier else "Add an external rule or exact exception."))
    metadata = workbook.create_sheet("METADATA")
    metadata.append(METADATA_COLUMNS)
    for finding in report.findings:
        if finding["construct"] in {"unknown_predicate", "unknown_rdf_type", "annotation_property", "restriction", "union", "intersection", "property_chain", "cardinality"}:
            metadata.append((finding["resource"]["value"], finding["construct"], finding["example"], "", "", finding["status"], finding["id"]))
    blockers = workbook.create_sheet("BLOCKERS")
    blockers.append(("status", "category", "construct", "resource", "mapping_rule", "message", "next_action", "finding_id", "triple_ids"))
    for finding in report.findings:
        if finding["status"] != "mapped":
            category = finding["category"]
            blockers.append((finding["status"], category, finding["construct"], finding["resource"]["value"], finding.get("mapping_rule", ""), finding.get("decision_needed") or finding.get("reason") or "decision required", _next_action(category), finding["id"], " | ".join(finding["triple_ids"])))
    validation = workbook.create_sheet("VALIDATION")
    validation.append(("severity", "sheet", "row", "message"))
    metadata = workbook.create_sheet("_metadata")
    metadata.sheet_state = "hidden"
    metadata_rows = [("workbook_version", WORKBOOK_VERSION), ("source_sha256", inventory.source_sha256), ("manifest_sha256", _hash_json(profiles.manifest))]
    if catalog:
        metadata_rows.extend((("catalog_sha256", catalog.source_sha256), ("catalog_identifier_predicate", catalog_identifier_predicate or ""), ("catalog_namespace_id", str(catalog_namespace_id or ""))))
    _append_rows(metadata, metadata_rows)
    for sheet in workbook.worksheets:
        _format_sheet(sheet)
    _add_validations(rules, namespaces)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def check_workbook(path: Path, profiles: GenerationProfiles, inventory: Inventory) -> dict[str, object]:
    report, _ = _checked_workbook(path, profiles, inventory)
    return report


def refresh_workbook(path: Path, profiles: GenerationProfiles, inventory: Inventory) -> dict[str, object]:
    """Persist only derived validation and presentation data in a workbook."""
    report, workbook = _checked_workbook(path, profiles, inventory)
    if not report["valid"]:
        return report
    _annotate_workbook(workbook, report["issues"])
    workbook.save(path)
    return report


def annotate_workbook(path: Path, profiles: GenerationProfiles, inventory: Inventory, issues: list[dict[str, object]]) -> None:
    """Add normalized, derived issues without changing mapping decisions."""
    report, workbook = _checked_workbook(path, profiles, inventory)
    if not report["valid"]:
        raise AssistantError("Workbook cannot be annotated until its validation errors are resolved")
    _annotate_workbook(workbook, issues)
    workbook.save(path)


def _checked_workbook(path: Path, profiles: GenerationProfiles, inventory: Inventory) -> tuple[dict[str, object], object]:
    workbook = _load_workbook(path)
    issues: list[dict[str, object]] = []
    _check_metadata(workbook, profiles, inventory, issues)
    for sheet, columns in (("RULES", RULE_COLUMNS), ("NAMESPACE_REGISTRY", NAMESPACE_COLUMNS), ("EXTERNAL_EXCEPTIONS", EXCEPTION_COLUMNS), ("EXTERNAL_REFERENCE_RULES", EXTERNAL_RULE_COLUMNS), ("EDITORIAL_EXCEPTIONS", EDITORIAL_EXCEPTION_COLUMNS), ("DECISIONS", DECISION_COLUMNS)):
        _check_headers(workbook, sheet, columns, issues)
    if not issues:
        _validate_rows(workbook, issues)
    report = {"format_version": "1.0", "workbook": str(path), "valid": not any(issue["severity"] == "error" for issue in issues), "issues": issues}
    return report, workbook


def compile_workbook(path: Path, profiles: GenerationProfiles, inventory: Inventory) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    report, workbook = _checked_workbook(path, profiles, inventory)
    if not report["valid"]:
        raise AssistantError("Workbook has blocking validation errors")
    rules = [_rule_from_row(row) for row in _sheet_rows(workbook["RULES"], RULE_COLUMNS) if row["id"]]
    namespaces = [_namespace_from_row(row) for row in _sheet_rows(workbook["NAMESPACE_REGISTRY"], NAMESPACE_COLUMNS) if row["uri"]]
    references = [_reference_from_row(row) for row in _sheet_rows(workbook["EXTERNAL_EXCEPTIONS"], EXCEPTION_COLUMNS) if row["uri"]]
    external_rules = [_external_rule_from_row(row) for row in _sheet_rows(workbook["EXTERNAL_REFERENCE_RULES"], EXTERNAL_RULE_COLUMNS) if row["id"]]
    editorial_exceptions = [dict(row) for row in _sheet_rows(workbook["EDITORIAL_EXCEPTIONS"], EDITORIAL_EXCEPTION_COLUMNS) if row["id"]]
    decisions = [{key: value for key, value in row.items() if value != ""} for row in _sheet_rows(workbook["DECISIONS"], DECISION_COLUMNS) if row["id"]]
    mapping = {"format_version": "7.0", "scope": profiles.mapping["scope"], "rules": rules, "external_references": references, "external_reference_rules": external_rules, "editorial_exceptions": editorial_exceptions, "decisions": decisions}
    registry = {"format_version": "1.0", "namespaces": namespaces}
    validate_compiled_profiles(mapping, registry, profiles)
    report["provenance"] = {
        "workbook_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_sha256": inventory.source_sha256,
        "mapping_sha256": _hash_json(mapping),
        "namespace_registry_sha256": _hash_json(registry),
        "xsd_sha256": profiles.capability["xsd"]["sha256"],
    }
    return mapping, registry, report


def validate_compiled_profiles(mapping: dict[str, object], registry: dict[str, object], profiles: GenerationProfiles) -> None:
    """Validate exactly the YAML documents that compile would publish."""
    for value, schema_name in ((mapping, "schemas/config/mapping-profile-7.0.schema.json"), (registry, "schemas/config/namespace-registry.schema.json")):
        schema = json.loads(package_resource_path(schema_name).read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value), key=str)
        if errors:
            raise AssistantError(f"Compiled profile is invalid: {errors[0].message}")
    namespace_ids = [item["ontome_namespace_id"] for item in registry["namespaces"]]
    if len(namespace_ids) != len(set(namespace_ids)):
        raise AssistantError("OntoME namespace identifiers must be unique")
    rule_ids = [item["id"] for item in mapping["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise AssistantError("Mapping rule identifiers must be unique")
    try:
        validate_external_reference_configuration(mapping, registry)
    except ExternalReferenceError as error:
        raise AssistantError(str(error)) from error
    try:
        validate_generation_mapping(mapping, profiles.capability)
    except ProfileError as error:
        raise AssistantError(str(error)) from error


def dump_yaml(value: dict[str, object]) -> bytes:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).encode("utf-8")


def _load_workbook(path: Path):
    if path.suffix.lower() != ".xlsx" or not path.is_file():
        raise AssistantError(f"Workbook does not exist or is not an XLSX file: {path}")
    return load_workbook(path, read_only=False, data_only=False, keep_vba=False)


def _check_metadata(workbook: object, profiles: GenerationProfiles, inventory: Inventory, issues: list[dict[str, object]]) -> None:
    if "_metadata" not in workbook.sheetnames:
        issues.append(_issue("error", "_metadata", 0, "Workbook metadata sheet is missing."))
        return
    values = {row[0]: row[1] for row in workbook["_metadata"].iter_rows(values_only=True) if row[0]}
    if values.get("workbook_version") != WORKBOOK_VERSION:
        issues.append(_issue("error", "_metadata", 0, "Unsupported workbook version."))
    if values.get("source_sha256") != inventory.source_sha256:
        issues.append(_issue("error", "_metadata", 0, "Workbook source checksum does not match the manifest source."))
    if values.get("manifest_sha256") != _hash_json(profiles.manifest):
        issues.append(_issue("error", "_metadata", 0, "Workbook manifest checksum does not match."))


def _check_headers(workbook: object, name: str, expected: tuple[str, ...], issues: list[dict[str, object]]) -> None:
    if name not in workbook.sheetnames:
        issues.append(_issue("error", name, 0, "Required sheet is missing."))
        return
    actual = tuple(cell.value for cell in workbook[name][1])
    if actual != expected:
        issues.append(_issue("error", name, 1, "Workbook columns do not match the contract."))


def _validate_rows(workbook: object, issues: list[dict[str, object]]) -> None:
    identifiers: set[str] = set()
    mapping_rules: list[dict[str, object]] = []
    for row_number, row in enumerate(_sheet_rows(workbook["RULES"], RULE_COLUMNS), start=2):
        if not row["id"]:
            continue
        if row["id"] in identifiers:
            issues.append(_issue("error", "RULES", row_number, "Rule identifiers must be unique."))
        identifiers.add(row["id"])
        selector_count = sum(bool(row[column]) for column in RULE_COLUMNS[1:4])
        if selector_count == 0:
            issues.append(_issue("error", "RULES", row_number, "A rule requires at least one selector."))
        if row["action"] == "map":
            mapping_rules.append(row)
            required = ("entity_kind", "identifier_source", "label_predicates")
            if any(not row[column] for column in required):
                issues.append(_issue("error", "RULES", row_number, "A mapping rule requires entity kind, identifier strategy and label predicates."))
            if row["identifier_source"] == "uri_suffix" and not row["identifier_strip_prefix"]:
                issues.append(_issue("error", "RULES", row_number, "uri_suffix requires an identifier prefix."))
            if row["identifier_source"] == "literal_predicate" and not row["identifier_predicate"]:
                issues.append(_issue("error", "RULES", row_number, "literal_predicate requires an identifier predicate."))
            if row["identifier_source"] == "regex_capture" and not row["identifier_pattern"]:
                issues.append(_issue("error", "RULES", row_number, "regex_capture requires an identifier pattern."))
            if row["entity_kind"] == "property" and any(not row[column] for column in ("property_kind", "domain_predicate", "range_predicate")):
                issues.append(_issue("error", "RULES", row_number, "A property rule requires kind, domain predicate and range predicate."))
        elif row["action"] == "exclude" and not row["reason"]:
            issues.append(_issue("error", "RULES", row_number, "An exclusion requires a reason."))
        elif row["action"] == "configure" and not row["decision_needed"]:
            issues.append(_issue("error", "RULES", row_number, "A configured rule requires a decision description."))
        for column in ("relations_json", "text_fields_json"):
            if row[column]:
                try:
                    value = json.loads(str(row[column]))
                except json.JSONDecodeError:
                    issues.append(_issue("error", "RULES", row_number, f"{column} must contain valid JSON."))
                else:
                    if not isinstance(value, list):
                        issues.append(_issue("error", "RULES", row_number, f"{column} must contain a JSON array."))
    for sheet_name in ("CLASSES", "PROPERTIES"):
        for row_number, row in enumerate(_sheet_rows(workbook[sheet_name], RESOURCE_COLUMNS), start=2):
            if not row["uri"]:
                continue
            matches = [rule for rule in mapping_rules if _matches_resource_row(rule, row)]
            if len(matches) == 0:
                issues.append(_issue("error", sheet_name, row_number, "No mapping rule covers this resource."))
            elif len(matches) > 1:
                issues.append(_issue("error", sheet_name, row_number, "More than one mapping rule covers this resource."))
    namespace_values = [int(row["ontome_namespace_id"]) for row in _sheet_rows(workbook["NAMESPACE_REGISTRY"], NAMESPACE_COLUMNS) if row["uri"] and str(row["ontome_namespace_id"]).isdigit()]
    namespace_ids = set(namespace_values)
    if len(namespace_ids) != len(namespace_values):
        issues.append(_issue("error", "NAMESPACE_REGISTRY", 0, "OntoME namespace identifiers must be unique."))
    references: set[str] = set()
    for row_number, row in enumerate(_sheet_rows(workbook["EXTERNAL_EXCEPTIONS"], EXCEPTION_COLUMNS), start=2):
        if not row["uri"]:
            continue
        if row["uri"] in references:
            issues.append(_issue("error", "EXTERNAL_EXCEPTIONS", row_number, "External exception URIs must be unique."))
        references.add(row["uri"])
        if not str(row["reference_namespace"]).isdigit() or int(row["reference_namespace"]) not in namespace_ids or not row["identifier"]:
            issues.append(_issue("error", "EXTERNAL_EXCEPTIONS", row_number, "An external exception requires a registered namespace ID and identifier."))
    external_rule_ids: set[str] = set()
    for row_number, row in enumerate(_sheet_rows(workbook["EXTERNAL_REFERENCE_RULES"], EXTERNAL_RULE_COLUMNS), start=2):
        if not row["id"]:
            continue
        if row["id"] in external_rule_ids or not row["uri_prefix"] or not str(row["reference_namespace"]).isdigit() or not row["identifier_source"]:
            issues.append(_issue("error", "EXTERNAL_REFERENCE_RULES", row_number, "An external reference rule requires a unique ID, URI prefix, namespace ID, and identifier source."))
        external_rule_ids.add(row["id"])
    decision_ids: set[str] = set()
    for row_number, row in enumerate(_sheet_rows(workbook["DECISIONS"], DECISION_COLUMNS), start=2):
        if not row["id"]:
            continue
        if row["id"] in decision_ids:
            issues.append(_issue("error", "DECISIONS", row_number, "Decision identifiers must be unique."))
        decision_ids.add(row["id"])
        required = ("resource_uri", "construct", "action", "status", "rationale", "approved_by", "approved_at", "decision_reference")
        if any(not row[column] for column in required):
            issues.append(_issue("error", "DECISIONS", row_number, "A decision requires scope, action, approval, rationale, and reference."))
        if row["action"] == "editorial_exception" and not row["exception_id"]:
            issues.append(_issue("error", "DECISIONS", row_number, "An editorial exception decision requires an exception ID."))


def _rule_from_row(row: dict[str, object]) -> dict[str, object]:
    selector = {key.removeprefix("selector_"): row[key] for key in RULE_COLUMNS[1:4] if row[key]}
    result: dict[str, object] = {"id": row["id"], "selector": selector, "action": row["action"]}
    if row["action"] == "exclude":
        result["reason"] = row["reason"]
    elif row["action"] == "configure":
        result["decision_needed"] = row["decision_needed"]
    else:
        identifier: dict[str, object] = {"source": row["identifier_source"]}
        if row["identifier_strip_prefix"]:
            identifier["strip_prefix"] = row["identifier_strip_prefix"]
        if row["identifier_predicate"]:
            identifier["predicate"] = row["identifier_predicate"]
        if row["identifier_pattern"]:
            identifier["pattern"] = row["identifier_pattern"]
        target: dict[str, object] = {"entity_kind": row["entity_kind"], "identifier_in_namespace": identifier, "label_predicates": str(row["label_predicates"]).split()}
        if row["identifier_in_uri"]:
            target["identifier_in_uri"] = "source_uri"
        if row["relations_json"]:
            target["relations"] = json.loads(str(row["relations_json"]))
        if row["text_fields_json"]:
            target["text_fields"] = json.loads(str(row["text_fields_json"]))
        if row["entity_kind"] == "property":
            target["property_kind"] = row["property_kind"]
            target["domain_range"] = {"domain_predicate": row["domain_predicate"], "range_predicate": row["range_predicate"]}
        result["target"] = target
    return result


def _matches_resource_row(rule: dict[str, object], resource: dict[str, object]) -> bool:
    if rule["selector_uri"] and rule["selector_uri"] != resource["uri"]:
        return False
    if rule["selector_uri_prefix"] and not str(resource["uri"]).startswith(str(rule["selector_uri_prefix"])):
        return False
    if rule["selector_rdf_type"] and str(rule["selector_rdf_type"]) not in str(resource["rdf_types"]).split(" | "):
        return False
    return True


def _rule_to_row(rule: dict[str, object]) -> tuple[object, ...]:
    selector = rule["selector"]
    target = rule.get("target", {})
    identifier = target.get("identifier_in_namespace", {})
    domain_range = target.get("domain_range", {})
    return (
        rule["id"], selector.get("uri", ""), selector.get("uri_prefix", ""), selector.get("rdf_type", ""), rule["action"],
        target.get("entity_kind", ""), target.get("property_kind", ""), identifier.get("source", ""), identifier.get("strip_prefix", ""), identifier.get("predicate", ""), identifier.get("pattern", ""),
        " ".join(target.get("label_predicates", [])), "yes" if target.get("identifier_in_uri") else "",
        json.dumps(target.get("relations", []), ensure_ascii=False) if target.get("relations") else "",
        json.dumps(target.get("text_fields", []), ensure_ascii=False) if target.get("text_fields") else "",
        domain_range.get("domain_predicate", ""), domain_range.get("range_predicate", ""), rule.get("reason", ""), rule.get("decision_needed", ""),
    )


def _namespace_from_row(row: dict[str, object]) -> dict[str, object]:
    result = {"uri": row["uri"], "ontome_namespace_id": int(row["ontome_namespace_id"]), "status": row["status"], "source": row["source"]}
    if row["verified_at"]:
        result["verified_at"] = row["verified_at"]
    return result


def _reference_from_row(row: dict[str, object]) -> dict[str, object]:
    return {"uri": row["uri"], "reference_namespace": int(row["reference_namespace"]), "identifier": row["identifier"]}


def _external_rule_from_row(row: dict[str, object]) -> dict[str, object]:
    extraction: dict[str, object] = {"source": row["identifier_source"]}
    if row["identifier_pattern"]:
        extraction["pattern"] = row["identifier_pattern"]
    return {"id": row["id"], "uri_prefix": row["uri_prefix"], "reference_namespace": int(row["reference_namespace"]), "identifier_extraction": extraction}


def _sheet_rows(sheet: object, columns: tuple[str, ...]):
    for values in sheet.iter_rows(min_row=2, values_only=True):
        yield dict(zip(columns, ("" if value is None else value for value in values), strict=True))


def _external_uris(inventory: Inventory, mapping: dict[str, object]) -> list[str]:
    standard_reference_predicates = {
        f"{RDFS}subClassOf", f"{RDFS}subPropertyOf", f"{RDFS}domain", f"{RDFS}range",
        f"{OWL}equivalentClass", f"{OWL}equivalentProperty", f"{OWL}inverseOf",
    }
    return sorted({
        triple.object.value for triple in inventory.triples
        if triple.object.kind == "uri" and not _in_scope(triple.object.value, mapping, inventory)
        and (not triple.object.value.startswith((RDF, RDFS, OWL, SKOS, XSD)) or triple.predicate.value in standard_reference_predicates)
    })


def _external_uses(inventory: Inventory, mapping: dict[str, object]) -> dict[str, dict[str, set[str] | list[str]]]:
    uses: dict[str, dict[str, set[str] | list[str]]] = {}
    for triple in inventory.triples:
        if triple.object.kind != "uri" or triple.object.value not in _external_uris(inventory, mapping):
            continue
        item = uses.setdefault(triple.object.value, {"subjects": set(), "predicates": set(), "finding_ids": []})
        item["subjects"].add(triple.subject.value)
        item["predicates"].add(triple.predicate.value)
    return uses


def _catalog_identifiers(catalog: Inventory | None, predicate: str | None) -> dict[str, str]:
    if catalog is None or not predicate:
        raise AssistantError("A catalog requires --catalog-identifier-predicate")
    values: dict[str, set[str]] = {}
    for triple in catalog.triples:
        if triple.predicate.value == predicate and triple.subject.kind == "uri" and triple.object.kind == "literal" and triple.object.value:
            values.setdefault(triple.subject.value, set()).add(triple.object.value)
    ambiguous = sorted(uri for uri, identifiers in values.items() if len(identifiers) > 1)
    if ambiguous:
        raise AssistantError(f"Catalog identifier predicate is ambiguous for: {ambiguous[0]}")
    return {uri: next(iter(identifiers)) for uri, identifiers in values.items()}


def _uri_prefix(uri: str) -> str:
    return uri.rsplit("#", 1)[0] + "#" if "#" in uri else uri.rsplit("/", 1)[0] + "/"


def _in_scope(uri: str, mapping: dict[str, object], inventory: Inventory) -> bool:
    for selector in mapping["scope"]["resource_selectors"]:
        if "uri" in selector and uri != selector["uri"]:
            continue
        if "uri_prefix" in selector and not uri.startswith(str(selector["uri_prefix"])):
            continue
        if "rdf_type" in selector:
            resource = next((item for item in inventory.resources if item.id.kind == "uri" and item.id.value == uri), None)
            if resource is None or not any(term.value == selector["rdf_type"] for term in resource.types):
                continue
        return True
    return False


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _append_rows(sheet: object, rows: list[tuple[str, str]]) -> None:
    for row in rows:
        sheet.append(row)


def _format_sheet(sheet: object) -> None:
    sheet.freeze_panes = "A2"
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(48, max(14, max(len(str(cell.value or "")) for cell in column) + 2))


def _add_validations(rules: object, namespaces: object) -> None:
    action = DataValidation(type="list", formula1='"map,configure,exclude"')
    entity = DataValidation(type="list", formula1='"class,property"')
    property_kind = DataValidation(type="list", formula1='"object,datatype,rdf"')
    identifier_source = DataValidation(type="list", formula1='"uri_suffix,literal_predicate,regex_capture"')
    status = DataValidation(type="list", formula1='"active,deprecated,forbidden"')
    for validation, target in ((action, "E2:E1048576"), (entity, "F2:F1048576"), (property_kind, "G2:G1048576")):
        rules.add_data_validation(validation)
        validation.add(target)
    rules.add_data_validation(identifier_source)
    identifier_source.add("H2:H1048576")
    namespaces.add_data_validation(status)
    status.add("C2:C1048576")


def _issue(severity: str, sheet: str, row: int, message: str, **context: object) -> dict[str, object]:
    return {"severity": severity, "sheet": sheet, "row": row, "message": message, **context}


def _next_action(category: str) -> str:
    actions = {
        "missing_profile_rule": "Add or correct a mapping rule.", "missing_external_data": "Confirm and register the external namespace.",
        "forbidden_external_namespace": "Remove or replace the forbidden reference.", "ambiguous_source_data": "Select or correct the source value.",
        "incomplete_source_data": "Complete the source or use an approved exception.", "invalid_source_data": "Correct the source data or extraction strategy.",
        "unsupported_rdf_construct": "Exclude explicitly or wait for a supported capability.", "invalid_profile": "Correct the profile decision.",
    }
    return actions.get(category, "Review the reported finding.")


def _annotate_workbook(workbook: object, issues: list[dict[str, object]]) -> None:
    validation = workbook["VALIDATION"]
    if validation.max_row > 1:
        validation.delete_rows(2, validation.max_row - 1)
    validation.delete_rows(1, 1)
    validation.append(("phase", "severity", "sheet", "row", "resource_uri", "mapping_rule", "external_uri", "triple_ids", "code", "message"))
    for issue in issues:
        validation.append((
            issue.get("phase", "workbook"), issue["severity"], issue.get("sheet", "VALIDATION"), issue.get("row", 0),
            issue.get("resource_uri", ""), issue.get("mapping_rule", ""), issue.get("external_uri", ""),
            " | ".join(issue.get("triple_ids", [])), issue.get("code", ""), issue["message"],
        ))
    _clear_fills(workbook)
    for sheet_name in ("CLASSES", "PROPERTIES", "EXTERNAL_USAGE", "METADATA", "BLOCKERS"):
        sheet = workbook[sheet_name]
        for row in range(2, sheet.max_row + 1):
            status_column = 1 if sheet_name == "BLOCKERS" else 5 if sheet_name == "EXTERNAL_USAGE" else 6
            status = str(sheet.cell(row, status_column).value or "").lower()
            fill = RED if status in {"blocked", "invalid", "error"} else ORANGE if status in {"configured", "unreviewed"} else GREEN if status in {"mapped", "green", "resolved"} else GREY if status == "excluded" else None
            if fill:
                for cell in sheet[row]:
                    cell.fill = fill
    for row in range(2, validation.max_row + 1):
        if validation.cell(row, 2).value == "error":
            for cell in validation[row]:
                cell.fill = RED
    for issue in issues:
        _color_issue(workbook, issue)


def _clear_fills(workbook: object) -> None:
    for sheet_name in ("CLASSES", "PROPERTIES", "EXTERNAL_USAGE", "RULES", "METADATA", "BLOCKERS", "VALIDATION"):
        if sheet_name not in workbook.sheetnames:
            continue
        for row in workbook[sheet_name].iter_rows():
            for cell in row:
                cell.fill = PatternFill()


def _color_issue(workbook: object, issue: dict[str, object]) -> None:
    fill = RED if issue["severity"] == "error" else ORANGE
    sheet_name = str(issue.get("sheet", ""))
    row = issue.get("row")
    if sheet_name in workbook.sheetnames and isinstance(row, int) and row >= 2:
        for cell in workbook[sheet_name][row]:
            cell.fill = fill
    resource_uri = str(issue.get("resource_uri", ""))
    mapping_rule = str(issue.get("mapping_rule", ""))
    external_uri = str(issue.get("external_uri", ""))
    for name in ("CLASSES", "PROPERTIES"):
        if resource_uri and name in workbook.sheetnames:
            for candidate in range(2, workbook[name].max_row + 1):
                if workbook[name].cell(candidate, 1).value == resource_uri:
                    for cell in workbook[name][candidate]:
                        cell.fill = fill
    if mapping_rule and "RULES" in workbook.sheetnames:
        for candidate in range(2, workbook["RULES"].max_row + 1):
            if workbook["RULES"].cell(candidate, 1).value == mapping_rule:
                for cell in workbook["RULES"][candidate]:
                    cell.fill = fill
    if external_uri and "EXTERNAL_USAGE" in workbook.sheetnames:
        for candidate in range(2, workbook["EXTERNAL_USAGE"].max_row + 1):
            if workbook["EXTERNAL_USAGE"].cell(candidate, 1).value == external_uri:
                for cell in workbook["EXTERNAL_USAGE"][candidate]:
                    cell.fill = fill
