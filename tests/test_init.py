import hashlib
from pathlib import Path

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
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--scope-uri-prefix", "https://example.org/", "--target-namespace-uri", "https://example.org/target/", "--target-label", "Example target namespace"]) == 2
    assert "Cannot infer RDF format" in capsys.readouterr().err
    assert not workspace.exists()


def test_workspace_completes_the_documented_terminal_workflow(tmp_path, monkeypatch):
    workspace = tmp_path / "my-import"
    assert main([
        "init", "--source", str(E2E_SOURCE), "--format", "turtle", "--workspace", str(workspace),
        "--scope-uri-prefix", "https://example.org/e2e/",
        "--target-namespace-uri", "https://ontome.net/ns/example-target/",
        "--target-label", "Example target",
    ]) == 0
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
