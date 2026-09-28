import hashlib
from pathlib import Path
import json

import pytest

from ontome_importer.cli import main
from ontome_importer import cli
from ontome_importer.profiles import load_audit_profiles, load_generation_profiles, verify_capability_xsd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures/phase2/rdf/baseline.rdf"
E2E_SOURCE = ROOT / "fixtures/e2e/minimal.ttl"


@pytest.fixture(autouse=True)
def verified_target(monkeypatch):
    def configure(uri="https://example.org/target/"):
        def fetch(namespace_id, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(f'''<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
<owl:Ontology rdf:about="{uri}"><rdfs:label xml:lang="en">Example target</rdfs:label></owl:Ontology>
</rdf:RDF>''', encoding="utf-8")
            return {"ontome_namespace_id": namespace_id, "namespace_uri": uri, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "url": f"https://ontome.net/api/namespaces-rdf-owl.rdf?namespace={namespace_id}&lang=en"}
        monkeypatch.setattr("ontome_importer.cli.fetch_target_namespace", fetch)
    configure()
    return configure


def test_init_creates_a_valid_auditable_workspace(tmp_path, capsys):
    workspace = tmp_path / "my-import"
    assert main([
        "init", "--source", str(SOURCE), "--workspace", str(workspace),
        "--scope-uri-prefix", "https://example.org/",
        "--target-namespace-uri", "https://example.org/target/",
        "--target-label", "Example target namespace",
        "--target-ontome-namespace", "123",
    ]) == 0
    assert "Next command:" in capsys.readouterr().out
    assert {path.name for path in workspace.iterdir()} == {"README.md", "source", "config", "build", "references"}
    assert "Prochaine étape : audit" in (workspace / "README.md").read_text()
    assert "review start" in (workspace / "README.md").read_text()
    assert "workbook" not in (workspace / "README.md").read_text()
    copied = workspace / "source/ontology.rdf"
    assert copied.read_bytes() == SOURCE.read_bytes()
    manifest = (workspace / "config/audit.yaml").read_text()
    assert hashlib.sha256(copied.read_bytes()).hexdigest() in manifest
    assert 'file: "../source/ontology.rdf"' in manifest
    profiles = load_audit_profiles(workspace / "config/audit.yaml")
    verify_capability_xsd(profiles.capability)
    generation = load_generation_profiles(workspace / "config/generation.yaml")
    verify_capability_xsd(generation.capability)
    assert main(["audit", "--manifest", str(workspace / "config/audit.yaml"), "--output-dir", str(workspace / "build/audit")]) == 0
    assert {path.name for path in (workspace / "build/audit").iterdir()} == {"inventory.json", "audit.json", "audit.md", "review-queue.json"}


def test_init_renders_multiple_scope_prefixes_and_refuses_existing_workspace(tmp_path, capsys):
    workspace = tmp_path / "my-import"
    arguments = [
        "init", "--source", str(SOURCE), "--format", "rdfxml", "--workspace", str(workspace),
        "--scope-uri-prefix", "https://example.org/one/", "--scope-uri-prefix", "https://example.org/two/",
        "--target-namespace-uri", "https://example.org/target/", "--target-label", "Example target namespace",
        "--target-ontome-namespace", "https://ontome.net/namespace/123#namespace-hierarchy",
    ]
    assert main(arguments) == 0
    mapping = (workspace / "config/profiles/mapping-audit.yaml").read_text()
    assert "https://example.org/one/" in mapping
    assert "https://example.org/two/" in mapping
    assert main(arguments) == 2
    assert "Workspace already exists" in capsys.readouterr().err


def test_init_requires_an_explicit_format_when_extension_is_unknown(tmp_path, capsys):
    source = tmp_path / "ontology.data"
    source.write_bytes(SOURCE.read_bytes())
    workspace = tmp_path / "my-import"
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--scope-uri-prefix", "https://example.org/", "--target-namespace-uri", "https://example.org/target/", "--target-label", "Example target namespace", "--target-ontome-namespace", "123"]) == 2
    assert "Cannot infer RDF format" in capsys.readouterr().err
    assert not workspace.exists()


def test_workspace_completes_the_documented_terminal_workflow(tmp_path, monkeypatch, verified_target):
    verified_target("https://example.org/e2e/")
    workspace = tmp_path / "my-import"
    assert main([
        "init", "--source", str(E2E_SOURCE), "--format", "turtle", "--workspace", str(workspace),
        "--scope-uri-prefix", "https://example.org/e2e/",
        "--target-ontome-namespace", "123",
    ]) == 0
    assert json.loads((workspace / "references/ontome/target-123.rdf.metadata.json").read_text())["ontome_namespace_id"] == 123
    assert main(["audit", "--manifest", str(workspace / "config/audit.yaml"), "--output-dir", str(workspace / "build/audit")]) == 0
    session = workspace / "decisions/review.json"
    assert main(["review", "start", "--manifest", str(workspace / "config/generation.yaml"), "--session", str(session)]) == 0
    monkeypatch.setattr("builtins.input", lambda _: "p")
    assert main(["review", "resources", "--session", str(session), "--limit", "100"]) == 0
    assert main(["review", "check", "--session", str(session)]) == 0
    assert main(["review", "finalize", "--manifest", str(workspace / "config/generation.yaml"), "--session", str(session)]) == 0
    assert main(["generate", "--manifest", str(workspace / "config/generation.yaml"), "--output-dir", str(workspace / "build/import")]) == 0
    assert main([
        "validate", "--manifest", str(workspace / "config/generation.yaml"),
        "--xml", str(workspace / "build/import/import.xml"),
        "--trace", str(workspace / "build/import/generation-trace.json"),
        "--audit", str(workspace / "build/import/generation-audit.json"),
        "--output", str(workspace / "build/import/validation.json"),
    ]) == 0
    assert json.loads((workspace / "build/import/validation.json").read_text())["target"]["ontome_namespace_id"] == 123
    trace_path = workspace / "build/import/generation-trace.json"
    trace = json.loads(trace_path.read_text())
    trace["target"]["ontome_namespace_id"] = 456
    trace_path.write_text(json.dumps(trace))
    assert main([
        "validate", "--manifest", str(workspace / "config/generation.yaml"),
        "--xml", str(workspace / "build/import/import.xml"), "--trace", str(trace_path),
        "--audit", str(workspace / "build/import/generation-audit.json"),
        "--output", str(workspace / "build/import/tampered-validation.json"),
    ]) == 3
    checks = json.loads((workspace / "build/import/tampered-validation.json").read_text())["checks"]
    assert any(item["name"] == "trace_target_matches_manifest" and not item["valid"] for item in checks)


def test_init_requires_a_target_when_noninteractive(tmp_path, capsys):
    workspace = tmp_path / "no-target"
    assert main(["init", "--source", str(E2E_SOURCE), "--workspace", str(workspace)]) == 2
    assert "--target-ontome-namespace" in capsys.readouterr().err
    assert not workspace.exists()


def test_init_does_not_create_workspace_when_target_is_unreachable(tmp_path, monkeypatch, capsys):
    from ontome_importer.ontome_catalog import OntoMECatalogError
    monkeypatch.setattr(cli, "fetch_target_namespace", lambda *_: (_ for _ in ()).throw(OntoMECatalogError("Target is unavailable")))
    workspace = tmp_path / "unavailable"
    assert main(["init", "--source", str(E2E_SOURCE), "--workspace", str(workspace), "--target-ontome-namespace", "123"]) == 2
    assert "Target is unavailable" in capsys.readouterr().err
    assert not workspace.exists()


def test_init_rejects_a_mismatched_target_uri(tmp_path, verified_target, capsys):
    verified_target("https://example.org/different/")
    workspace = tmp_path / "wrong-uri"
    assert main(["init", "--source", str(E2E_SOURCE), "--workspace", str(workspace), "--target-ontome-namespace", "123"]) == 2
    assert "does not match" in capsys.readouterr().err
    assert not workspace.exists()


def test_saved_target_export_is_checked_before_audit(tmp_path):
    workspace = tmp_path / "tampered"
    assert main(["init", "--source", str(SOURCE), "--workspace", str(workspace), "--target-ontome-namespace", "123", "--target-namespace-uri", "https://example.org/target/"]) == 0
    catalog = workspace / "references/ontome/target-123.rdf"
    catalog.write_bytes(catalog.read_bytes() + b"\n")
    assert main(["audit", "--manifest", str(workspace / "config/audit.yaml"), "--output-dir", str(workspace / "build/audit")]) == 2
    assert not (workspace / "build/audit/audit.json").exists()
