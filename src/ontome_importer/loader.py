"""RDF graph loading limited to supported simple-graph serializations."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rdflib import Graph

from ontome_importer.inventory import Inventory, build_inventory


SUPPORTED_FORMATS = {
    "turtle": "turtle",
    "rdfxml": "xml",
    "ntriples": "nt",
}


class RdfLoadError(ValueError):
    """A source cannot be loaded as a supported RDF graph."""


def load_inventory(source_path: str | Path, rdf_format: str) -> Inventory:
    """Load a supported RDF file and return its deterministic inventory."""
    if rdf_format not in SUPPORTED_FORMATS:
        supported = ", ".join(SUPPORTED_FORMATS)
        raise RdfLoadError(f"Unsupported RDF format {rdf_format!r}; supported formats: {supported}")

    source = Path(source_path)
    if not source.is_file():
        raise RdfLoadError(f"RDF source file does not exist: {source}")
    source_bytes = source.read_bytes()
    graph = Graph()
    try:
        graph.parse(
            data=source_bytes,
            format=SUPPORTED_FORMATS[rdf_format],
            publicID=source.resolve().as_uri(),
        )
    except Exception as error:
        raise RdfLoadError(f"Cannot parse {source} as {rdf_format}: {error}") from error

    return build_inventory(
        graph,
        source_file=str(source_path),
        source_format=rdf_format,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )
