"""Deterministic OntoME XML serialization from resolved values only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lxml import etree

from ontome_importer.resolution import ResolvedGeneration, ResolvedReference, ResolvedText


class XmlGenerationError(ValueError):
    """The resolved model cannot be serialized as a valid OntoME XML import."""


def write_xml(generation: ResolvedGeneration, capability: dict[str, object], xsd_path: Path, source_sha256: str) -> tuple[bytes, dict[str, object]]:
    root = etree.Element("namespace")
    entries: list[dict[str, object]] = []
    namespace = generation.namespace
    for index, text in enumerate(namespace.labels, 1):
        _text_element(root, "standardLabel", text, f"/namespace/standardLabel[{index}]", entries)
    if not namespace.labels:
        raise XmlGenerationError("Namespace requires at least one standardLabel.")
    _configured(root, "version", namespace.version, "/namespace/version", entries)
    _configured(root, "publishedAt", namespace.published_at, "/namespace/publishedAt", entries)
    _configured(root, "contributors", namespace.contributors, "/namespace/contributors", entries)
    for index, reference_namespace in enumerate(namespace.reference_namespaces, 1):
        _configured(root, "referenceNamespace", str(reference_namespace), f"/namespace/referenceNamespace[{index}]", entries)
    _configured(root, "namespaceURI", namespace.namespace_uri, "/namespace/namespaceURI", entries)
    for index, text in enumerate(namespace.descriptions, 1):
        _text_element(root, "description", text, f"/namespace/description[{index}]", entries)
    if generation.classes:
        classes = etree.SubElement(root, "classes")
        for index, item in enumerate(generation.classes, 1):
            element = etree.SubElement(classes, "class")
            base = f"/namespace/classes/class[{index}]"
            _rdf_value(element, "identifierInNamespace", item.identifier, item.resource, item.identifier_triple_ids, item.mapping_rule, "rdf" if item.identifier_triple_ids else item.identifier_origin, f"{base}/identifierInNamespace", entries)
            if item.identifier_uri:
                _rdf_value(element, "identifierInURI", item.identifier_uri, item.resource, item.source_triple_ids, item.mapping_rule, "rdf", f"{base}/identifierInURI", entries)
            for label_index, text in enumerate(item.labels, 1):
                _text_element(element, "standardLabel", text, f"{base}/standardLabel[{label_index}]", entries)
            _relations(element, item.relations, ("subClassOf", "equivalentClass", "disjointWith"), base, entries)
            _texts(element, item.texts, base, entries)
    if generation.properties:
        properties = etree.SubElement(root, "properties")
        for index, item in enumerate(generation.properties, 1):
            element = etree.SubElement(properties, "property")
            base = f"/namespace/properties/property[{index}]"
            _rdf_value(element, "identifierInNamespace", item.identifier, item.resource, item.identifier_triple_ids, item.mapping_rule, "rdf" if item.identifier_triple_ids else item.identifier_origin, f"{base}/identifierInNamespace", entries)
            if item.identifier_uri:
                _rdf_value(element, "identifierInURI", item.identifier_uri, item.resource, item.source_triple_ids, item.mapping_rule, "rdf", f"{base}/identifierInURI", entries)
            for label_index, text in enumerate(item.labels, 1):
                label = etree.SubElement(element, "label", lang=text.language)
                standard = etree.SubElement(label, "standardLabel")
                standard.text = text.value
                _entry(entries, f"{base}/label[{label_index}]/standardLabel[1]", "standardLabel", text.value, {"lang": text.language}, text.resource, text.triple_ids, text.mapping_rule, text.origin)
            _relations(element, item.relations, ("subPropertyOf", "equivalentProperty", "inverseOf"), base, entries)
            if item.domain is None or item.range is None:
                raise XmlGenerationError("Resolved property has no domain or range.")
            _reference_element(element, "hasDomain", item.domain, f"{base}/hasDomain", entries)
            _reference_element(element, "hasRange", item.range, f"{base}/hasRange", entries)
            _texts(element, item.texts, base, entries)
    xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    document = etree.fromstring(xml)
    if not schema.validate(document):
        raise XmlGenerationError(f"Generated XML does not validate against XSD: {schema.error_log.last_error}")
    xml_sha256 = hashlib.sha256(xml).hexdigest()
    for entry in entries:
        entry["id"] = "trace-" + hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    xsd = capability["xsd"]
    trace = {"format_version": "1.2", "source_sha256": source_sha256, "xsd": {"version": xsd["version"], "sha256": xsd["sha256"]}, "xml_sha256": xml_sha256, "entries": entries}
    return xml, trace


def _configured(parent: etree._Element, name: str, value: str | None, path: str, entries: list[dict[str, object]]) -> None:
    if value is not None:
        _rdf_value(parent, name, value, None, (), "manifest", "configuration", path, entries)


def _texts(parent: etree._Element, texts: tuple[tuple[str, ResolvedText], ...], base: str, entries: list[dict[str, object]]) -> None:
    if not texts:
        return
    wrapper = etree.SubElement(parent, "textProperties")
    counts: dict[str, int] = {}
    order = {"scopeNote": 0, "example": 1, "contextNote": 2, "bibliographicalNote": 3}
    for field, text in sorted(texts, key=lambda item: (order[item[0]], item[1].language, item[1].value, item[1].triple_ids)):
        counts[field] = counts.get(field, 0) + 1
        _text_element(wrapper, field, text, f"{base}/textProperties/{field}[{counts[field]}]", entries)


def _relations(parent: etree._Element, relations: tuple[tuple[str, ResolvedReference], ...], order: tuple[str, ...], base: str, entries: list[dict[str, object]]) -> None:
    for field in order:
        values = [reference for candidate, reference in relations if candidate == field]
        for index, reference in enumerate(values, 1):
            _reference_element(parent, field, reference, f"{base}/{field}[{index}]", entries)


def _text_element(parent: etree._Element, name: str, text: ResolvedText, path: str, entries: list[dict[str, object]]) -> None:
    _rdf_value(parent, name, text.value, text.resource, text.triple_ids, text.mapping_rule, text.origin, path, entries, {"lang": text.language})


def _reference_element(parent: etree._Element, name: str, reference: ResolvedReference, path: str, entries: list[dict[str, object]]) -> None:
    attributes = {} if reference.reference_namespace is None else {"referenceNamespace": str(reference.reference_namespace)}
    _rdf_value(parent, name, reference.value, reference.resource, reference.triple_ids, reference.mapping_rule, reference.origin, path, entries, attributes, reference.reference_rule, reference.exception_id)


def _rdf_value(parent: etree._Element, name: str, value: str, resource: object, triple_ids: tuple[str, ...], mapping_rule: str, origin: str, path: str, entries: list[dict[str, object]], attributes: dict[str, str] | None = None, reference_rule: str | None = None, exception_id: str | None = None) -> None:
    attributes = attributes or {}
    element = etree.SubElement(parent, name, **attributes)
    element.text = value
    _entry(entries, path, name, value, attributes, resource, triple_ids, mapping_rule, origin, reference_rule, exception_id)


def _entry(entries: list[dict[str, object]], path: str, element: str, value: str, attributes: dict[str, str], resource: object, triple_ids: tuple[str, ...], mapping_rule: str, origin: str, reference_rule: str | None = None, exception_id: str | None = None) -> None:
    entry: dict[str, object] = {"xml_path": path, "element": element, "value": value, "attributes": dict(sorted(attributes.items())), "source_triples": list(triple_ids), "mapping_rule": mapping_rule, "origin": origin}
    if resource is not None:
        entry["source_resource"] = resource.to_dict()
    if reference_rule is not None:
        entry["reference_rule"] = reference_rule
    if exception_id is not None:
        entry["exception_id"] = exception_id
    entries.append(entry)
