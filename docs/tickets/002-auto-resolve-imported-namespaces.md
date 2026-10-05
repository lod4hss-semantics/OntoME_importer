# Ticket: Resolve imported OntoME namespaces automatically

## Problem

`review references` currently asks for an external namespace URI, an OntoME
namespace ID, a version, and optionally an RDF/XML catalog for every external
term.

This is unnecessary when the source ontology declares the external ontology in
`owl:imports` and the bundled namespace catalog already maps that imported
namespace and version to an OntoME namespace ID.

For CRMdig 5.0, the source declares:

```xml
<owl:imports rdf:resource="http://www.cidoc-crm.org/cidoc-crm/owl/7.1.3/"/>
```

The bundled catalog resolves:

```text
http://www.cidoc-crm.org/cidoc-crm/ + 7.1.3 -> 188
```

A source reference such as:

```text
http://www.cidoc-crm.org/cidoc-crm/E11_Modification
```

must therefore be serialized automatically as:

```xml
<subClassOf referenceNamespace="188">E11</subClassOf>
```

No interactive input, catalog download, or `skos:notation` lookup is required.

## Expected Behavior

1. Read `owl:imports` from the source ontology.
2. Normalize each imported ontology URI to its external RDF namespace URI and version.
3. Resolve the OntoME namespace ID using the bundled JSON catalog.
4. Register the resolved external namespace automatically.
5. Resolve every external URI belonging to that namespace.
6. Derive its OntoME term identifier from the source URI using the historical identifier convention:
   - `E11_Modification` -> `E11`
   - `P94_has_created` -> `P94`
   - `O24_measured` -> `O24`
7. Generate `referenceNamespace="<resolved OntoME namespace ID>"` without prompting the user.

## User Interaction

`review references` must not ask for URI, version, namespace ID, RDF/XML
export path, or catalog download when an exact `owl:imports` declaration
resolves through the bundled catalog.

It must ask for a decision only when:

- no matching `owl:imports` declaration exists;
- an import cannot be mapped to the bundled catalog;
- several imported namespaces could match an external URI;
- the term identifier cannot be derived unambiguously from the source URI.

## Historical Behavior

The legacy `graph_to_ontome.ipynb`:

- selected the OntoME namespace ID from a URI/version JSON table;
- extracted the identifier from the RDF URI;
- wrote the identifier and `referenceNamespace` directly in XML.

It did not require an OntoME RDF export or a per-term `skos:notation` validation.

## Acceptance Criteria

- CRMdig 5.0 resolves CIDOC CRM 7.1.3 automatically to OntoME namespace `188`.
- CRMdig 5.0 resolves CRMsci 3.2 automatically when present in the bundled catalog.
- All CIDOC CRM terms used by CRMdig generate their identifiers from source URIs.
- No `review references` prompts occur for these resolvable imports.
- The generated namespace registry records URI, version, OntoME namespace ID, and source provenance.
- Unresolvable or ambiguous external namespaces remain explicit review blockers.
- Tests cover CIDOC CRM and CRMsci imports, automatic identifier extraction, and unresolved imports.
