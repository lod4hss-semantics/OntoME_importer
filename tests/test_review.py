from datetime import datetime, timezone
import hashlib
from pathlib import Path

from ontome_importer.audit import AuditReport
from ontome_importer.cli import _assertion_groups, _compile_review
from ontome_importer.inventory import build_inventory
from ontome_importer.ontome_catalog import NamespaceBinding
from ontome_importer.profiles import load_generation_profiles
from ontome_importer.review import active_dependencies, build_review_queue, load_session, new_session, record_choice, refresh_session, review_resource_sets, save_session, status
from ontome_importer.resolution import resolve_generation


def _inventory():
    from rdflib import Graph

    graph = Graph()
    graph.parse(data="""@prefix ex: <https://example.org/source/> .
@prefix ext: <https://example.org/external/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
ex:Class a owl:Class ; rdfs:label "A class"@en ; rdfs:subClassOf ext:Parent .
ex:property a owl:ObjectProperty ; rdfs:label "A property" ; rdfs:domain ex:Class ; rdfs:range ext:Range .
ex:ontology owl:imports ext:ontology .
ext:ontology owl:versionIRI <https://example.org/external/ontology/1.2> .
""", format="turtle")
    return build_inventory(graph, source_file="source.ttl", source_format="turtle", source_sha256="a" * 64)


def _report(inventory):
    def finding(uri, finding_id):
        return {"id": finding_id, "construct": "label", "resource": {"kind": "uri", "value": uri}, "triple_ids": []}
    return AuditReport(inventory, (finding("https://example.org/source/Class", "class-finding"), finding("https://example.org/source/property", "property-finding")), ())


def test_build_review_queue_groups_scoped_resources_and_separates_dependencies():
    inventory = _inventory()
    queue = build_review_queue(inventory, _report(inventory))

    assert [item["uri"] for item in queue["resources"]["classes"]] == ["https://example.org/source/Class"]
    assert queue["resources"]["classes"][0]["labels"] == [{"kind": "literal", "value": "A class", "language": "en"}]
    assert [item["uri"] for item in queue["resources"]["properties"]] == ["https://example.org/source/property"]
    assert [{key: item[key] for key in ("uri", "relation_predicates", "sources")} for item in queue["external_dependencies"]] == [
        {"uri": "https://example.org/external/Parent", "relation_predicates": ["http://www.w3.org/2000/01/rdf-schema#subClassOf"], "sources": ["https://example.org/source/Class"]},
        {"uri": "https://example.org/external/Range", "relation_predicates": ["http://www.w3.org/2000/01/rdf-schema#range"], "sources": ["https://example.org/source/property"]},
        {"uri": "https://example.org/source/Class", "relation_predicates": ["http://www.w3.org/2000/01/rdf-schema#domain"], "sources": ["https://example.org/source/property"]},
    ]
    assert all(len(item["assertions"]) == 1 and item["assertions"][0]["triple_id"].startswith("triple-") for item in queue["external_dependencies"])
    assert queue["dependencies"] == [{"uri": "https://example.org/external/ontology", "version": "https://example.org/external/ontology/1.2"}]


