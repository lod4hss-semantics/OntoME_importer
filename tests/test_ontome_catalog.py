import pytest

from ontome_importer.ontome_catalog import OntoMECatalogError, parse_target_namespace, resolve_namespace_binding


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
