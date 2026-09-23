# Configuration Guide

Run `ontome-importer init` before editing these files. It creates the audit and generation manifests plus the profile templates in a new workspace. This page explains the fields that the import team completes after reading the first audit report.

The standard `ontome-importer assist` workflow uses an XLSX workbook as the human editing surface. `assist compile` converts checked decisions into mapping profile 7.0 and namespace registry 1.0 described below; generation never reads XLSX directly. `assist check` is read-only; `assist refresh`, and the optional `--workbook` arguments of `generate` and `validate`, update only derived diagnostics in the workbook. The manifest identifies inputs and target metadata, the mapping defines transformations, and the registry provides external namespace data. Do not use the workbook, manifest, or registry to hide ontology-specific logic in the application code.

In workbook 1.7, edit only `RULES`, `EXTERNAL_REFERENCE_RULES`, `EXTERNAL_EXCEPTIONS`, `EDITORIAL_EXCEPTIONS`, `DECISIONS`, and `NAMESPACE_REGISTRY`. `CLASSES`, `PROPERTIES`, `EXTERNAL_USAGE`, `BLOCKERS`, `METADATA`, and `VALIDATION` are derived views and never compile into YAML.

`assist export` can receive an optional RDF catalog. A catalog is only authoritative for external identifiers when the caller explicitly supplies an identifier predicate and the predicate has exactly one literal value for each catalog URI. Otherwise it is not used to create mappings.

## Audit Profiles

Audit uses manifest 1.1, capability profile 1.1, namespace registry 1.0, and mapping profile 1.1. Scope selectors are ORed; conditions in a selector are ANDed. Mapping 1.1 is audit-only and its generic map targets never authorize XML generation.

`exclude` requires a human-readable `reason`. `configure` requires `decision_needed`. Unknown constructions are blocked by default.

## Generation Profiles

Generation uses manifest 1.0, capability profile 1.0, namespace registry 1.0, and mapping profile 7.0. The target namespace requires at least one localized label.

## Decision Journal

Mapping profile 7.0 contains a `decisions` journal. Each entry records an explicit human decision for one RDF resource and construct: its action, approval status, rationale, approver, approval date, and durable decision reference. An entry can also name the mapping rule or editorial exception it governs. The `DECISIONS` workbook sheet is the editable source; `assist compile` validates and publishes it with the mapping profile. Audit findings link to a matching decision through `decision_id` and `decision_status`.

Each mapping 7.0 `map` rule has a typed target:

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

An identifier uses an explicit strategy: `uri_suffix` with `strip_prefix`, `literal_predicate` with one literal predicate value, or `regex_capture` with a full URI pattern and exactly one capture group. There is no core default. A configured identifier predicate is consumed by generation; unconfigured predicates remain blocked by the audit.

Class rules may configure `subClassOf`, `equivalentClass`, and `disjointWith`. Property rules require `domain_range` and may configure `subPropertyOf`, `equivalentProperty`, and `inverseOf`. Text assertions are emitted only through explicit `text_fields`; `rdfs:comment` has no implicit XML destination. Parent relations, inverse labels, and quantifiers remain blocked because no generic RDF transformation contract is defined for them.

```yaml
text_fields:
  - field: contextNote
    predicates:
      - http://www.w3.org/2000/01/rdf-schema#comment
```

Exact URI-to-OntoME mappings remain available for exceptions:

```yaml
external_references:
  - uri: https://example.org/external/Term
    reference_namespace: 123
    identifier: T1
```

For mechanically derivable identifiers, use an external reference rule instead of one exception per URI:

```yaml
external_reference_rules:
  - id: external-suffix
    uri_prefix: https://example.org/external/
    reference_namespace: 123
    identifier_extraction:
      source: uri_suffix
```

`regex_capture` is also available when a full URI pattern with exactly one capture group is required. Exact exceptions take precedence over rules; otherwise the most specific matching URI prefix is used. The namespace must exist in the registry. `active` and explicitly configured `deprecated` namespaces are allowed; `forbidden` namespaces block generation and validation.

This rule also applies to RDF/RDFS/OWL/SKOS/XSD terms used as a domain, range or relation target. Add an exception or a profile rule with its OntoME namespace ID and extraction policy; the importer contains no built-in datatype or vocabulary mapping.

`EDITORIAL_EXCEPTIONS` is deliberately narrower: it may provide only a missing `hasDomain` or `hasRange`, never replace an RDF assertion that is present. Each exception requires a rationale, approval, date, and decision reference.
