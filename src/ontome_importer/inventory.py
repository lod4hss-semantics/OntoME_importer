"""Deterministic, generic representations of RDF graphs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Literal

from rdflib import BNode, Literal as RdfLiteral, URIRef
from rdflib.namespace import RDF


TermKind = Literal["uri", "blank_node", "literal"]


@dataclass(frozen=True)
class RdfTerm:
    kind: TermKind
    value: str
    language: str | None = None
    datatype: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"kind": self.kind, "value": self.value}
        if self.language is not None:
            result["language"] = self.language
        if self.datatype is not None:
            result["datatype"] = self.datatype
        return result


@dataclass(frozen=True)
class InventoryTriple:
    id: str
    subject: RdfTerm
    predicate: RdfTerm
    object: RdfTerm
    source_file: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "subject": self.subject.to_dict(),
            "predicate": self.predicate.to_dict(),
            "object": self.object.to_dict(),
            "provenance": {"file": self.source_file},
        }


@dataclass(frozen=True)
class InventoryResource:
    id: RdfTerm
    types: tuple[RdfTerm, ...]
    outgoing_assertion_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id.to_dict(),
            "types": [term.to_dict() for term in self.types],
            "outgoing_assertion_ids": list(self.outgoing_assertion_ids),
        }


@dataclass(frozen=True)
class Inventory:
    source_file: str
    source_format: str
    source_sha256: str
    resources: tuple[InventoryResource, ...]
    triples: tuple[InventoryTriple, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": "1.1",
            "source": {
                "file": self.source_file,
                "format": self.source_format,
                "sha256": self.source_sha256,
            },
            "resources": [resource.to_dict() for resource in self.resources],
            "triples": [triple.to_dict() for triple in self.triples],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"


def build_inventory(
    graph: object, *, source_file: str, source_format: str, source_sha256: str
) -> Inventory:
    """Build an inventory from an RDFLib graph without semantic interpretation."""
    raw_triples = list(graph)
    blank_node_ids = _canonical_blank_node_ids(raw_triples)
    triples = [
        _inventory_triple(raw_triple, blank_node_ids, source_file)
        for raw_triple in raw_triples
    ]
    triples.sort(key=lambda triple: triple.id)

    resource_terms: dict[RdfTerm, list[InventoryTriple]] = {}
    type_terms: dict[RdfTerm, list[RdfTerm]] = {}
    rdf_type = str(RDF.type)
    for triple in triples:
        resource_terms.setdefault(triple.subject, []).append(triple)
        if triple.object.kind != "literal":
            resource_terms.setdefault(triple.object, [])
        if triple.predicate.value == rdf_type and triple.object.kind != "literal":
            type_terms.setdefault(triple.subject, []).append(triple.object)

    resources = []
    for resource, outgoing in resource_terms.items():
        resources.append(
            InventoryResource(
                id=resource,
                types=tuple(sorted(set(type_terms.get(resource, [])), key=_term_key)),
                outgoing_assertion_ids=tuple(sorted(triple.id for triple in outgoing)),
            )
        )
    resources.sort(key=lambda resource: _term_key(resource.id))
    return Inventory(
        source_file=source_file,
        source_format=source_format,
        source_sha256=source_sha256,
        resources=tuple(resources),
        triples=tuple(triples),
    )


def _inventory_triple(
    raw_triple: tuple[object, object, object],
    blank_node_ids: dict[BNode, str],
    source_file: str,
) -> InventoryTriple:
    subject, predicate, object_ = raw_triple
    subject_term = _term_from_rdflib(subject, blank_node_ids)
    predicate_term = _term_from_rdflib(predicate, blank_node_ids)
    object_term = _term_from_rdflib(object_, blank_node_ids)
    if subject_term.kind == "literal" or predicate_term.kind != "uri":
        raise ValueError("RDFLib graph contains an invalid RDF triple")
    canonical = json.dumps(
        [subject_term.to_dict(), predicate_term.to_dict(), object_term.to_dict()],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return InventoryTriple(
        id=f"triple-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}",
        subject=subject_term,
        predicate=predicate_term,
        object=object_term,
        source_file=source_file,
    )


def _term_from_rdflib(term: object, blank_node_ids: dict[BNode, str]) -> RdfTerm:
    if isinstance(term, URIRef):
        return RdfTerm("uri", str(term))
    if isinstance(term, BNode):
        return RdfTerm("blank_node", blank_node_ids[term])
    if isinstance(term, RdfLiteral):
        if term.language is not None:
            return RdfTerm("literal", str(term), language=str(term.language))
        if term.datatype is not None:
            return RdfTerm("literal", str(term), datatype=str(term.datatype))
        return RdfTerm("literal", str(term))
    raise ValueError(f"Unsupported RDF term: {term!r}")


def _canonical_blank_node_ids(
    triples: list[tuple[object, object, object]],
) -> dict[BNode, str]:
    blank_nodes = {term for triple in triples for term in triple if isinstance(term, BNode)}
    signatures = {node: "blank" for node in blank_nodes}
    for _ in range(len(blank_nodes)):
        next_signatures = {
            node: _blank_node_signature(node, triples, signatures) for node in blank_nodes
        }
        if next_signatures == signatures:
            break
        signatures = next_signatures
    ordered_nodes = sorted(blank_nodes, key=lambda node: (signatures[node], str(node)))
    return {node: f"b{index}" for index, node in enumerate(ordered_nodes)}


def _blank_node_signature(
    node: BNode,
    triples: list[tuple[object, object, object]],
    signatures: dict[BNode, str],
) -> str:
    descriptions = []
    for subject, predicate, object_ in triples:
        if subject == node:
            descriptions.append(("out", str(predicate), _signature_term(object_, signatures)))
        if object_ == node:
            descriptions.append(("in", str(predicate), _signature_term(subject, signatures)))
    value = json.dumps(sorted(descriptions), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _signature_term(term: object, signatures: dict[BNode, str]) -> str:
    if isinstance(term, BNode):
        return f"blank:{signatures[term]}"
    if isinstance(term, URIRef):
        return f"uri:{term}"
    if isinstance(term, RdfLiteral):
        return json.dumps(
            [str(term), term.language, str(term.datatype) if term.datatype else None],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    raise ValueError(f"Unsupported RDF term: {term!r}")


def _term_key(term: RdfTerm) -> tuple[str, str, str, str]:
    return (term.kind, term.value, term.language or "", term.datatype or "")
