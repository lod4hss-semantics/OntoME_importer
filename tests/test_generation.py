import json
from pathlib import Path

from jsonschema import Draft202012Validator
from lxml import etree

from ontome_importer.cli import main
from ontome_importer.loader import load_inventory
from ontome_importer.profiles import load_generation_profiles, verify_capability_xsd
from ontome_importer.resolution import resolve_generation
from ontome_importer.xml_writer import write_xml


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/phase4"


def test_generation_resolves_writes_valid_xml_and_complete_trace(tmp_path):
    profiles = load_generation_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/valid.ttl", "turtle")
    result = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, profiles.namespace_registry)
    assert result.generation is not None
    xml, trace = write_xml(result.generation, profiles.capability, verify_capability_xsd(profiles.capability), inventory.source_sha256)
    document = etree.fromstring(xml)
    assert document.xpath("/namespace/classes/class[1]/equivalentClass/@referenceNamespace") == ["100"]
    assert document.xpath("/namespace/properties/property[identifierInNamespace='property']/hasDomain/text()") == ["Class"]
    assert document.xpath("/namespace/properties/property[identifierInNamespace='dataProperty']/hasRange/text()") == ["D1"]
    assert document.xpath("/namespace/properties/property[identifierInNamespace='dataProperty']/hasRange/@referenceNamespace") == ["100"]
    assert document.xpath("/namespace/properties/property/identifierInNamespace/text()") == ["dataProperty", "property", "rdfProperty"]
    assert document.xpath("/namespace/referenceNamespace/text()") == ["100"]
    assert document.xpath("/namespace/classes/class[1]/textProperties/contextNote/text()") == ["A mapped comment."]
    assert all(entry["source_triples"] for entry in trace["entries"] if entry["origin"] == "rdf")
    trace_schema = json.loads((ROOT / "schemas/reports/generation-trace-1.1.schema.json").read_text())
    audit_schema = json.loads((ROOT / "schemas/reports/generation-audit-1.0.schema.json").read_text())
    assert list(Draft202012Validator(trace_schema).iter_errors(trace)) == []
    assert list(Draft202012Validator(audit_schema).iter_errors(result.audit)) == []


def test_generation_is_byte_deterministic(tmp_path):
    profiles = load_generation_profiles(FIXTURES / "import-manifest.yaml")
    inventory = load_inventory(FIXTURES / "rdf/valid.ttl", "turtle")
    first = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, profiles.namespace_registry)
    second = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, profiles.namespace_registry)
    first_xml, first_trace = write_xml(first.generation, profiles.capability, verify_capability_xsd(profiles.capability), inventory.source_sha256)
    second_xml, second_trace = write_xml(second.generation, profiles.capability, verify_capability_xsd(profiles.capability), inventory.source_sha256)
    assert first_xml == second_xml
    assert first_trace == second_trace


def test_missing_property_range_blocks_resolution(tmp_path):
    profiles = load_generation_profiles(FIXTURES / "import-manifest.yaml")
    source = tmp_path / "missing-range.ttl"
    source.write_text((FIXTURES / "rdf/valid.ttl").read_text().replace("  rdfs:range ex:Parent ;\n", ""))
    inventory = load_inventory(source, "turtle")
    result = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, profiles.namespace_registry)
    assert result.generation is None
    assert any(item["status"] == "blocked" for item in result.audit["findings"])


def test_generate_cli_writes_only_the_phase4_artifacts(tmp_path):
    assert main(["generate", "--manifest", str(FIXTURES / "import-manifest.yaml"), "--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == {"import.xml", "generation-trace.json", "generation-audit.json"}


def test_generate_cli_blocks_without_publishing_xml(tmp_path):
    assert main(["generate", "--manifest", str(FIXTURES / "import-manifest-missing-range.yaml"), "--output-dir", str(tmp_path)]) == 3
    assert {path.name for path in tmp_path.iterdir()} == {"generation-audit.json"}


def test_generate_refuses_to_replace_an_existing_bundle(tmp_path):
    assert main(["generate", "--manifest", str(FIXTURES / "import-manifest.yaml"), "--output-dir", str(tmp_path)]) == 0
    original_xml = (tmp_path / "import.xml").read_bytes()
    assert main(["generate", "--manifest", str(FIXTURES / "import-manifest-missing-range.yaml"), "--output-dir", str(tmp_path)]) == 2
    assert (tmp_path / "import.xml").read_bytes() == original_xml


def test_generate_cli_is_deterministic_across_output_directories(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    command = ["generate", "--manifest", str(FIXTURES / "import-manifest.yaml"), "--output-dir"]
    assert main([*command, str(first)]) == 0
    assert main([*command, str(second)]) == 0
    for name in ("import.xml", "generation-trace.json", "generation-audit.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_deprecated_external_namespace_is_generated_and_audited():
    profiles = load_generation_profiles(FIXTURES / "import-manifest.yaml")
    registry = dict(profiles.namespace_registry)
    registry["namespaces"] = [{**registry["namespaces"][0], "status": "deprecated"}]
    inventory = load_inventory(FIXTURES / "rdf/valid.ttl", "turtle")
    result = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, registry)
    assert result.generation is not None
    assert any(item.get("reason") == "Deprecated external namespace used." for item in result.audit["findings"])
