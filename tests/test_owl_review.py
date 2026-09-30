import json

import pytest
import yaml

from ontome_importer.cli import _print_review_blockers, main


ROOT = "https://example.org/model/"


def _workspace(tmp_path, properties=2, anonymous_field="domain"):
    source = tmp_path / "ontology.ttl"
    declarations = []
    for i in range(1, properties + 1):
        expression = f'[ a owl:Class ; owl:{"unionOf" if i % 2 else "intersectionOf"} (<{ROOT}Person> <{ROOT}Group>) ]'
        domain = expression if anonymous_field == "domain" else f"<{ROOT}Person>"
        range_ = expression if anonymous_field == "range" else f"<{ROOT}Person>"
        declarations.append(f'<{ROOT}p{i}> a owl:ObjectProperty ; rdfs:label "Property {i}"@en ; rdfs:domain {domain} ; rdfs:range {range_} .')
    source.write_text(f'''@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<{ROOT}> a owl:Ontology ; rdfs:label "Model"@en .
<{ROOT}Person> a owl:Class ; rdfs:label "Person"@en .
<{ROOT}Group> a owl:Class ; rdfs:label "Group"@en .
{chr(10).join(declarations)}
''')
    workspace = tmp_path / "workspace"
    assert main(["init", "--source", str(source), "--workspace", str(workspace), "--target-ontome-namespace", "427"]) == 0
    return workspace


def _start(workspace):
    session = workspace / "decisions/review.json"
    manifest = workspace / "config/generation.yaml"
    assert main(["review", "start", "--session", str(session), "--manifest", str(manifest)]) == 0
    assert main(["review", "resources", "--session", str(session), "--action", "publish"]) == 0
    return session, manifest


def test_repeated_resource_excludes_all_with_a_reason(tmp_path, capsys):
    session, _ = _start(_workspace(tmp_path, 3))
    uris = [f"{ROOT}p{i}" for i in (1, 2, 3)]
    args = ["review", "resources", "--session", str(session)]
    for uri in uris:
        args.extend(["--resource", uri])
    assert main([*args, "--limit", "1", "--action", "exclude", "--reason", "Not published"]) == 0
    assert "Apply exclude to 3 resource(s)" in capsys.readouterr().out
    choices = json.loads(session.read_text())["choices"]
    assert all(choices["resources"][uri] == "exclude" and choices["resource_reasons"][uri] == "Not published" for uri in uris)
    assert main(["review", "check", "--session", str(session)]) == 0


def test_required_can_replace_a_union_or_exclude_an_intersection(tmp_path, monkeypatch, capsys):
    workspace = _workspace(tmp_path)
    session, manifest = _start(workspace)
    assert main(["review", "check", "--session", str(session)]) == 3
    assert "OWL review: hasDomain" in capsys.readouterr().out
    answers = iter(["b", "Unsupported intersection", "y", "r", "p", ROOT + "Person", "y", "Approved simplification"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "required", "--session", str(session), "--reviewer", "Curator"]) == 0
    choices = json.loads(session.read_text())["choices"]
    assert choices["required"][ROOT + "p1"]["hasDomain"]["reference_uri"] == ROOT + "Person"
    assert choices["resources"][ROOT + "p2"] == "exclude"
    assert main(["review", "check", "--session", str(session)]) == 0
    assert main(["review", "finalize", "--manifest", str(manifest), "--session", str(session)]) == 0
    assert main(["generate", "--manifest", str(manifest), "--output-dir", str(workspace / "build/import")]) == 0
    xml = (workspace / "build/import/import.xml").read_text()
    assert "<hasDomain>Person</hasDomain>" in xml
    assert "<identifierInNamespace>p1</identifierInNamespace>" in xml
    assert "<identifierInNamespace>p2</identifierInNamespace>" not in xml
    audit = json.loads((workspace / "build/import/generation-audit.json").read_text())
    assert any(item.get("category") == "editorial_replacement" for item in audit["findings"])


