import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from ontome_importer.audit import audit_inventory
from ontome_importer.constructs import RDFS, SEMANTIC_CONSTRUCTS
from ontome_importer.loader import load_inventory
from ontome_importer.profiles import ProfileError, load_audit_profiles, load_generation_profiles, validate_generation_mapping, verify_capability_xsd


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/phase3"


def test_audit_reports_supported_and_blocked_constructs():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle")
    report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
    statuses = {finding["construct"]: finding["status"] for finding in report.findings}
    assert statuses["owl_class"] == "configured"
    assert statuses["anonymous_class"] == "blocked"
    assert statuses["unknown_predicate"] == "blocked"
    assert statuses["unknown_namespace"] == "blocked"
    assert report.to_dict()["strict_ok"] is False


def test_anonymous_constructs_inherit_the_scope_of_their_uri_parent():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle")
    report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
    unions = [finding for finding in report.findings if finding["construct"] == "union"]
    assert len(unions) == 1
    assert unions[0]["status"] == "blocked"
    assert unions[0]["resource"]["kind"] == "blank_node"
    assert unions[0]["scope_resource"] == {"kind": "uri", "value": "https://example.org/source/property"}
    assert len(unions[0]["triple_ids"]) == 2


def test_forbidden_namespace_blocks_even_when_a_mapping_rule_matches():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle")
    registry = {
        "format_version": "1.0",
        "namespaces": [{
            "uri": "https://example.org/external/",
            "ontome_namespace_id": 1,
            "status": "forbidden",
            "source": "test",
        }],
    }
    report = audit_inventory(inventory, profiles.capability, profiles.mapping, registry)
    finding = next(item for item in report.findings if item["construct"] == "forbidden_namespace")
    assert finding["status"] == "blocked"
    assert finding["generation_impact"] == "blocks_generation"
    assert "mapping_rule" not in finding


def test_forbidden_namespace_cannot_be_excluded():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    mapping = dict(profiles.mapping)
    mapping["rules"] = [{
        "id": "exclude-source",
        "selector": {"uri_prefix": "https://example.org/source/"},
        "action": "exclude",
        "reason": "Not permitted for a forbidden reference.",
    }]
    registry = {
        "format_version": "1.0",
        "namespaces": [{
            "uri": "https://example.org/external/",
            "ontome_namespace_id": 1,
            "status": "forbidden",
            "source": "test",
        }],
    }
    report = audit_inventory(
        load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle"),
        profiles.capability,
        mapping,
        registry,
    )
    finding = next(item for item in report.findings if item["construct"] == "forbidden_namespace")
    assert finding["status"] == "blocked"


def test_examples_preserve_literal_language_and_datatype():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle")
    report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
    label = next(item for item in report.findings if item["construct"] == "label")
    comment = next(item for item in report.findings if item["construct"] == "comment")
    typed = next(
        item for item in report.findings
        if '^^<http://www.w3.org/2001/XMLSchema#integer>' in item["example"]
    )
    assert '"Class"' in label["example"]
    assert '"A synthetic class."@en' in comment["example"]
    assert '"42"^^<http://www.w3.org/2001/XMLSchema#integer>' in typed["example"]


def test_capability_xsd_checksum_is_verified():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    capability = dict(profiles.capability)
    capability["xsd"] = {**capability["xsd"], "sha256": "0" * 64}
    with pytest.raises(ProfileError, match="XSD SHA-256"):
        verify_capability_xsd(capability)


