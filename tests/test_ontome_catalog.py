from ontome_importer.ontome_catalog import OntoMECatalogError, resolve_namespace_binding


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
