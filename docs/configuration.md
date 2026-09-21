# Configuration Guide

Run `ontome-importer init` before editing these files. It creates the audit and generation manifests plus the profile templates in a new workspace. This page explains the fields that the import team completes after reading the first audit report.

The standard `ontome-importer assist` workflow uses an XLSX workbook as the human editing surface. `assist compile` converts checked decisions into the same mapping profile 2.0 and namespace registry 1.0 described below; generation never reads XLSX directly. `assist check` is read-only; `assist refresh`, and the optional `--workbook` arguments of `generate` and `validate`, update only derived diagnostics in the workbook.

`assist export` can receive an optional RDF catalog. A catalog is only authoritative for external identifiers when the caller explicitly supplies an identifier predicate and the predicate has exactly one literal value for each catalog URI. Otherwise it is not used to create mappings.

## Audit Profiles

Audit uses manifest 1.1, capability profile 1.1, namespace registry 1.0, and mapping profile 1.1. Scope selectors are ORed; conditions in a selector are ANDed. Mapping 1.1 is audit-only and its generic map targets never authorize XML generation.

`exclude` requires a human-readable `reason`. `configure` requires `decision_needed`. Unknown constructions are blocked by default.

## Generation Profiles

Generation uses manifest 1.0, capability profile 1.0, namespace registry 1.0, and mapping profile 2.0. The target namespace requires at least one localized label.

Each mapping 2.0 `map` rule has a typed target:

```yaml
target:
  entity_kind: class # or property
  property_kind: object # required only for properties: object, datatype, rdf
  identifier_in_namespace:
    source: uri_suffix
    strip_prefix: https://example.org/source/
  identifier_in_uri: source_uri # optional
  label_predicates:
    - http://www.w3.org/2000/01/rdf-schema#label
```

An identifier can only be extracted with the explicit `uri_suffix` and `strip_prefix` policy. There is no core default.

Class rules may configure `subClassOf` and `equivalentClass`. Property rules require `domain_range` and may configure `subPropertyOf`, `equivalentProperty`, and `inverseOf`. Text assertions are emitted only through explicit `text_fields`; `rdfs:comment` has no implicit XML destination.

```yaml
text_fields:
  - field: contextNote
    predicates:
      - http://www.w3.org/2000/01/rdf-schema#comment
```

External references are exact URI-to-OntoME mappings:

```yaml
external_references:
  - uri: https://example.org/external/Term
    reference_namespace: 123
    identifier: T1
```

The namespace must exist in the registry. `active` and explicitly configured `deprecated` namespaces are allowed; `forbidden` namespaces block generation and validation.

This rule also applies to RDF/RDFS/OWL/SKOS/XSD terms used as a domain, range or relation target. Add their exact URI, OntoME namespace ID and OntoME identifier to `external_references`; the importer contains no built-in datatype or vocabulary mapping.