def test_audit_json_matches_its_schema_and_is_deterministic():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle")
    first = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
    second = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
    schema = json.loads((ROOT / "schemas/reports/audit-1.0.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(first.to_dict())) == []
    assert first.to_json() == second.to_json()


def test_ambiguous_mapping_is_invalid():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    mapping = dict(profiles.mapping)
    mapping["rules"] = [*mapping["rules"], {"id": "also-map", "selector": {"uri_prefix": "https://example.org/source/"}, "action": "map", "target": {"representation": "generic"}}]
    report = audit_inventory(load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle"), profiles.capability, mapping)
    assert {finding["status"] for finding in report.findings} == {"invalid"}


def test_supported_assertion_without_xml_mapping_blocks_generation(tmp_path):
    source = tmp_path / "definition.ttl"
    source.write_text(
        """@prefix ex: <https://example.org/source/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Class a owl:Class ; rdfs:label "Class"@en ; rdfs:isDefinedBy ex:Definition .
""",
        encoding="utf-8",
    )
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    capability = {**profiles.capability, "constructs": {**profiles.capability["constructs"], "definition_link": "supported"}}
    mapping = {
        "format_version": "2.0",
        "scope": {"resource_selectors": [{"uri_prefix": "https://example.org/source/"}]},
        "external_references": [],
        "rules": [{
            "id": "class", "selector": {"rdf_type": "http://www.w3.org/2002/07/owl#Class"}, "action": "map",
            "target": {"entity_kind": "class", "identifier_in_namespace": {"source": "uri_suffix", "strip_prefix": "https://example.org/source/"}, "label_predicates": [f"{RDFS}label"]},
        }],
    }
    report = audit_inventory(load_inventory(source, "turtle"), capability, mapping, {"format_version": "1.0", "namespaces": []})
    finding = next(item for item in report.findings if item["construct"] == "definition_link")
    assert finding["status"] == "blocked"
    assert "explicit generation mapping" in finding["decision_needed"]


def test_standard_range_requires_an_exact_configured_reference(tmp_path):
    source = tmp_path / "xsd-range.ttl"
    source.write_text(
        """@prefix ex: <https://example.org/source/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:Property a owl:DatatypeProperty ; rdfs:label "Property"@en ; rdfs:domain ex:Class ; rdfs:range xsd:string .
ex:Class a owl:Class ; rdfs:label "Class"@en .
""",
        encoding="utf-8",
    )
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    report = audit_inventory(load_inventory(source, "turtle"), profiles.capability, profiles.mapping, profiles.namespace_registry)
    missing = [item for item in report.findings if item["construct"] == "missing_external_reference"]
    assert any("XMLSchema#string" in item["example"] for item in missing)

    mapping = {
        "format_version": "2.0",
        "scope": {"resource_selectors": [{"uri_prefix": "https://example.org/source/"}]},
        "rules": [],
        "external_references": [{"uri": "http://www.w3.org/2001/XMLSchema#string", "reference_namespace": 42, "identifier": "String"}],
    }
    registry = {"format_version": "1.0", "namespaces": [{"uri": "http://www.w3.org/2001/XMLSchema#", "ontome_namespace_id": 42, "status": "active", "source": "test"}]}
    configured = audit_inventory(load_inventory(source, "turtle"), profiles.capability, mapping, registry)
    assert not any(item["construct"] == "missing_external_reference" for item in configured.findings)


def test_rdf_list_components_are_reported_instead_of_ignored():
    profiles = load_audit_profiles(FIXTURES / "import-manifest.yaml")
    report = audit_inventory(load_inventory(FIXTURES / "rdf/constructs.ttl", "turtle"), profiles.capability, profiles.mapping, profiles.namespace_registry)
    assert any(item["construct"] == "rdf_list_structure" and item["status"] == "blocked" for item in report.findings)


def test_relation_predicate_cannot_target_a_different_xml_field():
    profiles = load_generation_profiles(ROOT / "fixtures/phase4/import-manifest.yaml")
    mapping = deepcopy(profiles.mapping)
    mapping["rules"][0]["target"]["relations"][0]["field"] = "equivalentClass"
    with pytest.raises(ProfileError, match="predicate-to-XML"):
        validate_generation_mapping(mapping, profiles.capability)


def test_semantic_constructs_are_declared_by_the_bundled_audit_capability():
    audit = yaml.safe_load((ROOT / "src/ontome_importer/templates/audit/capability-1.1.yaml").read_text())
    generation = yaml.safe_load((ROOT / "src/ontome_importer/templates/generation/capability-1.0.yaml").read_text())
    published = yaml.safe_load((ROOT / "profiles/capabilities/ontome-import-2026-09-15.yaml").read_text())
    assert set(audit["constructs"]) == SEMANTIC_CONSTRUCTS
    assert set(generation["constructs"]) == SEMANTIC_CONSTRUCTS
    assert set(published["constructs"]) == SEMANTIC_CONSTRUCTS
