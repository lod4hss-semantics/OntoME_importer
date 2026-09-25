# Phase 0 Contracts

Phase 0 defines the execution contract for the importer. It applies to every RDF source; source ontology conventions belong only in profiles.

## Authority Boundaries

The core detects standard RDF, RDFS, OWL and SKOS constructs. It contains no source ontology URI, term, datatype correspondence or external namespace identifier. The OntoME XSD defines XML validity. The capability profile defines the subset that the current writer can serialize and validate. The mapping profile provides every RDF-to-XML transformation and approved decision journal. The namespace registry contains externally supplied OntoME namespace data. Editorial exceptions may complete only a missing property domain or range; they must never hide or replace an RDF assertion.

## Versioned Artifacts

- `resources/xsd/` contains the retrieved official XSD and source metadata. The checksum must match before it is used.
- `profiles/capabilities/` contains a capability profile tied to one XSD checksum.
- `schemas/config/` contains JSON Schemas for human-authored YAML configuration.
- `schemas/reports/` contains JSON Schemas for machine-readable outputs.

The XSD public URL does not expose a version number. Its local version is its retrieval date; its SHA-256 is the immutable identity. A changed XSD requires a new local file, metadata record and capability profile. It must not overwrite a previous artifact.

## Strict Decisions

`status` is the operational result: `mapped` means that a complete target representation exists; `configured` means a rule still needs a configuration decision; `excluded` requires a documented reason; `blocked` means generation cannot continue; `invalid` means source or configuration data is contradictory.

Every in-scope finding also has a `category`, which records the cause independently from the operational result: `mechanical_transformation`, `intentional_exclusion`, `configuration_required`, `missing_profile_rule`, `missing_external_data`, `forbidden_external_namespace`, `ambiguous_source_data`, `incomplete_source_data`, `invalid_source_data`, `unsupported_rdf_construct`, or `invalid_profile`.

Strict mode is always `true`. In-scope `configured`, `blocked` and `invalid` entries prevent generation. Out-of-scope assertions remain in the inventory and are not treated as exclusions.

## Configuration Policy

The manifest records the source file used for execution separately from its optional documentary source URI. Transformation scope is explicit through resource selectors. No namespace is included by default. The internal transformation profile defines resource selection and serialization only. The namespace registry provides URI, version, OntoME namespace ID, status, and provenance. The local terminal review is the human decision surface; generation reads only its finalized internal profiles.

No value is fabricated. A missing language, datatype, domain, range, external namespace datum, or mapping rule blocks or requires configuration. The core does not infer OWL semantics, parse prose, or derive cross-vocabulary semantic equivalences. An in-scope RDF assertion is either transformed, explicitly excluded with a reason, or reported as blocking.

## Generation Invariants

- A successful generation is validated against the selected XSD and is byte-deterministic for identical inputs.
- Every XML leaf has trace provenance from RDF, configuration, or an approved editorial exception.
- Every external XML reference has a root namespace declaration and is permitted by the registry and mapping.
- Every local XML reference names a generated local identifier.
- A capability profile cannot advertise class or property fields that the XML writer does not serialize.

## Verification

Run `python tools/validate_phase0.py` and `python tools/validate_contracts.py`. They check XSD integrity and compilation, valid YAML profiles, the invalid-exclusion fixture, and report-schema fixtures. The application test suite verifies audit categorization, capability/writer alignment, deterministic generation, trace completeness, and independent bundle validation.
