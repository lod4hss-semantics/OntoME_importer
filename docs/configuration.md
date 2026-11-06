# Configuration Guide

Run `ontome-importer init` before editing these files. It creates the audit and generation manifests plus the profile templates in a new workspace. This page explains the fields that the import team completes after reading the first audit report.

The standard workflow uses `ontome-importer review`, a local terminal session. It records human decisions, then `review finalize` writes the internal transformation profile and namespace registry used by generation. Generation never reads an interactive session directly. The manifest identifies inputs and the RDF namespace URI to import, the transformation profile defines mechanical serialization, and the registry provides external namespace data.

The review session is the human decision surface. Its queue and its compiled profiles are separate: reports are read-only evidence and only confirmed terminal decisions are compiled.

The review downloads an RDF catalog only after the user confirms an OntoME dependency selected by URI and version. A catalog is authoritative only when it supplies exactly one `skos:notation` value for a referenced URI.

## Audit Profiles

New workspaces use audit manifest 1.3, capability profile 1.1, namespace registry 1.1, and mapping profile 1.1. Scope selectors are ORed; conditions in a selector are ANDed. Mapping 1.1 is audit-only and its generic map targets never authorize XML generation.

`exclude` requires a human-readable `reason`. `configure` requires `decision_needed`. Unknown constructions are blocked by default.

## Generation Profiles

New workspaces use generation manifest 1.2, with the existing capability profiles, namespace registry 1.1, and an internal transformation profile 7.0 compiled by the review. The target records the source RDF URI, localized labels and an optional version. By default the XML omits `namespaceURI`: the active OntoME project's root namespace supplies the URI during import. If an explicit, different URI is needed for the imported version, pass `--import-namespace-uri` to `init`; this records `target.import_namespace_uri` and writes the XML `namespaceURI` element. `--target-namespace-uri` separately selects the source RDF ontology URI when it cannot be inferred. No target export or target API call is required. Earlier manifests containing a target namespace ID remain readable as legacy metadata.

At initialization, the numeric suffix of the ontology's `owl:versionIRI` (for example `/3.2/` or `/v3.2/`) becomes `target.version` and the localized `owl:versionInfo` text becomes `target.descriptions`, exported as the namespace's `<description>` in OntoME XML. An untagged versionInfo uses the target label language. If no versionIRI is present, version remains absent unless `--target-version` is supplied; ambiguous or non-numeric versionIRIs require an explicit override. Existing workspaces can update the generation manifest's `target.version` and `target.descriptions` before regenerating.

The imported version's namespace `standardLabel` is generated as `<base label> version <version>` (for example, `CRMsci version 3.2`). If the base label already contains that version number, it is left unchanged; without a version, the base label is kept. The XML `version` field stays numeric, and `description` still contains `owl:versionInfo`. The manifest retains the base label so that future version imports can reuse it.

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

Terminal review compiles a `regex_capture` for local CIDOC-style identifiers such as `S10_Material_Substantial` and `O37_expressed_the_observed_as_observable_proposition`: OntoME receives the code (`S10` or `O37`) in `identifierInNamespace` and retains the full URI in `identifierInURI`. The same code is used for all local class and property references. Other URI suffixes keep the existing `uri_suffix` mapping.

Class rules may configure `subClassOf`, `equivalentClass`, and `disjointWith`. Property rules require `domain_range` and may configure `subPropertyOf`, `equivalentProperty`, and `inverseOf`. Text assertions are emitted only through explicit `text_fields` or `comment_sections`; `rdfs:comment` has no implicit XML destination. Reviewed inverse property pairs are represented by the retained property's `inverseLabel`; the inverse property's other fields are not exported. Parent relations remain unsupported without an explicit mapping.

```yaml
text_fields:
  - field: contextNote
    predicates:
      - http://www.w3.org/2000/01/rdf-schema#comment
```

For CIDOC CRM editorial comments, `review assertions` offers `[d]` when all comments in the group can be parsed. Approval compiles an opt-in rule on each retained class or property:

```yaml
comment_sections:
  predicate: http://www.w3.org/2000/01/rdf-schema#comment
  format: cidoc_crm_ea
```

`Scope note:` becomes `scopeNote`; the `- ` entries under `Examples:` are combined as an HTML `<ul><li>…</li></ul>` list in one `example` text element per source comment. The XML escapes the HTML markup as text, which OntoME's TinyMCE rich-text field interprets; individual example text is HTML-escaped before insertion. `Full path:` and `In First Order Logic:` are omitted with the reviewer's recorded rationale. On retained properties, the E-A notation `(range min,max:domain min,max)` becomes the XSD's UML-end quantifier fields: `rangeInstancesMin/MaxQuantifier` from the first pair, `domainInstancesMin/MaxQuantifier` from the second. For example, `(1,1:0,n)` means one range instance per domain instance, and zero to n domain instances per range instance. Comments with missing or ambiguous sections require individual review. Only the retained property's comment is processed; the inverse contributes its label only. All resulting XML elements trace back to the source comment triple. In `review inverses`, `[a]` retains the first property of every remaining pair without changing decisions already recorded.

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
