import json
from pathlib import Path

from ontome_importer import __version__
from ontome_importer import cli
from ontome_importer.audit import AuditReport
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

    def fake_fetch(binding, destination, timeout, base_url):
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


def test_audit_guides_review_only_when_decisions_are_required(tmp_path, capsys):
    source = Path(__file__).resolve().parents[1] / "fixtures/e2e/minimal.ttl"
    workspace = tmp_path / "my-import"
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--target-ontome-namespace", "427"]) == 0
    capsys.readouterr()
    manifest = workspace / "config/audit.yaml"
    assert main(["audit", "--manifest", str(manifest), "--output-dir", str(workspace / "build/audit")]) == 0
    output = capsys.readouterr().out
    assert "decisions required" in output
    assert f"ontome-importer review start --manifest {workspace / 'config/generation.yaml'} --session {workspace / 'decisions/review.json'}" in output
    assert "ontome-importer generate" not in output


def test_audit_ready_offers_generation_or_review(tmp_path, monkeypatch, capsys):
    source = Path(__file__).resolve().parents[1] / "fixtures/e2e/minimal.ttl"
    workspace = tmp_path / "my-import"
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--target-ontome-namespace", "427"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(cli, "audit_inventory", lambda inventory, *_: AuditReport(inventory, (), ()))
    assert main(["audit", "--manifest", str(workspace / "config/audit.yaml"), "--output-dir", str(workspace / "build/audit")]) == 0
    output = capsys.readouterr().out
    assert "ready for generation" in output and "Next steps:" in output
    assert "ontome-importer generate --manifest" in output
    assert "ontome-importer review start --manifest" in output
    assert "If the generation profile is already finalized" in output


def test_review_guides_pending_resources_and_owl_blockers(tmp_path, capsys):
    source = tmp_path / "source.ttl"
    source.write_text('''@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://example.org/model/> a owl:Ontology ; rdfs:label "Model"@en .
<https://example.org/model/Person> a owl:Class ; rdfs:label "Person"@en .
<https://example.org/model/p> a owl:ObjectProperty ; rdfs:label "p"@en ;
 rdfs:domain [ a owl:Class ; owl:unionOf (<https://example.org/model/Person>) ] ;
 rdfs:range <https://example.org/model/Person> .
''')
    workspace = tmp_path / "my-import"
    session = workspace / "decisions/review.json"
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--target-ontome-namespace", "427"]) == 0
    assert main(["review", "start", "--manifest", str(workspace / "config/generation.yaml"), "--session", str(session)]) == 0
    output = capsys.readouterr().out
    assert f"ontome-importer review resources --session {session}" in output
    assert "ontome-importer review start" not in output
    assert main(["review", "resources", "--session", str(session), "--action", "publish"]) == 0
    output = capsys.readouterr().out
    assert "Next steps:" in output and "ontome-importer review assertions" in output
    assert "ontome-importer review check" in output
    assert main(["review", "check", "--session", str(session)]) == 3
    output = capsys.readouterr().out
    assert "OWL review:" in output and "ontome-importer review required" in output
    assert "ontome-importer review assertions" in output
