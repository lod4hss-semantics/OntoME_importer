import json
from pathlib import Path

from ontome_importer import __version__
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
    assert "audit" in capsys.readouterr().out


def test_audit_writes_all_reports(tmp_path):
    manifest = Path(__file__).resolve().parents[1] / "fixtures/phase3/import-manifest.yaml"
    assert main(["audit", "--manifest", str(manifest), "--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == {"inventory.json", "audit.json", "audit.md"}
    audit = json.loads((tmp_path / "audit.json").read_text())
    assert audit["strict_ok"] is False
    assert any(item["status"] == "configured" for item in audit["findings"])
    assert "Strict result: blocked" in (tmp_path / "audit.md").read_text()


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
    (tmp_path / "registry.yaml").write_text("format_version: \"1.0\"\nnamespaces: []\n")
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
