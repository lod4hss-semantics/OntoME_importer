"""Locate versioned assets in source checkouts and installed distributions."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def package_resource_path(relative_path: str) -> Path:
    """Return a filesystem path for a shipped schema or XSD resource."""
    installed = resources.files("ontome_importer").joinpath(relative_path)
    try:
        path = Path(installed)
    except TypeError:
        path = Path(__file__).resolve().parents[2] / relative_path
    if path.is_file():
        return path
    source = Path(__file__).resolve().parents[2] / relative_path
    if source.is_file():
        return source
    return path
