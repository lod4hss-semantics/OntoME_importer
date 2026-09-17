# Phase 4 Resolution And XML Generation

This is a technical reference. For the operational workflow, use the [User Guide](user-guide.md).

`ontome-importer generate --manifest MANIFEST --output-dir DIRECTORY` loads the complete version 1.0 manifest and capability contracts with a mapping profile 2.0. It verifies the source checksum and XSD checksum, reruns the RDF audit, resolves mappings, validates the XML against the pinned XSD, then writes `import.xml`, `generation-trace.json`, and `generation-audit.json`.

Mapping profile 2.0 rules are typed as `class` or `property`; properties require `object`, `datatype`, or `rdf`. A local identifier can only be derived by the configured `uri_suffix` policy and its explicit `strip_prefix`. A generic mapping target is not a generation contract.

References to local generated resources use their resolved identifier. Every external URI must appear exactly in `external_references`, with its OntoME namespace ID and identifier. Forbidden namespaces block. Deprecated namespaces are generated only when explicitly declared and are recorded in the generation audit.

Text assertions are emitted only when their source predicates are configured in `text_fields`. In particular, `rdfs:comment` has no implicit XML target. Labels and configured text values require a language.

The command returns `0` after successful generation, `2` for configuration/source/XSD errors, and `3` for audit, resolution, or XML generation blocks. A blocked run writes `generation-audit.json` but never writes `import.xml`.
