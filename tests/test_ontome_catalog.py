import pytest

from ontome_importer.ontome_catalog import NamespaceBinding, OntoMECatalogError, parse_target_namespace, resolve_imported_namespaces, resolve_namespace_binding


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


def test_import_resolution_uses_existing_namespace_uri_and_version(monkeypatch):
    bindings = (
        NamespaceBinding("https://example.org/model/", "2.0", 321),
        NamespaceBinding("https://example.org/model/", "2.0.1", 322),
        NamespaceBinding("https://example.org/other/", None, 323),
    )
    monkeypatch.setattr("ontome_importer.ontome_catalog.load_namespace_bindings", lambda path=None: bindings)

    assert resolve_imported_namespaces({
        "https://example.org/model/release/2.0/",
        "https://example.org/model/release/2.0.1",
        "https://example.org/model/release/2",
        "https://example.org/other/release/2.0",
    }) == (
        (bindings[1], "https://example.org/model/release/2.0.1"),
        (bindings[0], "https://example.org/model/release/2.0/"),
    )


def test_bundled_catalog_resolves_crm_and_crmsci_from_their_declared_import_uris():
    assert resolve_imported_namespaces({
        "http://www.cidoc-crm.org/cidoc-crm/owl/7.1.3/",
        "http://www.cidoc-crm.org/extensions/crmsci/owl/3.2/",
    }) == (
        (NamespaceBinding("http://www.cidoc-crm.org/cidoc-crm/", "7.1.3", 188), "http://www.cidoc-crm.org/cidoc-crm/owl/7.1.3/"),
        (NamespaceBinding("http://www.cidoc-crm.org/extensions/crmsci/", "3.2", 424), "http://www.cidoc-crm.org/extensions/crmsci/owl/3.2/"),
    )


def test_bundled_catalog_resolves_crmsci_32_from_crmdig_import():
    uri = "http://www.cidoc-crm.org/extensions/crmsci/"
    binding = resolve_namespace_binding(uri, "3.2")
    assert binding.ontome_namespace_id == 424
    assert resolve_imported_namespaces({uri + "3.2/"}) == ((binding, uri + "3.2/"),)


@pytest.mark.parametrize("value", ["123", "https://ontome.net/namespace/123", "https://ontome.net/namespace/123#namespace-hierarchy"])
def test_target_namespace_accepts_id_and_ontome_page(value):
    assert parse_target_namespace(value) == 123


@pytest.mark.parametrize("value", ["0", "-1", "https://example.org/namespace/123", "http://ontome.net/namespace/123", "https://ontome.net/namespace/123?foo=1", "https://ontome.net/namespace/123#wrong", "https://ontome.net/namespace/123/extra"])
def test_target_namespace_rejects_untrusted_or_invalid_values(value):
    with pytest.raises(OntoMECatalogError):
        parse_target_namespace(value)
