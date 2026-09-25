"""Generic detection of RDF, RDFS, OWL and SKOS constructs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ontome_importer.inventory import Inventory, InventoryTriple, RdfTerm


RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
XSD = "http://www.w3.org/2001/XMLSchema#"

TYPE_CONSTRUCTS = {
    f"{RDF}Property": "rdf_property", f"{RDFS}Class": "rdfs_class", f"{OWL}Class": "owl_class",
    f"{OWL}ObjectProperty": "object_property", f"{OWL}DatatypeProperty": "datatype_property",
    f"{OWL}AnnotationProperty": "annotation_property", f"{OWL}NamedIndividual": "named_individual",
    f"{OWL}Restriction": "restriction",
}
PREDICATE_CONSTRUCTS = {
    f"{RDFS}label": "label", f"{SKOS}prefLabel": "label", f"{RDFS}comment": "comment",
    f"{SKOS}scopeNote": "scope_note", f"{SKOS}example": "example", f"{RDFS}isDefinedBy": "definition_link",
    f"{RDFS}subClassOf": "subclass_of", f"{RDFS}subPropertyOf": "subproperty_of",
    f"{OWL}equivalentClass": "equivalent_class", f"{OWL}equivalentProperty": "equivalent_property",
    f"{OWL}inverseOf": "inverse_of", f"{RDFS}domain": "named_domain", f"{RDFS}range": "named_range",
    f"{OWL}unionOf": "union", f"{OWL}intersectionOf": "intersection", f"{OWL}propertyChainAxiom": "property_chain",
    f"{OWL}disjointWith": "disjointness", f"{OWL}disjointUnionOf": "disjointness",
}
CARDINALITY_PREDICATES = {f"{OWL}{name}" for name in ("cardinality", "minCardinality", "maxCardinality", "qualifiedCardinality", "minQualifiedCardinality", "maxQualifiedCardinality")}
CHARACTERISTICS = {f"{OWL}{name}" for name in ("FunctionalProperty", "InverseFunctionalProperty", "TransitiveProperty", "SymmetricProperty", "AsymmetricProperty", "ReflexiveProperty", "IrreflexiveProperty")}
ONTOLOGY_METADATA_PREDICATES = {f"{OWL}imports", f"{OWL}versionIRI", f"{OWL}versionInfo"}
KNOWN_DATATYPES = {f"{XSD}{name}" for name in ("string", "boolean", "decimal", "integer", "int", "float", "double", "date", "dateTime", "time", "anyURI")}
SEMANTIC_CONSTRUCTS = frozenset({
    "rdfs_class", "owl_class", "rdf_property", "object_property", "datatype_property", "annotation_property",
    "named_individual", "restriction", "restriction_property", "label", "comment", "scope_note", "example",
    "definition_link", "subclass_of", "subproperty_of", "equivalent_class", "equivalent_property", "inverse_of",
    "named_domain", "named_range", "anonymous_class", "union", "intersection", "property_chain", "cardinality",
    "disjointness", "property_characteristic", "rdf_list_structure", "unknown_datatype", "missing_domain",
    "missing_range", "missing_label_language", "punning", "unknown_predicate", "unknown_rdf_type",
    "unknown_namespace", "forbidden_namespace", "missing_external_reference",
})
RELATION_FIELDS = {
    f"{RDFS}subClassOf": "subClassOf",
    f"{RDFS}subPropertyOf": "subPropertyOf",
    f"{OWL}equivalentClass": "equivalentClass",
    f"{OWL}equivalentProperty": "equivalentProperty",
    f"{OWL}disjointWith": "disjointWith",
    f"{OWL}inverseOf": "inverseOf",
}


@dataclass(frozen=True)
class ConstructOccurrence:
    construct: str
    resource: RdfTerm
    triple_ids: tuple[str, ...]
    scope_resource: RdfTerm | None = None

    @property
    def id(self) -> str:
        scope = self.scope_resource
        value = "|".join((
            self.construct,
            self.resource.kind,
            self.resource.value,
            scope.kind if scope else "",
            scope.value if scope else "",
            *self.triple_ids,
        ))
        return f"finding-{hashlib.sha256(value.encode()).hexdigest()}"


def detect_constructs(inventory: Inventory) -> tuple[ConstructOccurrence, ...]:
    occurrences: list[ConstructOccurrence] = []
    property_terms: set[RdfTerm] = set()
    type_triples: dict[RdfTerm, list[InventoryTriple]] = {}
    predicates = {triple.predicate.value for triple in inventory.triples}
    for triple in inventory.triples:
        if triple.predicate.value == f"{RDF}type" and triple.object.kind != "literal":
            type_triples.setdefault(triple.subject, []).append(triple)
            construct = TYPE_CONSTRUCTS.get(triple.object.value)
            if construct:
                occurrences.append(_occurrence(construct, triple.subject, triple.id))
                if construct in {"rdf_property", "object_property", "datatype_property"}:
                    property_terms.add(triple.subject)
            elif triple.object.value in CHARACTERISTICS:
                occurrences.append(_occurrence("property_characteristic", triple.subject, triple.id))
            else:
                occurrences.append(_occurrence("unknown_rdf_type", triple.subject, triple.id))
        construct = PREDICATE_CONSTRUCTS.get(triple.predicate.value)
        if construct:
            if construct in {"named_domain", "named_range"} and triple.object.kind == "blank_node":
                occurrences.append(_occurrence("anonymous_class", triple.subject, triple.id))
            else:
                occurrences.append(_occurrence(construct, triple.subject, triple.id))
        elif triple.predicate.value in CARDINALITY_PREDICATES:
            occurrences.append(_occurrence("cardinality", triple.subject, triple.id))
        elif triple.predicate.value in {f"{RDF}first", f"{RDF}rest"}:
            occurrences.append(_occurrence("rdf_list_structure", triple.subject, triple.id))
        elif triple.predicate.value == f"{OWL}onProperty":
            occurrences.append(_occurrence("restriction_property", triple.subject, triple.id))
        elif triple.predicate.value != f"{RDF}type" and triple.predicate.value not in ONTOLOGY_METADATA_PREDICATES:
            occurrences.append(_occurrence("unknown_predicate", triple.subject, triple.id))
        if triple.object.kind == "literal" and triple.object.datatype and triple.object.datatype not in KNOWN_DATATYPES:
            occurrences.append(_occurrence("unknown_datatype", triple.subject, triple.id))
        if triple.predicate.value in {f"{RDFS}label", f"{SKOS}prefLabel"} and triple.object.kind == "literal" and not triple.object.language:
            occurrences.append(_occurrence("missing_label_language", triple.subject, triple.id))
    for resource, triples in type_triples.items():
        categories = {TYPE_CONSTRUCTS.get(triple.object.value) for triple in triples}
        if len(categories & {"rdf_property", "object_property", "datatype_property", "annotation_property", "rdf_class", "rdfs_class", "owl_class", "named_individual"}) > 1:
            occurrences.append(_occurrence("punning", resource, *(triple.id for triple in triples)))
    for property_term in property_terms:
        if not any(t.subject == property_term and t.predicate.value == f"{RDFS}domain" for t in inventory.triples):
            occurrences.append(_occurrence("missing_domain", property_term))
        if not any(t.subject == property_term and t.predicate.value == f"{RDFS}range" for t in inventory.triples):
            occurrences.append(_occurrence("missing_range", property_term))
    return _inherit_blank_node_scope(occurrences, inventory)


def _occurrence(construct: str, resource: RdfTerm, *triple_ids: str) -> ConstructOccurrence:
    return ConstructOccurrence(construct, resource, tuple(sorted(triple_ids)))


def _inherit_blank_node_scope(
    occurrences: list[ConstructOccurrence], inventory: Inventory
) -> tuple[ConstructOccurrence, ...]:
    """Attach anonymous constructs to every URI resource that structurally contains them."""
    incoming: dict[RdfTerm, list[InventoryTriple]] = {}
    for triple in inventory.triples:
        if triple.object.kind == "blank_node":
            incoming.setdefault(triple.object, []).append(triple)

    inherited: list[ConstructOccurrence] = []
    for occurrence in occurrences:
        if occurrence.resource.kind != "blank_node":
            inherited.append(occurrence)
            continue
        anchors = _blank_node_anchors(occurrence.resource, incoming)
        if not anchors:
            inherited.append(occurrence)
            continue
        for anchor, path_ids in anchors.items():
            inherited.append(
                ConstructOccurrence(
                    occurrence.construct,
                    occurrence.resource,
                    tuple(sorted(set((*occurrence.triple_ids, *path_ids)))),
                    anchor,
                )
            )
    return tuple(sorted(set(inherited), key=lambda occurrence: occurrence.id))


def _blank_node_anchors(
    node: RdfTerm, incoming: dict[RdfTerm, list[InventoryTriple]]
) -> dict[RdfTerm, set[str]]:
    anchors: dict[RdfTerm, set[str]] = {}

    def visit(current: RdfTerm, path_ids: set[str], visited: set[RdfTerm]) -> None:
        for triple in incoming.get(current, []):
            next_ids = path_ids | {triple.id}
            if triple.subject.kind == "uri":
                anchors.setdefault(triple.subject, set()).update(next_ids)
            elif triple.subject not in visited:
                visit(triple.subject, next_ids, visited | {triple.subject})

    visit(node, set(), {node})
    return anchors
