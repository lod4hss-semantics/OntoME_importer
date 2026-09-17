# Phase 5 Validation

This is a technical reference. For the operational workflow, use the [User Guide](user-guide.md).

Validate the generated XML and its associated reports before publication:

```bash
ontome-importer validate \
  --manifest config/generation.yaml \
  --xml build/import/import.xml \
  --trace build/import/generation-trace.json \
  --audit build/import/generation-audit.json \
  --output build/import/validation.json
```

The command verifies XML well-formedness and the pinned XSD, source and XSD checksums, XML/trace correspondence, source triple provenance, local and external references, identifier and property constraints, generation audit consistency, and deterministic reconstruction from the configured source.

It returns `0` for a valid result, `3` for validation failures (and still writes `validation.json`), and `2` when required manifest, profile, source, XSD, or output prerequisites cannot be loaded.

Archive the XML, trace, generation audit, validation report, manifest, profiles, source identity, and selected XSD together.
