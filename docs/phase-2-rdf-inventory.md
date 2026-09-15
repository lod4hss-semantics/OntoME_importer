# Phase 2 RDF Inventory

Phase 2 loads simple RDF graphs and creates a generic inventory. It does not detect OWL constructs, map source terms, produce XML or add a public CLI command.

## Supported Formats

The loader requires an explicit format identifier:

- `turtle` for Turtle;
- `rdfxml` for RDF/XML;
- `ntriples` for N-Triples.

TriG, N-Quads and other dataset formats are rejected. Named-graph provenance requires a later inventory model revision.

## Inventory Contract

`schemas/reports/inventory-1.1.schema.json` is the contract for inventories created by this phase. It records the source file, source format and SHA-256 of the bytes read. Every triple has a content-derived identifier and source-file provenance. Every URI or blank node appearing as a subject or object is indexed as one resource.

Types are derived from `rdf:type` triples without removing those triples. Literals retain their value, language or datatype. Unknown predicates and types are retained as ordinary RDF assertions.

## Determinism

Triples and resources are ordered canonically. Blank nodes receive internal `b0`, `b1` identifiers derived from their graph context, rather than RDFLib parser identifiers. This is deterministic for the supported fixtures and repeated loading of the same source; it is not a universal RDF dataset canonicalization algorithm.
