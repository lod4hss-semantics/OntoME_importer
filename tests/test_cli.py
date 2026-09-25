import json
from pathlib import Path

from ontome_importer import __version__
from ontome_importer import cli
from ontome_importer.cli import main


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_help(capsys):
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    output = capsys.readouterr().out
    assert "audit" in output
    assert "init" in output


def test_audit_writes_all_reports(tmp_path):
    manifest = Path(__file__).resolve().parents[1] / "fixtures/phase3/import-manifest.yaml"
    assert main(["audit", "--manifest", str(manifest), "--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == {"inventory.json", "audit.json", "audit.md", "review-queue.json"}
    audit = json.loads((tmp_path / "audit.json").read_text())
    assert audit["strict_ok"] is False
    assert any(item["status"] == "configured" for item in audit["findings"])
    assert "Strict result: blocked" in (tmp_path / "audit.md").read_text()
    assert json.loads((tmp_path / "review-queue.json").read_text())["format_version"] == "1.0"


def test_review_start_creates_a_local_session(tmp_path):
    manifest = Path(__file__).resolve().parents[1] / "fixtures/phase4/import-manifest.yaml"
    session = tmp_path / "review.json"
    assert main(["review", "start", "--manifest", str(manifest), "--session", str(session)]) == 0
    document = json.loads(session.read_text())
    assert document["format_version"] == "1.0"
    assert document["choices"]["resources"]


def test_namespaces_fetch_uses_the_versioned_namespace_catalog(tmp_path, monkeypatch):
    output = tmp_path / "crm-713.rdf"

    def fake_fetch(binding, destination, timeout):
        destination.write_text("catalog", encoding="utf-8")
        return {"ontome_namespace_id": binding.ontome_namespace_id, "catalog": str(destination)}

    monkeypatch.setattr(cli, "fetch_namespace_catalog", fake_fetch)
    assert main([
        "namespaces", "fetch",
        "--uri", "http://www.cidoc-crm.org/cidoc-crm/",
        "--version", "7.1.3",
        "--output", str(output),
    ]) == 0
    assert output.read_text(encoding="utf-8") == "catalog"
    assert json.loads(output.with_suffix(".rdf.metadata.json").read_text()) == {"ontome_namespace_id": 188, "catalog": str(output)}


def test_audit_reports_a_missing_capability_xsd_without_writing_outputs(tmp_path, capsys):
    (tmp_path / "source.ttl").write_text("@prefix ex: <https://example.org/source/> .\nex:A ex:p ex:B .\n")
    (tmp_path / "manifest.yaml").write_text(
        """format_version: \"1.1\"
source:
  file: source.ttl
  format: turtle
target:
  namespace_uri: https://example.org/target/
profiles:
  capability: capability.yaml
  namespace_registry: registry.yaml
  mapping: mapping.yaml
strict: true
"""
    )
    (tmp_path / "capability.yaml").write_text(
        """format_version: \"1.1\"
xsd:
  path: resources/xsd/does-not-exist.xsd
  version: \"test\"
  sha256: "0000000000000000000000000000000000000000000000000000000000000000"
constructs: {}
unknown_construct_policy: blocked
"""
    )
    (tmp_path / "registry.yaml").write_text("format_version: \"1.1\"\nnamespaces: []\n")
    (tmp_path / "mapping.yaml").write_text(
        """format_version: \"1.1\"
scope:
  resource_selectors:
    - uri_prefix: https://example.org/source/
rules: []
"""
    )
    output = tmp_path / "output"
    assert main(["audit", "--manifest", str(tmp_path / "manifest.yaml"), "--output-dir", str(output)]) == 2
    assert "Capability XSD does not exist" in capsys.readouterr().err
    assert not output.exists()
