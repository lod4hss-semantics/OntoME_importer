"""Resolve versioned OntoME namespaces and cache their published RDF catalogs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from ontome_importer.loader import RdfLoadError, load_inventory
from ontome_importer.package_resources import package_resource_path


SKOS_NOTATION = "http://www.w3.org/2004/02/skos/core#notation"
CATALOG_RESOURCE = "resources/catalogs/ontome-namespaces-2026-09-25.json"


class OntoMECatalogError(ValueError):
    """The published namespace registry or an OntoME RDF catalog is unusable."""


@dataclass(frozen=True)
class NamespaceBinding:
    uri: str
    version: str | None
    ontome_namespace_id: int


def load_namespace_bindings(path: Path | None = None) -> tuple[NamespaceBinding, ...]:
    """Load the versioned URI-to-OntoME namespace registry supplied by OntoME."""
    catalog = path or package_resource_path(CATALOG_RESOURCE)
    try:
        document = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OntoMECatalogError(f"OntoME namespace catalog cannot be read: {catalog}") from error
    if not isinstance(document, dict):
        raise OntoMECatalogError("OntoME namespace catalog must be a JSON object")
    bindings: list[NamespaceBinding] = []
    for uri, versions in document.items():
        if not isinstance(uri, str) or not isinstance(versions, list):
            raise OntoMECatalogError("OntoME namespace catalog has an invalid namespace entry")
        for item in versions:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int) or item["id"] < 1:
                raise OntoMECatalogError(f"OntoME namespace catalog has an invalid entry for {uri}")
            version = item.get("version")
            if version is not None and not isinstance(version, str):
                raise OntoMECatalogError(f"OntoME namespace catalog has an invalid version for {uri}")
            bindings.append(NamespaceBinding(uri, version, item["id"]))
    if len({(item.uri, item.version) for item in bindings}) != len(bindings):
        raise OntoMECatalogError("OntoME namespace catalog has duplicate URI/version entries")
    return tuple(bindings)


def resolve_namespace_binding(uri: str, version: str | None, path: Path | None = None) -> NamespaceBinding:
    """Resolve an explicit URI and version. No version fallback is permitted."""
    matches = [item for item in load_namespace_bindings(path) if item.uri == uri and item.version == version]
    if len(matches) != 1:
        rendered_version = "no version" if version is None else version
        raise OntoMECatalogError(f"No OntoME namespace matches URI {uri} and version {rendered_version}")
    return matches[0]


def fetch_namespace_catalog(binding: NamespaceBinding, destination: Path, timeout: float = 30.0) -> dict[str, object]:
    """Fetch, parse, and atomically cache the RDF export for a selected namespace."""
    url = f"https://ontome.net/api/namespaces-rdf-owl.rdf?namespace={binding.ontome_namespace_id}&lang=en"
    try:
        with urlopen(url, timeout=timeout) as response:
            content = response.read()
    except OSError as error:
        raise OntoMECatalogError(f"Cannot download OntoME namespace {binding.ontome_namespace_id}: {error}") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(content)
    try:
        inventory = load_inventory(temporary, "rdfxml")
    except RdfLoadError as error:
        temporary.unlink(missing_ok=True)
        raise OntoMECatalogError(f"OntoME namespace {binding.ontome_namespace_id} did not return valid RDF/XML") from error
    temporary.replace(destination)
    return {
        "uri": binding.uri,
        "version": binding.version,
        "ontome_namespace_id": binding.ontome_namespace_id,
        "url": url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "catalog": str(destination),
        "resource_count": len(inventory.resources),
    }


def catalog_identifiers(path: Path) -> dict[str, str]:
    """Return exact source URI to OntoME identifier mappings from skos:notation."""
    try:
        inventory = load_inventory(path, "rdfxml")
    except RdfLoadError as error:
        raise OntoMECatalogError(f"OntoME RDF catalog cannot be parsed: {path}") from error
    values: dict[str, list[str]] = {}
    for triple in inventory.triples:
        if triple.subject.kind == "uri" and triple.predicate.value == SKOS_NOTATION and triple.object.kind == "literal":
            values.setdefault(triple.subject.value, []).append(triple.object.value)
    return {uri: identifiers[0] for uri, identifiers in values.items() if len(identifiers) == 1 and identifiers[0]}
