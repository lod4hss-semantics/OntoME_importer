import json

import pytest
from lxml import etree

from ontome_importer.cli import main
from ontome_importer.comment_sections import parse_cidoc_comment
from ontome_importer.review import load_session, save_session


def test_cidoc_comment_extraction_converts_ea_cardinalities_to_uml():
    parsed = parse_cidoc_comment(
        "Quantification: one to many, necessary (1,1:0,n)\n\n"
        "Full path: an unrelated path\n\n"
        "Scope note:\nThe scope note.\n\nSecond paragraph.\n\n"
        "Examples:\n- First (Citation, 2026)\n- Second\n  continued\n\n"
        "In First Order Logic:\n- P(x,y) ⇒ E(x)",
        property=True,
    )
    assert parsed.scope_note == "The scope note.\n\nSecond paragraph."
    assert parsed.examples == ("First (Citation, 2026)", "Second\n  continued")
    assert dict(parsed.quantifiers) == {
        "domainInstancesMinQuantifier": "0", "domainInstancesMaxQuantifier": "n",
        "rangeInstancesMinQuantifier": "1", "rangeInstancesMaxQuantifier": "1",
    }


@pytest.mark.parametrize("comment", [
    "Scope note:\nBody\n\nQuantification: (1,n:0,7)",
    "Scope note:\nBody\n\nQuantification: (2,1:0,n)",
    "Scope note:\nBody\n\nExamples:\nUnmarked example",
    "Scope note:\nBody\n\nScope note:\nAnother body",
])
def test_cidoc_comment_rejects_ambiguous_sections(comment):
    with pytest.raises(ValueError):
        parse_cidoc_comment(comment, property=True)


def test_review_splits_comments_and_exports_only_retained_property_details(tmp_path, monkeypatch):
    source = tmp_path / "cidoc.ttl"
    source.write_text('''@prefix ex: <https://example.org/model/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex: a owl:Ontology ; rdfs:label "Model"@en .
ex:Class a rdfs:Class ; rdfs:label "Class"@en ;
  rdfs:comment "Scope note:\\nA class.\\n\\nExamples:\\n- A class example\\n\\nIn First Order Logic:\\n- C(x)"@en .
ex:Forward a rdf:Property ; rdfs:label "forward"@en ; owl:inverseOf ex:Reverse ;
  rdfs:domain ex:Class ; rdfs:range ex:Class ;
  rdfs:comment "Quantification: one to many (1,1:0,n)\\n\\nFull path: ignored\\n\\nScope note:\\nForward scope.\\n\\nExamples:\\n- First < example & more\\n- Second example\\n\\nIn First Order Logic:\\n- F(x,y)"@en .
ex:Reverse a rdf:Property ; rdfs:label "reverse"@en ; owl:inverseOf ex:Forward ;
  rdfs:domain ex:Class ; rdfs:range ex:Class ;
  rdfs:comment "This inverse comment must never become an XML text property."@en .
''', encoding="utf-8")
    workspace = tmp_path / "workspace"
    assert main(["init", "--source", str(source), "--workspace", str(workspace)]) == 0
    manifest = workspace / "config/generation.yaml"
    session_path = workspace / "decisions/review.json"
    assert main(["review", "start", "--manifest", str(manifest), "--session", str(session_path)]) == 0
    assert main(["review", "resources", "--session", str(session_path), "--action", "publish"]) == 0
    session = load_session(session_path)
    pair = session["queue"]["inverse_pairs"][0]
    session["choices"]["inverse_pairs"][pair["id"]] = {
        "action": "retain", "retained_uri": "https://example.org/model/Forward",
        "inverse_uri": "https://example.org/model/Reverse",
        "reviewer": "Editor", "at": "2026-10-06T12:00:00+00:00",
    }
    save_session(session, session_path)
    answers = iter(["d", "Keep scope, examples and UML quantification; omit full path and FOL"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "assertions", "--session", str(session_path)]) == 0
    session = load_session(session_path)
    assert len(session["choices"]["field_mappings"]) == 2
    assert main(["review", "check", "--session", str(session_path)]) == 0
    assert main(["review", "finalize", "--manifest", str(manifest), "--session", str(session_path)]) == 0
    assert main(["generate", "--manifest", str(manifest), "--output-dir", str(workspace / "build/import")]) == 0
    document = etree.parse(str(workspace / "build/import/import.xml"))
    forward = "/namespace/properties/property[identifierInNamespace='Forward']"
    assert document.xpath(f"{forward}/label/inverseLabel/text()") == ["reverse"]
    assert document.xpath(f"{forward}/textProperties/scopeNote/text()") == ["Forward scope."]
    assert document.xpath(f"{forward}/textProperties/example/text()") == ["<ul><li>First &lt; example &amp; more</li><li>Second example</li></ul>"]
    assert document.xpath("/namespace/classes/class/textProperties/scopeNote/text()") == ["A class."]
    assert document.xpath("/namespace/classes/class/textProperties/example/text()") == ["<ul><li>A class example</li></ul>"]
    assert [document.xpath(f"{forward}/{field}/text()") for field in (
        "domainInstancesMinQuantifier", "domainInstancesMaxQuantifier",
        "rangeInstancesMinQuantifier", "rangeInstancesMaxQuantifier",
    )] == [["0"], ["n"], ["1"], ["1"]]
    xml = (workspace / "build/import/import.xml").read_text()
    assert "This inverse comment" not in xml and "Full path" not in xml and "F(x,y)" not in xml
    trace = json.loads((workspace / "build/import/generation-trace.json").read_text())
    assert len([entry for entry in trace["entries"] if entry["origin"] == "cidoc_ea_to_uml"]) == 4
    assert len([entry for entry in trace["entries"] if entry["element"] == "example"]) == 2
    assert all(entry["source_triples"] for entry in trace["entries"] if entry["origin"] in {"cidoc_comment_section", "cidoc_ea_to_uml"})
    output = workspace / "build/import"
    assert main(["validate", "--manifest", str(manifest), "--xml", str(output / "import.xml"),
                 "--trace", str(output / "generation-trace.json"), "--audit", str(output / "generation-audit.json"),
                 "--output", str(output / "validation.json")]) == 0


