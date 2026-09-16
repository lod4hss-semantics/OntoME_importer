# Operational Workflow

1. Prepare a local RDF source and versioned manifest, capability profile, namespace registry, and mapping profile.
2. Run `ontome-importer audit` with the phase 3 manifest. Review `audit.json` and resolve, configure, or explicitly exclude every in-scope block.
3. Run `ontome-importer generate` with a manifest 1.0 and mapping profile 2.0. A successful run writes `import.xml`, `generation-trace.json`, and `generation-audit.json`.
4. Run `ontome-importer validate` on that exact bundle. Only a report with `valid: true` is ready for publication.
5. Archive the source identity, manifest, profiles, XSD, XML, trace, generation audit, and validation report as one bundle.

The configuration contracts are versioned JSON Schemas under `schemas/config/`. Mapping 1.1 is audit-only. Mapping 2.0 is required for generation and explicitly configures entity kind, identifiers, labels, relations, documentation fields, domain/range, and external references.

The generator refuses to overwrite generated artifacts in an output directory. Use a new output directory for every release candidate.
