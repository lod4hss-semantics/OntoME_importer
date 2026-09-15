# Phase 0 Contracts

Phase 0 freezes configuration and report contracts before implementation of RDF loading or XML generation.

## Authority Boundaries

The core detects standard RDF, RDFS, OWL and SKOS constructs. It contains no source ontology URI, term, datatype correspondence or external namespace identifier. The OntoME XSD defines XML validity. The capability profile defines the supported subset of that XSD. The mapping profile provides every source-to-target decision.

## Versioned Artifacts

- `resources/xsd/` contains the retrieved official XSD and source metadata. The checksum must match before it is used.
- `profiles/capabilities/` contains a capability profile tied to one XSD checksum.
- `schemas/config/` contains JSON Schemas for human-authored YAML configuration.
- `schemas/reports/` contains JSON Schemas for machine-readable outputs.

The XSD public URL does not expose a version number. Its local version is its retrieval date; its SHA-256 is the immutable identity. A changed XSD requires a new local file, metadata record and capability profile. It must not overwrite a previous artifact.

## Strict Decisions

`mapped` means that a complete, valid target representation exists. `configured` means a rule exists but required configured data is absent. `excluded` requires a documented reason. `blocked` means no valid rule applies. `invalid` means source or configuration data is contradictory.

Strict mode is always `true` in format version 1.0. In-scope `configured`, `blocked` and `invalid` entries prevent generation. Out-of-scope assertions remain in the inventory and are not treated as exclusions.

## Configuration Policy

The manifest records the source file used for execution separately from its optional documentary source URI. Mapping scope is explicit through resource selectors. No namespace is included by default. A missing language, datatype, domain, range, anonymous structure or external namespace requires a mapping decision; it is never fabricated.

## Verification

Run `python tools/validate_phase0.py`. It checks XSD integrity and compilation, valid YAML profiles, the invalid-exclusion fixture, and report-schema fixtures.
