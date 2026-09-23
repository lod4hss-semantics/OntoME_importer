"""Validation of published OntoME generation bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from lxml import etree

from ontome_importer.inventory import Inventory
from ontome_importer.external_references import ExternalReferenceError, resolve_external_reference
from ontome_importer.loader import load_inventory
from ontome_importer.package_resources import package_resource_path
from ontome_importer.profiles import ProfileError, load_generation_profiles, verify_capability_xsd, verify_source_checksum
from ontome_importer.resolution import resolve_generation
from ontome_importer.xml_writer import XmlGenerationError, write_xml


def validate_generation(manifest_path: Path, xml_path: Path, trace_path: Path, audit_path: Path) -> dict[str, object]:
    profiles = load_generation_profiles(manifest_path)
    xsd_path = verify_capability_xsd(profiles.capability)
    source = profiles.manifest["source"]
    assert isinstance(source, dict)
    source_path = manifest_path.parent / str(source["file"])
    verify_source_checksum(profiles.manifest, source_path)
    inventory = load_inventory(source_path, str(source["format"]))
    checks: list[dict[str, object]] = []
    duplicates: list[str] = []
    unresolved: list[str] = []
    count_differences: list[str] = []
    untraced: list[str] = []
    absent: list[str] = []

    def check(name: str, valid: bool, message: str | None = None, location: str | None = None) -> None:
        item: dict[str, object] = {"name": name, "valid": valid}
        if message:
            item["message"] = message
        if location:
            item["location"] = location
        checks.append(item)

    xml_bytes = _read_bytes(xml_path, "xml_artifact", check)
    trace = _read_json(trace_path, "trace_json", check)
    audit = _read_json(audit_path, "audit_json", check)
    trace_valid = _validate_json_schema(trace, "schemas/reports/generation-trace-1.2.schema.json", "trace_schema", check)
    audit_valid = _validate_json_schema(audit, "schemas/reports/generation-audit-1.1.schema.json", "audit_schema", check)
    xml_document = _parse_xml(xml_bytes, check)
    try:
        schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as error:
        raise ProfileError(f"Capability XSD cannot be compiled: {error}") from error
    if xml_document is not None:
        valid_xsd = schema.validate(xml_document)
        check("xml_xsd_valid", valid_xsd, None if valid_xsd else str(schema.error_log.last_error))
    else:
        check("xml_xsd_valid", False, "XML is not well formed.")

    xml_sha256 = hashlib.sha256(xml_bytes).hexdigest() if xml_bytes is not None else ""
    if isinstance(trace, dict) and trace_valid:
        check("xml_sha256_matches_trace", trace["xml_sha256"] == xml_sha256, "XML checksum differs from generation trace.", "generation-trace.json#/xml_sha256")
        check("trace_source_sha256_matches_source", trace["source_sha256"] == inventory.source_sha256, "Trace source checksum differs from source.")
        check("trace_xsd_matches_capability", trace["xsd"] == _xsd_identity(profiles.capability), "Trace XSD identity differs from capability profile.")
    if isinstance(audit, dict) and audit_valid:
        check("audit_source_sha256_matches_source", audit["source"]["sha256"] == inventory.source_sha256, "Audit source checksum differs from source.")
        check("audit_xsd_matches_capability", audit["xsd"] == _xsd_identity(profiles.capability), "Audit XSD identity differs from capability profile.")
        check("generation_audit_strict_ok", audit["strict_ok"] is True, "Generation audit is not strict_ok.")
        actual_counts: dict[str, int] = {}
        for finding in audit["findings"]:
            status = finding.get("status")
            if isinstance(status, str):
                actual_counts[status] = actual_counts.get(status, 0) + 1
        if actual_counts != audit["counts"]:
            count_differences.append("generation-audit counts do not match findings")
        check("generation_audit_counts", actual_counts == audit["counts"], "Generation audit counts differ from its findings.")
    if isinstance(trace, dict) and isinstance(audit, dict) and trace_valid and audit_valid:
        check("trace_and_audit_source_agree", trace["source_sha256"] == audit["source"]["sha256"], "Trace and audit source checksums differ.")

    if xml_document is not None:
        _check_xml_structure(xml_document, duplicates, unresolved, check)
    if xml_document is not None and isinstance(trace, dict) and trace_valid:
        _check_trace(trace, xml_document, inventory, profiles.mapping, unresolved, untraced, check)
    if xml_document is not None and isinstance(trace, dict) and trace_valid:
        _check_reference_namespaces(xml_document, trace, profiles.mapping, profiles.namespace_registry, unresolved, check)

    if xml_document is not None and trace_valid and audit_valid:
        result = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, profiles.namespace_registry)
        check("source_reconstruction_not_blocked", result.generation is not None, "Current source and profiles no longer resolve.")
        if result.generation is not None:
            try:
                expected_xml, expected_trace = write_xml(result.generation, profiles.capability, xsd_path, inventory.source_sha256)
                check("xml_matches_reconstruction", expected_xml == xml_bytes, "XML differs from deterministic reconstruction.")
                check("trace_matches_reconstruction", expected_trace == trace, "Trace differs from deterministic reconstruction.")
                check("generation_audit_matches_reconstruction", result.audit == audit, "Generation audit differs from deterministic reconstruction.")
                _check_resolved_identifiers(result.generation, xml_document, absent, check)
            except XmlGenerationError as error:
                check("xml_reconstruction", False, str(error))

    checks.sort(key=lambda item: str(item["name"]))
    failures = sum(not item["valid"] for item in checks)
    return {
        "format_version": "1.1",
        "valid": failures == 0,
        "source": {"file": inventory.source_file, "sha256": inventory.source_sha256},
        "xsd": _xsd_identity(profiles.capability),
        "artifacts": {"xml_sha256": xml_sha256, "trace": trace_path.name, "audit": audit_path.name},
        "checks": checks,
        "duplicate_identifiers": sorted(set(duplicates)),
        "unresolved_references": sorted(set(unresolved)),
        "count_differences": sorted(set(count_differences)),
        "xml_elements_without_trace": sorted(set(untraced)),
        "resolved_resources_absent_from_xml": sorted(set(absent)),
        "counts": {"passed": len(checks) - failures, "failed": failures},
    }


def _read_bytes(path: Path, name: str, check: object) -> bytes | None:
    try:
        value = path.read_bytes()
    except OSError as error:
        check(name, False, str(error), str(path))
        return None
    check(name, True)
    return value


def _read_json(path: Path, name: str, check: object) -> object | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        check(name, False, str(error), str(path))
        return None
    check(name, True)
    return value


def _validate_json_schema(value: object | None, schema_path: str, name: str, check: object) -> bool:
    if value is None:
        check(name, False, "Artifact is unavailable.")
        return False
    schema = json.loads(package_resource_path(schema_path).read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(value))
    check(name, not errors, str(errors[0]) if errors else None)
    return not errors


def _parse_xml(xml_bytes: bytes | None, check: object) -> etree._Element | None:
    if xml_bytes is None:
        check("xml_well_formed", False, "XML artifact is unavailable.")
        return None
    try:
        document = etree.fromstring(xml_bytes, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as error:
        check("xml_well_formed", False, str(error))
        return None
    check("xml_well_formed", True)
    return document


def _xsd_identity(capability: dict[str, object]) -> dict[str, str]:
    xsd = capability["xsd"]
    assert isinstance(xsd, dict)
    return {"version": str(xsd["version"]), "sha256": str(xsd["sha256"])}


def _check_xml_structure(document: etree._Element, duplicates: list[str], unresolved: list[str], check: object) -> None:
    identifiers = document.xpath("/namespace/classes/class/identifierInNamespace/text() | /namespace/properties/property/identifierInNamespace/text()")
    duplicates.extend(value for value in identifiers if identifiers.count(value) > 1)
    invalid = [value for value in identifiers if not value or any(character.isspace() for character in value) or "{" in value or "}" in value]
    check("local_identifier_uniqueness", not duplicates, "Duplicate local identifiers." if duplicates else None)
    check("local_identifier_validity", not invalid, "Invalid local identifiers." if invalid else None)
    class_labels = document.xpath("/namespace/classes/class[not(standardLabel[@lang])]")
    property_labels = document.xpath("/namespace/properties/property[not(label[@lang]/standardLabel)]")
    invalid_properties = document.xpath("/namespace/properties/property[count(hasDomain) != 1 or count(hasRange) != 1]")
    check("class_labels", not class_labels, "Class without localized standardLabel." if class_labels else None)
    check("property_labels", not property_labels, "Property without localized label." if property_labels else None)
    check("property_domain_range", not invalid_properties, "Property requires one domain and one range." if invalid_properties else None)
    empty_wrappers = document.xpath("/namespace/classes[not(class)] | /namespace/properties[not(property)]")
    check("nonempty_entity_wrappers", not empty_wrappers, "XML contains an empty classes or properties wrapper." if empty_wrappers else None)


def _check_trace(trace: dict[str, object], document: etree._Element, inventory: Inventory, mapping: dict[str, object], unresolved: list[str], untraced: list[str], check: object) -> None:
    entries = trace["entries"]
    ids = [entry["id"] for entry in entries]
    paths = [entry["xml_path"] for entry in entries]
    check("trace_ids_unique", len(ids) == len(set(ids)), "Duplicate trace IDs." if len(ids) != len(set(ids)) else None)
    check("trace_paths_unique", len(paths) == len(set(paths)), "Duplicate trace paths." if len(paths) != len(set(paths)) else None)
    triple_ids = {triple.id for triple in inventory.triples}
    resources = {resource.id for resource in inventory.resources}
    rules = {rule["id"] for rule in mapping["rules"]}
    traced_nodes: set[etree._Element] = set()
    for entry in entries:
        expected_id = "trace-" + hashlib.sha256(json.dumps({key: value for key, value in entry.items() if key != "id"}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        check(f"trace_id:{entry['id']}", entry["id"] == expected_id, "Trace entry identifier is invalid.", entry["xml_path"])
        try:
            matches = document.xpath(entry["xml_path"])
        except etree.XPathEvalError:
            matches = []
        valid_node = len(matches) == 1 and isinstance(matches[0], etree._Element)
        check(f"trace_path:{entry['id']}", valid_node, "Trace path does not identify exactly one XML element.", entry["xml_path"])
        if valid_node:
            node = matches[0]
            traced_nodes.add(node)
            attributes = dict(sorted(node.attrib.items()))
            if node.tag == "standardLabel" and node.getparent() is not None and node.getparent().tag == "label":
                attributes = dict(sorted(node.getparent().attrib.items()))
            matches_value = (node.tag == entry["element"] and (node.text or "") == entry["value"] and attributes == entry["attributes"])
            check(f"trace_value:{entry['id']}", matches_value, "Trace element, value, or attributes differ from XML.", entry["xml_path"])
        sources_valid = all(identifier in triple_ids for identifier in entry["source_triples"])
        check(f"trace_source_triples:{entry['id']}", sources_valid, "Trace names an unknown source triple.")
        if entry["origin"] == "configuration":
            check(f"trace_origin:{entry['id']}", entry["mapping_rule"] == "manifest" and not entry["source_triples"], "Configuration trace has RDF provenance.")
        elif entry["origin"] in {"identifier_uri_suffix", "identifier_regex_capture"}:
            check(f"trace_origin:{entry['id']}", not entry["source_triples"] and entry["mapping_rule"] in rules, "Identifier strategy trace has invalid provenance.")
        elif entry["origin"] == "editorial_exception":
            exception = next((item for item in mapping.get("editorial_exceptions", []) if item["id"] == entry.get("exception_id")), None)
            resource = entry.get("source_resource")
            expected_field = "hasDomain" if entry["element"] == "hasDomain" else "hasRange" if entry["element"] == "hasRange" else None
            valid_exception = (
                exception is not None
                and exception["status"] == "approved"
                and isinstance(resource, dict)
                and resource.get("kind") == "uri"
                and resource.get("value") == exception["resource_uri"]
                and exception["field"] == expected_field
                and _resource_in_inventory(resource, resources)
            )
            check(f"trace_origin:{entry['id']}", not entry["source_triples"] and entry["mapping_rule"] in rules and valid_exception, "Editorial exception trace has invalid provenance.")
        else:
            resource = entry.get("source_resource")
            valid_resource = isinstance(resource, dict) and _resource_in_inventory(resource, resources)
            check(f"trace_origin:{entry['id']}", bool(entry["source_triples"]) and valid_resource, "RDF trace lacks valid provenance.")
            if entry["mapping_rule"] not in rules:
                unresolved.append(f"unknown mapping rule {entry['mapping_rule']}")
    untraced.extend(_xml_path(document, element) for element in document.iter() if len(element) == 0 and element not in traced_nodes)
    check("xml_leaves_traced", not untraced, "XML leaf has no trace entry." if untraced else None)


def _resource_in_inventory(resource: dict[str, object], resources: set[object]) -> bool:
    try:
        from ontome_importer.inventory import RdfTerm
        return RdfTerm(resource["kind"], resource["value"], resource.get("language"), resource.get("datatype")) in resources
    except (KeyError, TypeError, ValueError):
        return False


def _xml_path(document: etree._Element, element: etree._Element) -> str:
    return document.getroottree().getpath(element)


def _check_reference_namespaces(document: etree._Element, trace: dict[str, object], mapping: dict[str, object], registry: dict[str, object], unresolved: list[str], check: object) -> None:
    root_namespaces: set[int] = set()
    valid = True
    for value in document.xpath("/namespace/referenceNamespace/text()"):
        namespace = _positive_integer(value)
        if namespace is None:
            valid = False
            unresolved.append(f"root:{value}")
        else:
            root_namespaces.add(namespace)
    registry_ids = {item["ontome_namespace_id"]: item for item in registry["namespaces"]}
    trace_by_node: dict[etree._Element, dict[str, object]] = {}
    for entry in trace["entries"]:
        try:
            matches = document.xpath(entry["xml_path"])
        except etree.XPathEvalError:
            matches = []
        if len(matches) == 1 and isinstance(matches[0], etree._Element):
            trace_by_node[matches[0]] = entry
    for node in document.xpath("//*[@referenceNamespace]"):
        namespace = _positive_integer(node.attrib["referenceNamespace"])
        if namespace is None:
            valid = False
            unresolved.append(f"{node.tag}:{node.text or ''}:{node.attrib['referenceNamespace']}")
            continue
        entry = trace_by_node.get(node)
        source_resource = entry.get("source_resource") if entry else None
        try:
            if entry and entry.get("origin") == "editorial_exception":
                exception = next((item for item in mapping.get("editorial_exceptions", []) if item["id"] == entry.get("exception_id")), None)
                resolved = resolve_external_reference(exception["reference_uri"], mapping, registry) if exception else None
            else:
                resolved = resolve_external_reference(source_resource["value"], mapping, registry) if isinstance(source_resource, dict) else None
        except (ExternalReferenceError, KeyError):
            resolved = None
        provenance_matches = entry and (entry.get("origin") == "editorial_exception" or (resolved is not None and resolved.origin == entry.get("origin") and resolved.rule_id == entry.get("reference_rule")))
        if namespace not in root_namespaces or namespace not in registry_ids or registry_ids[namespace]["status"] == "forbidden" or resolved is None or resolved.reference_namespace != namespace or resolved.identifier != (node.text or "") or not provenance_matches:
            valid = False
            unresolved.append(f"{node.tag}:{node.text or ''}:{namespace}")
    check("external_references", valid, "External XML reference is absent, forbidden, or undeclared." if not valid else None)
    local_values = {value for value in document.xpath("/namespace/classes/class/identifierInNamespace/text() | /namespace/properties/property/identifierInNamespace/text()")}
    local_nodes = document.xpath("//subClassOf[not(@referenceNamespace)] | //equivalentClass[not(@referenceNamespace)] | //disjointWith[not(@referenceNamespace)] | //subPropertyOf[not(@referenceNamespace)] | //equivalentProperty[not(@referenceNamespace)] | //inverseOf[not(@referenceNamespace)] | //hasDomain[not(@referenceNamespace)] | //hasRange[not(@referenceNamespace)]")
    missing = [node.text for node in local_nodes if (node.text or "") not in local_values]
    unresolved.extend(f"local:{value}" for value in missing)
    check("local_references", not missing, "Local XML reference has no generated target." if missing else None)


def _positive_integer(value: object) -> int | None:
    try:
        result = int(str(value))
    except ValueError:
        return None
    return result if result > 0 else None


def _check_resolved_identifiers(generation: object, document: etree._Element, absent: list[str], check: object) -> None:
    expected = {item.identifier for item in (*generation.classes, *generation.properties)}
    actual = set(document.xpath("/namespace/classes/class/identifierInNamespace/text() | /namespace/properties/property/identifierInNamespace/text()"))
    absent.extend(expected - actual)
    check("resolved_resources_present", not absent, "Resolved resources are absent from XML." if absent else None)
