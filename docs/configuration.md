# Configuration Guide

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
