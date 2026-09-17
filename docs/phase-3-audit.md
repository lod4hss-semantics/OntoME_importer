# Phase 3 RDF Audit

This is a technical reference. For the operational workflow, use the [User Guide](user-guide.md).

`ontome-importer audit --manifest MANIFEST --output-dir DIRECTORY` loads an RDF source, validates its versioned profiles, and writes `inventory.json`, `audit.json`, and `audit.md`.

The audit is generic. It detects RDF, RDFS, OWL and SKOS constructs, preserves unknown predicates and RDF types, and links each finding to stable inventory triples. Capability and mapping profiles determine whether a finding is mapped, configured, excluded, blocked, or invalid.

Scope selectors are ORed; fields inside one selector are ANDed. More than one matching mapping rule is invalid. Out-of-scope observations remain visible in `audit.json` but do not block strict generation. The command itself succeeds after a completed audit even when its report is blocked; generation will enforce strict blocking in phase 4.

Anonymous RDF structures inherit the scope of every URI resource that structurally reaches them. Their report entry preserves the blank node in `resource` and records the URI anchor in `scope_resource`.

A generic `map` target is reported as `configured`, not `mapped`: phase 3 cannot claim XML representability until a typed generation mapping validates it. Namespaces registered as `forbidden` always block; active and deprecated registered namespaces are recognized, while unregistered namespaces block.

The capability profile XSD is resolved from the versioned project root and its SHA-256 is checked before RDF loading. Audit examples use deterministic N-Triples-style terms and preserve literal language and datatype information.