def test_session_records_choices_and_round_trips_atomically(tmp_path):
    inventory = _inventory()
    queue = build_review_queue(inventory, _report(inventory))
    moment = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    session = new_session(queue, manifest_sha256="b" * 64, now=moment, assertion_policy="strict")

    assert session["queue_sha256"] == hashlib.sha256(__import__("json").dumps(queue, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    record_choice(session, "resource", "https://example.org/source/Class", "publish", now=moment)
    record_choice(session, "dependency", "https://example.org/external/ontology", identifier="42", catalog_paths=["catalog/external.xml"], now=moment)
    path = tmp_path / "review.json"
    save_session(session, path)

    loaded = load_session(path)
    assert loaded["choices"]["resources"]["https://example.org/source/Class"] == "publish"
    assert loaded["choices"]["dependencies"] == [
        {"uri": "https://example.org/external/ontology", "version": "https://example.org/external/ontology/1.2", "id": "42", "catalog_paths": ["catalog/external.xml"]},
        {"uri": "https://example.org/external/Parent", "id": None, "catalog_paths": []},
        {"uri": "https://example.org/external/Range", "id": None, "catalog_paths": []},
        {"uri": "https://example.org/source/Class", "id": None, "catalog_paths": []},
    ]
    assert status(loaded) == {"resources": {"exclude": 0, "pending": 1, "publish": 1}, "dependencies": {"total": 2, "configured": 0}}
    assert len(loaded["journal"]) == 3


def test_refresh_session_retains_choices_and_tracks_only_selected_external_terms():
    inventory = _inventory()
    queue = build_review_queue(inventory, _report(inventory))
    old_queue = {**queue, "external_dependencies": []}
    session = new_session(old_queue, manifest_sha256="b" * 64, assertion_policy="strict")
    record_choice(session, "resource", "https://example.org/source/Class", "publish")
    record_choice(session, "resource", "https://example.org/source/property", "exclude")
    assert refresh_session(session, queue, manifest_sha256="b" * 64)
    assert session["choices"]["resources"] == {"https://example.org/source/Class": "publish", "https://example.org/source/property": "exclude"}
    assert status(session)["dependencies"] == {"total": 1, "configured": 0}
    assert not refresh_session(session, queue, manifest_sha256="b" * 64)


def test_import_resolved_namespace_bypasses_manual_external_reference_review(monkeypatch):
    inventory = _inventory()
    binding = NamespaceBinding("https://example.org/external/", "1.2", 321)
    monkeypatch.setattr(
        "ontome_importer.review.resolve_imported_namespaces",
        lambda import_uris: ((binding, "https://example.org/external/ontology"),),
    )

    queue = build_review_queue(inventory, _report(inventory))
    session = new_session(queue, manifest_sha256="b" * 64)

    assert queue["resolved_namespaces"] == [{
        "uri": "https://example.org/external/",
        "version": "1.2",
        "ontome_namespace_id": 321,
        "import_uri": "https://example.org/external/ontology",
    }]
    assert session["choices"]["dependencies"][1]["namespace_resolved"] == queue["resolved_namespaces"][0]
    assert status(session)["dependencies"] == {"total": 1, "configured": 0}


def test_inverse_pair_requires_one_explicit_review_decision():
    from rdflib import Graph

    graph = Graph()
    graph.parse(data="""@prefix ex: <https://example.org/source/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Left a owl:ObjectProperty ; rdfs:label "left"@en ; owl:inverseOf ex:Right .
ex:Right a owl:ObjectProperty ; rdfs:label "right"@en .
""", format="turtle")
    inventory = build_inventory(graph, source_file="source.ttl", source_format="turtle", source_sha256="c" * 64)
    report = AuditReport(inventory, (
        {"id": "left", "construct": "object_property", "resource": {"kind": "uri", "value": "https://example.org/source/Left"}, "triple_ids": []},
        {"id": "right", "construct": "object_property", "resource": {"kind": "uri", "value": "https://example.org/source/Right"}, "triple_ids": []},
    ), ())

    queue = build_review_queue(inventory, report)
    session = new_session(queue, manifest_sha256="b" * 64)

    assert queue["resources"]["properties"] == []
    assert len(queue["inverse_pairs"]) == 1
    assert queue["inverse_pairs"][0]["uris"] == ["https://example.org/source/Left", "https://example.org/source/Right"]
    assert queue["inverse_pairs"][0]["labels"]["https://example.org/source/Left"][0]["value"] == "left"
    assert session["choices"]["inverse_pairs"] == {}


def test_retained_inverse_property_activates_its_external_dependencies():
    from rdflib import Graph

    graph = Graph()
    graph.parse(data="""@prefix ex: <https://example.org/source/> .
@prefix ext: <https://example.org/external/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Left a owl:ObjectProperty ; owl:inverseOf ex:Right ; rdfs:subPropertyOf ext:Parent .
ex:Right a owl:ObjectProperty .
""", format="turtle")
    inventory = build_inventory(graph, source_file="source.ttl", source_format="turtle", source_sha256="e" * 64)
    report = AuditReport(inventory, (
        {"id": "left", "construct": "object_property", "resource": {"kind": "uri", "value": "https://example.org/source/Left"}, "triple_ids": []},
        {"id": "right", "construct": "object_property", "resource": {"kind": "uri", "value": "https://example.org/source/Right"}, "triple_ids": []},
    ), ())
    queue = build_review_queue(inventory, report)
    session = new_session(queue, manifest_sha256="b" * 64)
    pair = queue["inverse_pairs"][0]
    session["choices"]["inverse_pairs"][pair["id"]] = {
        "action": "retain",
        "retained_uri": "https://example.org/source/Left",
        "inverse_uri": "https://example.org/source/Right",
    }

    assert [item["uri"] for item in active_dependencies(session)] == ["https://example.org/external/Parent"]
    selected, published, absorbed = review_resource_sets(session)
    assert selected == published == {"https://example.org/source/Left"}
    assert absorbed == set(pair["triple_ids"])


def test_retained_inverse_property_is_reviewed_and_its_assertion_mapping_is_compiled():
    from rdflib import Graph

    graph = Graph()
    graph.parse(data="""@prefix ex: <https://example.org/source/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Class a owl:Class ; rdfs:label "Class"@en .
ex:Left a owl:ObjectProperty ; rdfs:label "left"@en ; rdfs:comment "A note"@en ; owl:inverseOf ex:Right ; rdfs:domain ex:Class ; rdfs:range ex:Class .
ex:Right a owl:ObjectProperty ; rdfs:label "right"@en ; rdfs:domain ex:Class ; rdfs:range ex:Class .
""", format="turtle")
    inventory = build_inventory(graph, source_file="source.ttl", source_format="turtle", source_sha256="f" * 64)
    left = "https://example.org/source/Left"
    right = "https://example.org/source/Right"
    comment = next(triple for triple in inventory.triples if triple.subject.value == left and triple.predicate.value == "http://www.w3.org/2000/01/rdf-schema#comment")
    report = AuditReport(inventory, (
        {"id": "left", "construct": "object_property", "resource": {"kind": "uri", "value": left}, "triple_ids": []},
        {"id": "right", "construct": "object_property", "resource": {"kind": "uri", "value": right}, "triple_ids": []},
    ), ())
    queue = build_review_queue(inventory, report)
    session = new_session(queue, manifest_sha256="b" * 64)
    pair = queue["inverse_pairs"][0]
    session["choices"]["inverse_pairs"][pair["id"]] = {
        "action": "retain", "retained_uri": left, "inverse_uri": right,
        "reviewer": "Curator", "at": "2026-10-06T12:00:00+00:00",
    }
    blocked_report = AuditReport(inventory, ({
        "id": "comment", "status": "blocked", "construct": "comment",
        "resource": {"kind": "uri", "value": left}, "triple_ids": [comment.id],
    },), ())

    assert _assertion_groups(session, blocked_report, inventory) == [(comment.predicate.value, [blocked_report.findings[0]])]
    session["choices"]["field_mappings"] = {
        f"{left}|{comment.predicate.value}": {"uri": left, "predicate": comment.predicate.value, "field": "contextNote", "construct": "comment", "action": "transform", "reason": "Keep the note.", "reviewer": "Curator", "at": "2026-10-06T12:00:00+00:00"},
    }
    profiles = load_generation_profiles(Path(__file__).resolve().parents[1] / "fixtures/phase4/import-manifest.yaml")
    mapping, _ = _compile_review(session, inventory, profiles)
    rule = next(item for item in mapping["rules"] if item["selector"] == {"uri": left})
    assert rule["target"]["text_fields"] == [{"field": "contextNote", "predicates": [comment.predicate.value]}]


def test_import_resolved_namespace_compiles_a_generic_external_identifier_rule():
    from rdflib import Graph

    graph = Graph()
    graph.parse(data="""@prefix ex: <https://example.org/source/> .
@prefix ext: <https://example.org/external/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Class a owl:Class ; rdfs:label "Class"@en ; rdfs:subClassOf ext:E11_Modification .
""", format="turtle")
    inventory = build_inventory(graph, source_file="source.ttl", source_format="turtle", source_sha256="0" * 64)
    uri = "https://example.org/source/Class"
    report = AuditReport(inventory, ({"id": "class", "construct": "owl_class", "resource": {"kind": "uri", "value": uri}, "triple_ids": []},), ())
    queue = build_review_queue(inventory, report)
    queue["resolved_namespaces"] = [{
        "uri": "https://example.org/external/",
        "version": "2.0",
        "ontome_namespace_id": 321,
        "import_uri": "https://example.org/external/ontology/2.0",
    }]
    session = new_session(queue, manifest_sha256="b" * 64)
    session["choices"]["resources"][uri] = "publish"
    profiles = load_generation_profiles(Path(__file__).resolve().parents[1] / "fixtures/phase4/import-manifest.yaml")

    mapping, registry = _compile_review(session, inventory, profiles)
    assert mapping["external_reference_rules"][-1]["identifier_extraction"] == {"source": "uri_local_identifier"}
    assert any(namespace["ontome_namespace_id"] == 321 for namespace in registry["namespaces"])
    result = resolve_generation(inventory, profiles.manifest, profiles.capability, mapping, registry)
    assert result.generation is not None
    assert result.generation.classes[0].relations[0][1].value == "E11"
    assert result.generation.classes[0].relations[0][1].reference_namespace == 321


def test_ambiguous_inverse_assertions_are_not_turned_into_review_pairs():
    from rdflib import Graph

    graph = Graph()
    graph.parse(data="""@prefix ex: <https://example.org/source/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:First a owl:ObjectProperty ; owl:inverseOf ex:Shared .
ex:Second a owl:ObjectProperty ; owl:inverseOf ex:Shared .
ex:Shared a owl:ObjectProperty .
""", format="turtle")
    inventory = build_inventory(graph, source_file="source.ttl", source_format="turtle", source_sha256="d" * 64)
    report = AuditReport(inventory, tuple(
        {"id": uri, "construct": "object_property", "resource": {"kind": "uri", "value": f"https://example.org/source/{uri.title()}"}, "triple_ids": []}
        for uri in ("first", "second", "shared")
    ), ())

    queue = build_review_queue(inventory, report)

    assert queue["inverse_pairs"] == []
    assert len(queue["inverse_ambiguities"]) == 2