def test_review_uses_short_cidoc_codes_for_local_references(tmp_path):
    source = tmp_path / "codes.ttl"
    source.write_text('''@prefix ex: <https://example.org/model/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex: a owl:Ontology ; rdfs:label "Model"@en .
ex:S10_Parent a rdfs:Class ; rdfs:label "Parent"@en .
ex:S11_Child a rdfs:Class ; rdfs:label "Child"@en ; rdfs:subClassOf ex:S10_Parent .
ex:PXY_Example a rdfs:Class ; rdfs:label "Example"@en .
ex:O37_Some_property a rdf:Property ; rdfs:label "some property"@en ;
  rdfs:domain ex:S11_Child ; rdfs:range ex:S10_Parent .
''', encoding="utf-8")
    workspace = tmp_path / "workspace"
    manifest = workspace / "config/generation.yaml"
    session = workspace / "decisions/review.json"
    assert main(["init", "--source", str(source), "--workspace", str(workspace)]) == 0
    assert main(["review", "start", "--manifest", str(manifest), "--session", str(session)]) == 0
    assert main(["review", "resources", "--session", str(session), "--action", "publish"]) == 0
    assert main(["review", "check", "--session", str(session)]) == 0
    assert main(["review", "finalize", "--manifest", str(manifest), "--session", str(session)]) == 0
    output = workspace / "build/import"
    assert main(["generate", "--manifest", str(manifest), "--output-dir", str(output)]) == 0
    document = etree.parse(str(output / "import.xml"))
    assert set(document.xpath("/namespace/classes/class/identifierInNamespace/text()")) == {"S10", "S11", "PXY"}
    assert document.xpath("/namespace/classes/class[identifierInNamespace='S11']/subClassOf/text()") == ["S10"]
    assert document.xpath("/namespace/properties/property/identifierInNamespace/text()") == ["O37"]
    assert document.xpath("/namespace/properties/property/hasDomain/text()") == ["S11"]
    assert document.xpath("/namespace/properties/property/hasRange/text()") == ["S10"]
    assert document.xpath("/namespace/properties/property/identifierInURI/text()") == ["https://example.org/model/O37_Some_property"]


def test_review_inverses_can_retain_first_for_all_remaining_pairs(tmp_path, monkeypatch):
    source = tmp_path / "inverse.ttl"
    source.write_text('''@prefix ex: <https://example.org/model/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex: a owl:Ontology ; rdfs:label "Model"@en .
ex:A a rdf:Property ; rdfs:label "A"@en ; owl:inverseOf ex:Ai .
ex:Ai a rdf:Property ; rdfs:label "Ai"@en .
ex:B a rdf:Property ; rdfs:label "B"@en ; owl:inverseOf ex:Bi .
ex:Bi a rdf:Property ; rdfs:label "Bi"@en .
ex:C a rdf:Property ; rdfs:label "C"@en ; owl:inverseOf ex:Ci .
ex:Ci a rdf:Property ; rdfs:label "Ci"@en .
''', encoding="utf-8")
    workspace = tmp_path / "workspace"
    assert main(["init", "--source", str(source), "--workspace", str(workspace)]) == 0
    session_path = workspace / "decisions/review.json"
    assert main(["review", "start", "--manifest", str(workspace / "config/generation.yaml"), "--session", str(session_path)]) == 0
    session = load_session(session_path)
    pairs = session["queue"]["inverse_pairs"]
    assert len(pairs) == 3
    session["choices"]["inverse_pairs"][pairs[0]["id"]] = {
        "action": "retain", "retained_uri": pairs[0]["uris"][1], "inverse_uri": pairs[0]["uris"][0],
        "reviewer": "First reviewer", "at": "2026-10-06T12:00:00+00:00",
    }
    save_session(session, session_path)
    answers = iter(["a"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert main(["review", "inverses", "--session", str(session_path), "--reviewer", "Editor"]) == 0
    decisions = load_session(session_path)["choices"]["inverse_pairs"]
    assert decisions[pairs[0]["id"]] == session["choices"]["inverse_pairs"][pairs[0]["id"]]
    assert all(decisions[pair["id"]]["retained_uri"] == pair["uris"][0] and decisions[pair["id"]]["reviewer"] == "Editor" for pair in pairs[1:])
    assert {entry["pair_id"] for entry in load_session(session_path)["journal"] if "pair_id" in entry} == {pair["id"] for pair in pairs[1:]}