def test_external_replacement_uses_configured_reference_rule_without_catalog(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path, 1)
    profile_dir = workspace / "config/profiles"
    mapping_path = profile_dir / "mapping-generation.yaml"
    registry_path = profile_dir / "namespace-registry.yaml"
    mapping = yaml.safe_load(mapping_path.read_text())
    mapping["external_reference_rules"] = [{"id": "external-class", "uri_prefix": "https://example.org/external/", "reference_namespace": 321, "identifier_extraction": {"source": "uri_suffix"}}]
    mapping_path.write_text(yaml.safe_dump(mapping))
    registry = yaml.safe_load(registry_path.read_text())
    registry["namespaces"].append({"uri": "https://example.org/external/", "version": "1", "ontome_namespace_id": 321, "status": "active", "source": "https://example.org/external/catalog"})
    registry_path.write_text(yaml.safe_dump(registry))
    session, manifest = _start(workspace)
    answers = iter(["r", "p", "https://example.org/external/Class", "y", "Editorial decision"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "required", "--session", str(session)]) == 0
    assert main(["review", "check", "--session", str(session)]) == 0
    assert main(["review", "finalize", "--session", str(session), "--manifest", str(manifest)]) == 0
    output = workspace / "build/import"
    assert main(["generate", "--manifest", str(manifest), "--output-dir", str(output)]) == 0
    assert '<hasDomain referenceNamespace="321">Class</hasDomain>' in (output / "import.xml").read_text()
    assert main(["validate", "--manifest", str(manifest), "--xml", str(output / "import.xml"), "--trace", str(output / "generation-trace.json"), "--audit", str(output / "generation-audit.json"), "--output", str(output / "validation.json")]) == 0


def test_blocker_summary_counts_unique_uris(capsys):
    _print_review_blockers([{"category": "invalid_source_data", "reason": "anonymous domain", "resource": {"value": f"uri-{i // 2}"}} for i in range(8)])
    assert "(8 finding(s), 4 URI(s); first: uri-0, uri-1, uri-2)" in capsys.readouterr().out


@pytest.mark.parametrize("field,xml_field", [("domain", "hasDomain"), ("range", "hasRange")])
def test_editorial_choice_requires_exact_valid_uri_and_confirmation(tmp_path, monkeypatch, field, xml_field, capsys):
    workspace = _workspace(tmp_path, 1, anonymous_field=field)
    session, _ = _start(workspace)
    answers = iter(["r", "p", "1", "r", "p", ROOT + "Person", "n"])
    # Each invocation leaves the property pending until a valid, confirmed URI is recorded.
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "required", "--session", str(session)]) == 0
    assert "explicit external reference/rule" in capsys.readouterr().out
    assert json.loads(session.read_text())["choices"]["required"] == {}
    assert main(["review", "required", "--session", str(session)]) == 0
    assert json.loads(session.read_text())["choices"]["required"] == {}
    assert main(["review", "check", "--session", str(session)]) == 3


def test_batch_excludes_every_property_in_a_group(tmp_path, monkeypatch, capsys):
    workspace = _workspace(tmp_path, 4)
    session, _ = _start(workspace)
    answers = iter(["b", "OWL intersection cannot be published", "y", "b", "OWL union cannot be published", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "required", "--session", str(session)]) == 0
    text = capsys.readouterr().out
    assert "intersection: 2 published property/properties" in text
    assert "union: 2 published property/properties" in text
    choices = json.loads(session.read_text())["choices"]
    assert all(choices["resources"][ROOT + f"p{i}"] == "exclude" for i in range(1, 5))
    assert main(["review", "check", "--session", str(session)]) == 0


def test_intersection_range_can_be_replaced_and_validated(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path, 2, anonymous_field="range")
    session, manifest = _start(workspace)
    answers = iter(["r", "p", ROOT + "Group", "y", "Editorial range", "b", "Exclude union property", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "required", "--session", str(session)]) == 0
    assert main(["review", "check", "--session", str(session)]) == 0
    assert main(["review", "finalize", "--manifest", str(manifest), "--session", str(session)]) == 0
    output = workspace / "build/import"
    assert main(["generate", "--manifest", str(manifest), "--output-dir", str(output)]) == 0
    assert "<hasRange>Group</hasRange>" in (output / "import.xml").read_text()
    assert main(["validate", "--manifest", str(manifest), "--xml", str(output / "import.xml"), "--trace", str(output / "generation-trace.json"), "--audit", str(output / "generation-audit.json"), "--output", str(output / "validation.json")]) == 0
