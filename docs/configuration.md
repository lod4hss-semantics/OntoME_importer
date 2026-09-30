# Configuration Guide

Run `ontome-importer init` before editing these files. It creates the audit and generation manifests plus the profile templates in a new workspace. This page explains the fields that the import team completes after reading the first audit report.

The standard workflow uses `ontome-importer review`, a local terminal session. It records human decisions, then `review finalize` writes the internal transformation profile and namespace registry used by generation. Generation never reads an interactive session directly. The manifest identifies inputs and target metadata, the transformation profile defines mechanical serialization, and the registry provides external namespace data.

The review session is the human decision surface. Its queue and its compiled profiles are separate: reports are read-only evidence and only confirmed terminal decisions are compiled.

The review downloads an RDF catalog only after the user confirms an OntoME dependency selected by URI and version. A catalog is authoritative only when it supplies exactly one `skos:notation` value for a referenced URI.

## Audit Profiles

Audit uses manifest 1.1, capability profile 1.1, namespace registry 1.0, and mapping profile 1.1. Scope selectors are ORed; conditions in a selector are ANDed. Mapping 1.1 is audit-only and its generic map targets never authorize XML generation.

`exclude` requires a human-readable `reason`. `configure` requires `decision_needed`. Unknown constructions are blocked by default.

## Generation Profiles

New workspaces use audit manifest 1.2 and generation manifest 1.1, with the existing capability profiles, namespace registry 1.1, and an internal transformation profile 7.0 compiled by the review. The target namespace requires an OntoME ID, the RDF URI and a localized label. No target export or target API call is required. Earlier manifests remain readable for existing fixtures.

## Decision Journal

The review session records decisions about resources, individual RDF assertions and their grouped coverage, external references and editorial exceptions. Each omission records its reason, reviewer, timestamp and source triple IDs in the compiled mapping and audit. `review check` and `review finalize` run the generation resolver and XSD serializer in memory; `finalize` only writes the internal profiles when that preflight succeeds. The decision journal remains in the session JSON.

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

For a published OntoME dependency, select the namespace by URI and explicit version from the versioned OntoME namespace catalog. Download its RDF/XML export with `ontome-importer namespaces fetch`, then use the catalog `skos:notation` values to prefill exact references. Do not derive an OntoME term identifier from an RDF URI without this catalog verification. The namespace registry 1.1 records the selected `uri`, `version`, and `ontome_namespace_id`; `active` and explicitly configured `deprecated` namespaces are allowed, while `forbidden` namespaces block generation and validation.

This rule also applies to RDF/RDFS/OWL/SKOS/XSD terms actually retained as a domain, range or relation target. `review references` requests a catalog only for retained external relations; a selected RDF/XML catalog must contain the exact referenced URI with one `skos:notation`. Its instance, namespace ID and version are declared explicitly. An assertion omitted with a reviewed reason needs no OntoME catalog. The importer contains no built-in datatype or vocabulary mapping.

`EDITORIAL_EXCEPTIONS` is deliberately narrower: it may provide only a missing `hasDomain` or `hasRange`, never replace an RDF assertion that is present. Each exception requires a rationale, approval, date, and decision reference.
