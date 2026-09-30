from datetime import datetime, timezone
import hashlib

from ontome_importer.audit import AuditReport
from ontome_importer.inventory import build_inventory
from ontome_importer.review import build_review_queue, load_session, new_session, record_choice, refresh_session, save_session, status


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
