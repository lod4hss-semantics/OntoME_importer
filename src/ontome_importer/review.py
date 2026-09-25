"""Persistent, non-interactive review sessions for RDF imports."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Literal

from ontome_importer.audit import AuditReport
from ontome_importer.constructs import OWL, RDF, RDFS, SKOS
from ontome_importer.inventory import Inventory, RdfTerm


RESOURCE_CHOICES = frozenset({"publish", "exclude", "pending"})
RELATION_PREDICATES = frozenset({
    f"{RDFS}subClassOf", f"{RDFS}subPropertyOf", f"{RDFS}domain", f"{RDFS}range",
    f"{OWL}equivalentClass", f"{OWL}equivalentProperty", f"{OWL}inverseOf",
})
CLASS_TYPES = frozenset({f"{RDFS}Class", f"{OWL}Class"})
PROPERTY_TYPES = frozenset({
    f"{RDF}Property", f"{OWL}ObjectProperty", f"{OWL}DatatypeProperty",
    f"{OWL}AnnotationProperty",
})


def build_review_queue(inventory: Inventory, report: AuditReport) -> dict[str, object]:
    """Build a deterministic queue from in-scope audit findings and RDF metadata."""
    if report.inventory.source_sha256 != inventory.source_sha256:
        raise ValueError("Audit report does not belong to the inventory")

    scoped_uris = _scoped_uris(report)
    imports = _imports(inventory)
    imported_uris = {item["uri"] for item in imports}
    resources = {resource.id.value: resource for resource in inventory.resources if resource.id.kind == "uri"}
    classes: list[dict[str, object]] = []
    properties: list[dict[str, object]] = []
    for uri in sorted(scoped_uris):
        resource = resources.get(uri)
        if resource is None:
            continue
        item = {
            "uri": uri,
            "types": [term.to_dict() for term in resource.types],
            "labels": _labels(resource.id, inventory),
            "findings": _resource_findings(uri, report),
        }
        type_uris = {term.value for term in resource.types}
        if type_uris & CLASS_TYPES:
            classes.append(item)
        if type_uris & PROPERTY_TYPES:
            properties.append(item)

    external: dict[str, set[str]] = {}
    for triple in inventory.triples:
        if (
            triple.subject.kind == "uri"
            and triple.subject.value in scoped_uris
            and triple.predicate.value in RELATION_PREDICATES
            and triple.object.kind == "uri"
            and triple.object.value not in scoped_uris
            and triple.object.value not in imported_uris
        ):
            external.setdefault(triple.object.value, set()).add(triple.predicate.value)

    return {
        "format_version": "1.0",
        "source_sha256": inventory.source_sha256,
        "resources": {"classes": classes, "properties": properties},
        "external_dependencies": [
            {"uri": uri, "relation_predicates": sorted(predicates)}
            for uri, predicates in sorted(external.items())
        ],
        "dependencies": imports,
    }


def new_session(
    queue: dict[str, object], *, manifest_sha256: str, now: datetime | None = None
) -> dict[str, object]:
    """Create a review session with all resources initially pending."""
    source_sha256 = queue.get("source_sha256")
    if not isinstance(source_sha256, str):
        raise ValueError("Review queue has no source_sha256")
    if not isinstance(manifest_sha256, str):
        raise ValueError("manifest_sha256 must be a string")
    timestamp = _timestamp(now)
    resource_choices = {
        item["uri"]: "pending"
        for group in queue.get("resources", {}).values()  # type: ignore[union-attr]
        for item in group  # type: ignore[union-attr]
    }
    dependencies = [
        {"uri": item["uri"], **({"version": item["version"]} if "version" in item else {}), "id": None, "catalog_paths": []}
        for item in queue.get("dependencies", [])  # type: ignore[union-attr]
    ]
    return {
        "format_version": "1.0",
        "created_at": timestamp,
        "source_sha256": source_sha256,
        "manifest_sha256": manifest_sha256,
        "queue_sha256": _sha256(queue),
        "queue": deepcopy(queue),
        "choices": {"resources": resource_choices, "dependencies": dependencies},
        "journal": [{"at": timestamp, "action": "session_created"}],
    }


def load_session(path: str | Path) -> dict[str, object]:
    """Load a session JSON document."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot load review session {path}: {error}") from error
    if not isinstance(data, dict) or data.get("format_version") != "1.0":
        raise ValueError("Unsupported review session")
    return data


