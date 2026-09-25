import json
from pathlib import Path
import shutil

from jsonschema import Draft202012Validator
import yaml

from ontome_importer.cli import main
from ontome_importer.validator import validate_generation


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/phase4"


def _generate(tmp_path):
    assert main(["generate", "--manifest", str(FIXTURES / "import-manifest.yaml"), "--output-dir", str(tmp_path)]) == 0
    return tmp_path


def test_validate_accepts_a_complete_generation_bundle(tmp_path):
    bundle = _generate(tmp_path)
    report = validate_generation(
        FIXTURES / "import-manifest.yaml",
        bundle / "import.xml",
        bundle / "generation-trace.json",
        bundle / "generation-audit.json",
    )
    schema = json.loads((ROOT / "schemas/reports/validation-1.1.schema.json").read_text())
    assert report["valid"] is True
    assert report["counts"]["failed"] == 0
    assert list(Draft202012Validator(schema).iter_errors(report)) == []


def test_validate_accepts_a_bundle_with_generic_external_reference_rules(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURES, workspace)
    mapping_path = workspace / "profiles/mapping.yaml"
    mapping = yaml.safe_load(mapping_path.read_text())
    mapping["external_references"] = []
    mapping["external_reference_rules"] = [{"id": "external-suffix", "uri_prefix": "https://example.org/external/", "reference_namespace": 100, "identifier_extraction": {"source": "uri_suffix"}}]
    mapping_path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    bundle = tmp_path / "bundle"
    assert main(["generate", "--manifest", str(workspace / "import-manifest.yaml"), "--output-dir", str(bundle)]) == 0
    report = validate_generation(workspace / "import-manifest.yaml", bundle / "import.xml", bundle / "generation-trace.json", bundle / "generation-audit.json")
    assert report["valid"] is True


def test_validate_accepts_an_editorial_exception_with_an_external_reference(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURES, workspace)
    mapping_path = workspace / "profiles/mapping.yaml"
    mapping = yaml.safe_load(mapping_path.read_text())
    mapping["editorial_exceptions"] = [{"id": "range", "resource_uri": "https://example.org/source/property", "field": "hasRange", "reference_uri": "https://example.org/external/ExternalClass", "status": "approved", "rationale": "Source omission.", "approved_by": "Editor", "approved_at": "2026-09-23", "decision_reference": "decision-1"}]
    mapping_path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    bundle = tmp_path / "bundle"
    manifest = workspace / "import-manifest-missing-range.yaml"
    assert main(["generate", "--manifest", str(manifest), "--output-dir", str(bundle)]) == 0
    report = validate_generation(manifest, bundle / "import.xml", bundle / "generation-trace.json", bundle / "generation-audit.json")
    assert report["valid"] is True


def test_validate_cli_writes_a_report_and_rejects_tampered_xml(tmp_path):
    bundle = _generate(tmp_path / "bundle")
    xml = bundle / "import.xml"
    xml.write_bytes(xml.read_bytes().replace(b"Example target namespace", b"Tampered target namespace"))
    output = tmp_path / "validation.json"
    assert main([
        "validate", "--manifest", str(FIXTURES / "import-manifest.yaml"), "--xml", str(xml),
        "--trace", str(bundle / "generation-trace.json"), "--audit", str(bundle / "generation-audit.json"),
        "--output", str(output),
    ]) == 3
    report = json.loads(output.read_text())
    assert report["valid"] is False
    assert any(item["name"] == "xml_sha256_matches_trace" and not item["valid"] for item in report["checks"])


def test_validate_rejects_missing_trace_entry(tmp_path):
    bundle = _generate(tmp_path)
    trace_path = bundle / "generation-trace.json"
    trace = json.loads(trace_path.read_text())
    trace["entries"].pop()
    trace_path.write_text(json.dumps(trace))
    report = validate_generation(FIXTURES / "import-manifest.yaml", bundle / "import.xml", trace_path, bundle / "generation-audit.json")
    assert report["valid"] is False
    assert report["xml_elements_without_trace"]


def test_validate_reports_malformed_xml(tmp_path):
    bundle = _generate(tmp_path)
    (bundle / "import.xml").write_bytes(b"<namespace>")
    report = validate_generation(FIXTURES / "import-manifest.yaml", bundle / "import.xml", bundle / "generation-trace.json", bundle / "generation-audit.json")
    assert report["valid"] is False
    assert any(item["name"] == "xml_well_formed" and not item["valid"] for item in report["checks"])


def test_validate_reports_duplicate_identifiers_and_missing_external_root_namespace(tmp_path):
    bundle = _generate(tmp_path)
    xml = bundle / "import.xml"
    xml.write_bytes(
        xml.read_bytes()
        .replace(b"<referenceNamespace>100</referenceNamespace>\n", b"")
        .replace(b"<identifierInNamespace>rdfProperty</identifierInNamespace>", b"<identifierInNamespace>property</identifierInNamespace>")
    )
    report = validate_generation(FIXTURES / "import-manifest.yaml", xml, bundle / "generation-trace.json", bundle / "generation-audit.json")
    assert report["valid"] is False
    assert report["duplicate_identifiers"] == ["property"]
    assert report["unresolved_references"]


def test_validate_reports_noninteger_reference_namespace_without_crashing(tmp_path):
    bundle = _generate(tmp_path)
    xml = bundle / "import.xml"
    xml.write_bytes(xml.read_bytes().replace(b'referenceNamespace="100"', b'referenceNamespace="not-an-integer"'))
    report = validate_generation(FIXTURES / "import-manifest.yaml", xml, bundle / "generation-trace.json", bundle / "generation-audit.json")
    assert report["valid"] is False
    assert report["unresolved_references"]


def test_validation_report_is_deterministic_across_bundle_directories(tmp_path):
    first = _generate(tmp_path / "first")
    second = _generate(tmp_path / "second")
    first_report = validate_generation(FIXTURES / "import-manifest.yaml", first / "import.xml", first / "generation-trace.json", first / "generation-audit.json")
    second_report = validate_generation(FIXTURES / "import-manifest.yaml", second / "import.xml", second / "generation-trace.json", second / "generation-audit.json")
    assert first_report == second_report
