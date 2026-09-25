import pytest

from ontome_importer.external_references import ExternalReferenceError, resolve_external_reference, validate_external_reference_configuration


REGISTRY = {"format_version": "1.1", "namespaces": [{"uri": "https://example.org/external/", "version": None, "ontome_namespace_id": 123, "status": "active", "source": "test"}]}


def _mapping(rules, references=()):
    return {"format_version": "7.0", "scope": {"resource_selectors": [{"uri_prefix": "https://example.org/source/"}]}, "rules": [], "external_references": list(references), "external_reference_rules": rules, "editorial_exceptions": [], "decisions": []}


def test_external_reference_rule_extracts_uri_suffix_and_exact_exception_wins():
    mapping = _mapping([{"id": "external", "uri_prefix": "https://example.org/external/", "reference_namespace": 123, "identifier_extraction": {"source": "uri_suffix"}}], [{"uri": "https://example.org/external/special", "reference_namespace": 123, "identifier": "override"}])
    assert resolve_external_reference("https://example.org/external/Term", mapping, REGISTRY).identifier == "Term"
    resolved = resolve_external_reference("https://example.org/external/special", mapping, REGISTRY)
    assert (resolved.identifier, resolved.origin, resolved.rule_id) == ("override", "external_exception", None)


def test_external_reference_rule_extracts_a_configured_regex_capture():
    mapping = _mapping([{"id": "external", "uri_prefix": "https://example.org/external/", "reference_namespace": 123, "identifier_extraction": {"source": "regex_capture", "pattern": r"https://example\.org/external/([A-Z][0-9]+)_.*"}}])
    resolved = resolve_external_reference("https://example.org/external/A12_descriptive_name", mapping, REGISTRY)
    assert (resolved.identifier, resolved.origin, resolved.rule_id) == ("A12", "external_rule", "external")


def test_external_reference_rule_requires_one_capture_group_and_a_matching_uri():
    invalid = _mapping([{"id": "external", "uri_prefix": "https://example.org/external/", "reference_namespace": 123, "identifier_extraction": {"source": "regex_capture", "pattern": r"https://example\.org/external/.*"}}])
    with pytest.raises(ExternalReferenceError, match="exactly one"):
        validate_external_reference_configuration(invalid, REGISTRY)
    mapping = _mapping([{"id": "external", "uri_prefix": "https://example.org/external/", "reference_namespace": 123, "identifier_extraction": {"source": "regex_capture", "pattern": r"https://example\.org/external/([A-Z][0-9]+)_.*"}}])
    with pytest.raises(ExternalReferenceError) as error:
        resolve_external_reference("https://example.org/external/not-matching", mapping, REGISTRY)
    assert error.value.category == "invalid_source_data"
