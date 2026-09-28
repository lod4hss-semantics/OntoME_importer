import hashlib
from pathlib import Path
import json

from ontome_importer.cli import main
from ontome_importer.profiles import load_audit_profiles, load_generation_profiles, verify_capability_xsd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures/phase2/rdf/baseline.rdf"
E2E_SOURCE = ROOT / "fixtures/e2e/minimal.ttl"


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
    assert {path.name for path in workspace.iterdir()} == {"README.md", "source", "config", "build"}
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


def test_workspace_completes_the_documented_terminal_workflow(tmp_path, monkeypatch):
    workspace = tmp_path / "my-import"
    assert main([
        "init", "--source", str(E2E_SOURCE), "--format", "turtle", "--workspace", str(workspace),
        "--scope-uri-prefix", "https://example.org/e2e/",
        "--target-ontome-namespace", "123",
    ]) == 0
    assert "ontome_namespace_id: 123" in (workspace / "config/generation.yaml").read_text()
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


def test_init_and_audit_do_not_contact_ontome_for_the_target(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Target initialization must not contact OntoME")
    monkeypatch.setattr("ontome_importer.ontome_catalog.urlopen", no_network)
    workspace = tmp_path / "offline"
    assert main(["init", "--source", str(SOURCE), "--workspace", str(workspace), "--target-ontome-namespace", "427", "--target-namespace-uri", "https://example.org/target/", "--target-label", "Example target"]) == 0
    assert not (workspace / "references").exists()
    assert load_audit_profiles(workspace / "config/audit.yaml").manifest["target"] == {"namespace_uri": "https://example.org/target/", "ontome_namespace_id": 427}
    assert main(["audit", "--manifest", str(workspace / "config/audit.yaml"), "--output-dir", str(workspace / "build/audit")]) == 0
    assert load_generation_profiles(workspace / "config/generation.yaml")


def test_init_uses_the_only_labeled_source_ontology_for_a_different_target_uri(tmp_path):
    source = tmp_path / "ontology.ttl"
    source.write_text('''@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://example.org/ontology#> a owl:Ontology ; rdfs:label "Example ontology"@en .
<https://example.org/terms#> a owl:Ontology .
''')
    workspace = tmp_path / "terms"
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--target-namespace-uri", "https://example.org/terms#", "--target-ontome-namespace", "427"]) == 0
    target = load_generation_profiles(workspace / "config/generation.yaml").manifest["target"]
    assert target["namespace_uri"] == "https://example.org/terms#"
    assert target["labels"] == [{"lang": "en", "value": "Example ontology"}]


def test_review_resources_runs_all_by_default_and_allows_revisiting_a_choice(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "review"
    assert main(["init", "--source", str(E2E_SOURCE), "--workspace", str(workspace), "--target-ontome-namespace", "427"]) == 0
    manifest = workspace / "config/generation.yaml"
    session = workspace / "decisions/review.json"
    assert main(["review", "start", "--manifest", str(manifest), "--session", str(session)]) == 0
    monkeypatch.setattr("builtins.input", lambda _: "p")
    assert main(["review", "resources", "--session", str(session)]) == 0
    choices = json.loads(session.read_text())["choices"]["resources"]
    assert all(choice == "publish" for choice in choices.values())
    assert "Findings:" in capsys.readouterr().out
    uri = next(iter(choices))
    monkeypatch.setattr("builtins.input", lambda _: "e")
    assert main(["review", "resources", "--session", str(session), "--resource", uri]) == 0
    assert json.loads(session.read_text())["choices"]["resources"][uri] == "exclude"
