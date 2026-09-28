import pytest

from ontome_importer.ontome_catalog import OntoMECatalogError, fetch_target_namespace, parse_target_namespace, resolve_namespace_binding


def test_bundled_catalog_resolves_crm_713_to_its_ontome_namespace():
    binding = resolve_namespace_binding("http://www.cidoc-crm.org/cidoc-crm/", "7.1.3")
    assert binding.ontome_namespace_id == 188


def test_bundled_catalog_requires_an_exact_version():
    try:
        resolve_namespace_binding("http://www.cidoc-crm.org/cidoc-crm/", "7.1.1")
    except OntoMECatalogError as error:
        assert "No OntoME namespace matches" in str(error)
    else:
        raise AssertionError("An unlisted namespace version must not resolve")


@pytest.mark.parametrize("value", ["123", "https://ontome.net/namespace/123", "https://ontome.net/namespace/123#namespace-hierarchy"])
def test_target_namespace_accepts_id_and_ontome_page(value):
    assert parse_target_namespace(value) == 123


@pytest.mark.parametrize("value", ["0", "-1", "https://example.org/namespace/123", "http://ontome.net/namespace/123", "https://ontome.net/namespace/123?foo=1", "https://ontome.net/namespace/123#wrong", "https://ontome.net/namespace/123/extra"])
def test_target_namespace_rejects_untrusted_or_invalid_values(value):
    with pytest.raises(OntoMECatalogError):
        parse_target_namespace(value)


def test_target_fetch_rejects_an_invalid_export_without_publishing_workspace(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def read(self):
            return b"<html>Not an RDF ontology</html>"
    monkeypatch.setattr("ontome_importer.ontome_catalog.urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(OntoMECatalogError, match="no usable ontology export"):
        fetch_target_namespace(123, tmp_path / "target.rdf")
