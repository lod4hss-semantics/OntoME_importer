# Semantic Policy

This policy defines the RDF assertions that OntoME Importer can represent. The tool performs no RDF Schema or OWL inference and never silently drops an in-scope assertion. A published resource does not imply that all of its assertions are approved for omission: each omission requires a recorded decision with a reason, reviewer and scope.

## Statuses

| Status | Meaning |
| --- | --- |
| Exportable | An explicit mapping can serialize the assertion to OntoME XML and trace it to RDF triples. |
| Configurable | An external-reference exception or a declared resolution rule is required before generation. |
| Blocked | The assertion has no supported XML representation in this version; it requires an explicit omit decision or a supported transformation. |
| Excluded | A reviewer chose to omit this assertion; its provenance and rationale remain in the generation audit. |
| Internal | A structural RDF list or restriction component is reported as part of a blocked construction. |
| Out of scope | The assertion is recorded as an observation and does not affect this import. |

## Exportable Assertions

| RDF assertion | Required mapping |
| --- | --- |
| `rdfs:Class`, `owl:Class` | `entity_kind: class` |
| `rdf:Property`, `owl:ObjectProperty`, `owl:DatatypeProperty` | Matching property kind |
| `rdfs:label`, `skos:prefLabel` | `label_predicates`, with a language-tagged literal |
| `rdfs:comment`, `skos:scopeNote`, `skos:example` | Explicit `text_fields` destination |
| `rdfs:subClassOf`, `rdfs:subPropertyOf`, `owl:equivalentClass`, `owl:equivalentProperty`, `owl:inverseOf`, `owl:disjointWith` | Explicit `relations` predicate |
| `rdfs:domain`, `rdfs:range` | Property `domain_range`, exactly one named URI each |

Every non-local relation target, including RDF/RDFS/OWL/XSD terms, requires an exact `external_references` exception or an `external_reference_rules` rule that resolves its OntoME namespace and identifier. These mappings are configuration, not Python code.

## Explicitly Blocked Assertions

`rdfs:isDefinedBy`, annotation properties, named individuals, restrictions, cardinalities, unions, intersections, property chains, property characteristics, anonymous domain/range classes, RDF list structures, `owl:onProperty`, punning, unsupported datatypes, and unknown RDF types or predicates require a decision; the review can omit an unsupported assertion without excluding the entire resource, but cannot invent mandatory target values. `parentClassOf`, `parentPropertyOf`, `inverseLabel`, and quantifiers remain unavailable even though the XSD permits them.

The OntoME XSD may contain fields for some of these concepts. They remain blocked until a versioned mapping contract, resolver implementation, XML trace, and regression tests are added together.

## No Inference

The importer does not infer superclass membership, inherited domain/range, equivalence, inverse assertions, OWL restrictions, or datatype conversions. Only explicit RDF triples are considered.