def save_session(session: dict[str, object], path: str | Path) -> None:
    """Atomically replace a session file after serializing it as canonical JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(session, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def status(session: dict[str, object]) -> dict[str, object]:
    """Return review counts without changing the session."""
    choices = session.get("choices", {})
    resources = choices.get("resources", {}) if isinstance(choices, dict) else {}
    counts = {choice: 0 for choice in sorted(RESOURCE_CHOICES)}
    for choice in resources.values() if isinstance(resources, dict) else ():
        if choice in counts:
            counts[choice] += 1
    dependencies = choices.get("dependencies", []) if isinstance(choices, dict) else []
    return {
        "resources": counts,
        "dependencies": {"total": len(dependencies), "configured": sum(bool(item.get("id") or item.get("catalog_paths")) for item in dependencies)},
    }


def record_choice(
    session: dict[str, object],
    kind: Literal["resource", "dependency"],
    uri: str,
    choice: str | None = None,
    *,
    version: str | None = None,
    identifier: str | None = None,
    catalog_paths: list[str] | None = None,
    now: datetime | None = None,
) -> None:
    """Record a resource decision or dependency catalog resolution in-place."""
    timestamp = _timestamp(now)
    choices = session.get("choices")
    if not isinstance(choices, dict):
        raise ValueError("Invalid review session choices")
    if kind == "resource":
        resources = choices.get("resources")
        if not isinstance(resources, dict) or uri not in resources:
            raise ValueError(f"Unknown review resource: {uri}")
        if choice not in RESOURCE_CHOICES:
            raise ValueError("Resource choice must be publish, exclude, or pending")
        resources[uri] = choice
        entry: dict[str, object] = {"at": timestamp, "action": "resource_choice", "uri": uri, "choice": choice}
    elif kind == "dependency":
        dependencies = choices.get("dependencies")
        if not isinstance(dependencies, list):
            raise ValueError("Invalid review dependencies")
        dependency = next((item for item in dependencies if item.get("uri") == uri and (version is None or item.get("version") == version)), None)
        if dependency is None:
            raise ValueError(f"Unknown review dependency: {uri}")
        if identifier is not None:
            dependency["id"] = identifier
        if catalog_paths is not None:
            dependency["catalog_paths"] = list(catalog_paths)
        entry = {"at": timestamp, "action": "dependency_choice", "uri": uri, "version": dependency.get("version"), "id": dependency.get("id"), "catalog_paths": dependency.get("catalog_paths")}
    else:
        raise ValueError("Choice kind must be resource or dependency")
    journal = session.get("journal")
    if not isinstance(journal, list):
        raise ValueError("Invalid review journal")
    journal.append(entry)


def _scoped_uris(report: AuditReport) -> set[str]:
    uris = set()
    for finding in report.findings:
        for field in ("resource", "scope_resource"):
            term = finding.get(field)
            if isinstance(term, dict) and term.get("kind") == "uri" and isinstance(term.get("value"), str):
                uris.add(term["value"])
    return uris


def _labels(resource: RdfTerm, inventory: Inventory) -> list[dict[str, str]]:
    predicates = {f"{RDFS}label", f"{SKOS}prefLabel"}
    labels = [triple.object.to_dict() for triple in inventory.triples if triple.subject == resource and triple.predicate.value in predicates and triple.object.kind == "literal"]
    return sorted(labels, key=lambda label: (label["value"], label.get("language", ""), label.get("datatype", "")))


def _resource_findings(uri: str, report: AuditReport) -> list[dict[str, object]]:
    return [deepcopy(finding) for finding in report.findings if any(isinstance(finding.get(field), dict) and finding[field].get("value") == uri for field in ("resource", "scope_resource"))]


def _imports(inventory: Inventory) -> list[dict[str, str]]:
    versions: dict[str, list[tuple[int, str]]] = {}
    for triple in inventory.triples:
        if triple.subject.kind != "uri":
            continue
        if triple.predicate.value == f"{OWL}versionIRI" and triple.object.kind == "uri":
            versions.setdefault(triple.subject.value, []).append((0, triple.object.value))
        elif triple.predicate.value == f"{OWL}versionInfo" and triple.object.kind == "literal":
            versions.setdefault(triple.subject.value, []).append((1, triple.object.value))
    imported = {triple.object.value for triple in inventory.triples if triple.predicate.value == f"{OWL}imports" and triple.object.kind == "uri"}
    result = []
    for uri in sorted(imported):
        item = {"uri": uri}
        if uri in versions:
            item["version"] = sorted(versions[uri])[0][1]
        result.append(item)
    return result


def _sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(now: datetime | None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
