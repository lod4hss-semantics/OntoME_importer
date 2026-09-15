import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from ontome_importer.loader import RdfLoadError, load_inventory


ROOT = Path(__file__).resolve().parents[1]
RDF = ROOT / "fixtures/phase2/rdf"


def test_turtle_inventory_matches_snapshot():
    inventory = load_inventory("fixtures/phase2/rdf/baseline.ttl", "turtle")
    expected = json.loads(
        (ROOT / "fixtures/phase2/expected/baseline-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert inventory.to_dict() == expected


@pytest.mark.parametrize(
    ("filename", "rdf_format"),
    [("baseline.ttl", "turtle"), ("baseline.rdf", "rdfxml"), ("baseline.nt", "ntriples")],
)
def test_supported_formats_produce_equivalent_graphs(filename, rdf_format):
    baseline = load_inventory(RDF / "baseline.ttl", "turtle").to_dict()
    current = load_inventory(RDF / filename, rdf_format).to_dict()
    _remove_source_provenance(baseline)
    _remove_source_provenance(current)
    assert current == baseline


def test_inventory_validates_against_1_1_schema():
    schema = json.loads(
        (ROOT / "schemas/reports/inventory-1.1.schema.json").read_text(encoding="utf-8")
    )
    inventory = load_inventory(RDF / "baseline.ttl", "turtle").to_dict()
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(inventory))
    assert errors == []


def test_empty_and_duplicate_graphs():
    assert load_inventory(RDF / "empty.ttl", "turtle").to_dict()["triples"] == []
    assert len(load_inventory(RDF / "duplicate.ttl", "turtle").triples) == 1


def test_blank_nodes_and_inventory_references_are_stable():
    first = load_inventory(RDF / "baseline.ttl", "turtle")
    second = load_inventory(RDF / "baseline.ttl", "turtle")
    assert first.to_json() == second.to_json()
    assertion_ids = {triple.id for triple in first.triples}
    for resource in first.resources:
        assert set(resource.outgoing_assertion_ids) <= assertion_ids


@pytest.mark.parametrize(
    ("source", "rdf_format", "message"),
    [
        ("missing.ttl", "turtle", "does not exist"),
        ("malformed.ttl", "turtle", "Cannot parse"),
        ("unsupported.trig", "trig", "Unsupported RDF format"),
    ],
)
def test_loader_rejects_invalid_sources(source, rdf_format, message):
    with pytest.raises(RdfLoadError, match=message):
        load_inventory(RDF / source, rdf_format)


def _remove_source_provenance(document):
    document["source"] = {}
    for triple in document["triples"]:
        triple["provenance"] = {}
