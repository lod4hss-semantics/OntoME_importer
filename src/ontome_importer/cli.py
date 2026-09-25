"""Command-line interface for the OntoME importer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from ontome_importer import __version__
from ontome_importer.audit import audit_inventory
from ontome_importer.loader import RdfLoadError, load_inventory
from ontome_importer.mapping_assistant import AssistantError, _catalog_identifiers, _resolve_catalog_identifier, annotate_workbook, check_workbook, compile_workbook, dump_yaml, export_workbook, refresh_workbook, validate_compiled_profiles
from ontome_importer.ontome_catalog import OntoMECatalogError, fetch_namespace_catalog, load_namespace_bindings, resolve_namespace_binding
from ontome_importer.profiles import ProfileError, load_audit_profiles, load_generation_profiles, verify_capability_xsd, verify_source_checksum
from ontome_importer.review import build_review_queue, load_session, new_session, record_choice, save_session, status
from ontome_importer.resolution import resolve_generation
from ontome_importer.validator import validate_generation
from ontome_importer.workspace import WorkspaceError, initialize_workspace
from ontome_importer.xml_writer import XmlGenerationError, write_xml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ontome-importer")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create an import workspace from an RDF source.")
    init.add_argument("--source", required=True, help="Path to the RDF source file to copy.")
    init.add_argument("--workspace", required=True, help="New workspace directory to create.")
    init.add_argument("--format", choices=("turtle", "rdfxml", "ntriples"), help="RDF source format; inferred from a known extension when omitted.")
    init.add_argument("--scope-uri-prefix", required=True, action="append", help="URI prefix to include in the import scope; repeat for multiple prefixes.")
    init.add_argument("--target-namespace-uri", help="Target OntoME namespace URI; defaults to a visible placeholder.")
    audit = commands.add_parser("audit", help="Audit an RDF ontology and prepare a terminal review queue.")
    audit.add_argument("--manifest", required=True, help="Path to an import manifest 1.1.")
    audit.add_argument("--output-dir", required=True, help="Directory for audit outputs.")
    audit.add_argument("--generation-manifest", help=argparse.SUPPRESS)
    audit.add_argument("--workbook", help=argparse.SUPPRESS)
    generate = commands.add_parser("generate", help="Generate OntoME XML from finalized publication decisions.")
    generate.add_argument("--manifest", required=True, help="Path to a finalized generation import manifest.")
    generate.add_argument("--output-dir", required=True, help="Directory for generated XML and reports.")
    generate.add_argument("--workbook", help=argparse.SUPPRESS)
    validate = commands.add_parser("validate", help="Validate a generated OntoME XML import.")
    validate.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    validate.add_argument("--xml", required=True, help="Path to import.xml.")
    validate.add_argument("--trace", required=True, help="Path to generation-trace.json.")
    validate.add_argument("--audit", required=True, help="Path to generation-audit.json.")
    validate.add_argument("--output", required=True, help="Path for validation.json.")
    validate.add_argument("--workbook", help=argparse.SUPPRESS)
    namespaces = commands.add_parser("namespaces", help="Resolve and cache versioned OntoME namespace catalogs.")
    namespace_commands = namespaces.add_subparsers(dest="namespace_command", required=True)
    fetch = namespace_commands.add_parser("fetch", help="Download the RDF catalog for an explicit OntoME namespace URI and version.")
    fetch.add_argument("--uri", required=True, help="External namespace URI from the RDF source.")
    fetch.add_argument("--version", required=True, help="Explicit OntoME namespace version to select.")
    fetch.add_argument("--output", required=True, help="New local RDF/XML cache path.")
    fetch.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    review = commands.add_parser("review", help="Review import decisions locally in the terminal.")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_start = review_commands.add_parser("start", help="Create or resume a local review session.")
    review_start.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    review_start.add_argument("--session", default="decisions/review.json", help="Path for the persistent review session.")
    review_resources = review_commands.add_parser("resources", help="Review pending classes and properties.")
    review_resources.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    review_resources.add_argument("--limit", type=int, default=1, help="Maximum pending resources to review in this run.")
    review_status = review_commands.add_parser("status", help="Show local review progress.")
    review_status.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    review_check = review_commands.add_parser("check", help="Report decisions that still block finalization.")
    review_check.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    review_finalize = review_commands.add_parser("finalize", help="Compile reviewed decisions into internal transformation profiles.")
    review_finalize.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    review_finalize.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    assist = commands.add_parser("assist", help="Legacy XLSX migration commands; use review instead.")
    assist_commands = assist.add_subparsers(dest="assist_command", required=True)
    export = assist_commands.add_parser("export", help="Create an XLSX workbook from a generation manifest.")
    export.add_argument("--manifest", required=True, help="Path to a generation import manifest.")
    export.add_argument("--output", required=True, help="New XLSX workbook path.")
    export.add_argument("--catalog", help="Optional RDF catalog used only to prefill exact external identifiers.")
    export.add_argument("--catalog-format", choices=("turtle", "rdfxml", "ntriples"), help="Format of the optional catalog RDF.")
    export.add_argument("--catalog-identifier-predicate", help="URI predicate holding one canonical identifier per catalog resource.")
    export.add_argument("--catalog-namespace-uri", help="External namespace URI represented by the catalog.")
    export.add_argument("--catalog-namespace-version", help="Explicit OntoME version represented by the catalog.")
    export.add_argument("--catalog-namespace-id", type=int, help="OntoME namespace ID for catalog terms.")
    check = assist_commands.add_parser("check", help="Check an XLSX workbook without modifying it.")
    check.add_argument("--manifest", required=True, help="Path to a generation import manifest.")
    check.add_argument("--workbook", required=True, help="XLSX workbook path.")
    check.add_argument("--output", required=True, help="Path for the JSON check report.")
    refresh = assist_commands.add_parser("refresh", help="Annotate an XLSX workbook with current validation diagnostics.")
    refresh.add_argument("--manifest", required=True, help="Path to a generation import manifest.")
    refresh.add_argument("--workbook", required=True, help="XLSX workbook path to update.")
    refresh.add_argument("--output", required=True, help="Path for the JSON refresh report.")
    compile_ = assist_commands.add_parser("compile", help="Compile checked XLSX decisions into YAML profiles.")
    compile_.add_argument("--manifest", required=True, help="Path to a generation import manifest.")
    compile_.add_argument("--workbook", required=True, help="XLSX workbook path.")
    compile_.add_argument("--mapping-output", required=True, help="Path for compiled mapping profile 7.0 YAML.")
    compile_.add_argument("--registry-output", required=True, help="Path for compiled namespace registry YAML.")
    compile_.add_argument("--report-output", required=True, help="Path for the JSON compile report.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return _run_init(args)
    if args.command == "audit":
        return _run_audit(args)
    if args.command == "generate":
        return _run_generate(args)
    if args.command == "namespaces":
        return _run_namespaces(args)
    if args.command == "review":
        return _run_review(args)
    if args.command == "assist":
        return _run_assist(args)
    return _run_validate(args)


def _run_init(args: argparse.Namespace) -> int:
    try:
        command = initialize_workspace(
            Path(args.source),
            Path(args.workspace),
            args.format,
            args.scope_uri_prefix,
            args.target_namespace_uri,
        )
        print("Workspace created.")
        print("Next command:")
        print(command)
        return 0
    except (WorkspaceError, RdfLoadError, OSError, ProfileError) as error:
        print(f"ontome-importer init: {error}", file=sys.stderr)
        return 2


def _run_audit(args: argparse.Namespace) -> int:
    try:
        manifest_path = Path(args.manifest)
        profiles = load_audit_profiles(manifest_path)
        verify_capability_xsd(profiles.capability)
        source = profiles.manifest["source"]
        assert isinstance(source, dict)
        source_path = manifest_path.parent / str(source["file"])
        verify_source_checksum(profiles.manifest, source_path)
        inventory = load_inventory(source_path, str(source["format"]))
        report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
        if bool(args.generation_manifest) != bool(args.workbook):
            raise ProfileError("--generation-manifest and --workbook must be used together")
        if args.workbook:
            workbook = Path(args.workbook)
            if workbook.exists():
                raise OSError(f"Workbook already exists: {workbook}")
            generation_profiles = load_generation_profiles(Path(args.generation_manifest))
            export_workbook(workbook, generation_profiles, inventory)
        _publish_files(Path(args.output_dir), {
            "inventory.json": inventory.to_json().encode("utf-8"),
            "audit.json": report.to_json().encode("utf-8"),
            "audit.md": report.to_markdown().encode("utf-8"),
            "review-queue.json": _json(build_review_queue(inventory, report)).encode("utf-8"),
        })
        print(f"ontome-importer audit: {'ready for generation' if report.to_dict()['strict_ok'] else 'decisions required'}; reports written to {args.output_dir}")
        return 0
    except (AssistantError, ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer audit: {error}", file=sys.stderr)
        return 2


def _run_namespaces(args: argparse.Namespace) -> int:
    try:
        binding = resolve_namespace_binding(args.uri, args.version)
        output = Path(args.output)
        metadata = output.with_suffix(output.suffix + ".metadata.json")
        if output.exists() or metadata.exists():
            raise OSError(f"Namespace catalog output already exists: {output}")
        result = fetch_namespace_catalog(binding, output, args.timeout)
        metadata.write_text(_json(result), encoding="utf-8")
        print(f"OntoME namespace {binding.ontome_namespace_id} ({binding.uri}, version {binding.version}) cached at {output}")
        return 0
    except (OntoMECatalogError, OSError, ValueError) as error:
        print(f"ontome-importer namespaces: {error}", file=sys.stderr)
        return 2


def _run_review(args: argparse.Namespace) -> int:
    try:
        session_path = Path(args.session)
        if args.review_command == "start":
            manifest_path = Path(args.manifest)
            profiles = load_generation_profiles(manifest_path)
            source = profiles.manifest["source"]
            assert isinstance(source, dict)
            inventory = load_inventory(manifest_path.parent / str(source["file"]), str(source["format"]))
            report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
            if session_path.exists():
                session = load_session(session_path)
                if session.get("source_sha256") != inventory.source_sha256:
                    raise ValueError("Review session does not belong to this source")
                print(f"Review session resumed: {session_path}")
            else:
                session = new_session(build_review_queue(inventory, report), manifest_sha256=_hash_json(profiles.manifest))
                save_session(session, session_path)
                print(f"Review session created: {session_path}")
            _configure_review_dependencies(session, session_path)
            save_session(session, session_path)
            _print_review_status(status(session))
            print("Next command: ontome-importer review resources --session " + str(session_path))
            return 0
        session = load_session(session_path)
        if args.review_command == "status":
            _print_review_status(status(session))
            return 0
        if args.review_command == "check":
            review_status = status(session)
            pending = review_status["resources"]["pending"]
            dependencies = review_status["dependencies"]
            if pending or dependencies["configured"] != dependencies["total"]:
                print(f"Review incomplete: {pending} resource decisions pending; {dependencies['configured']}/{dependencies['total']} dependencies configured.")
                return 3
            print("Review is complete.")
            return 0
        if args.review_command == "finalize":
            manifest_path = Path(args.manifest)
            profiles = load_generation_profiles(manifest_path)
            review_status = status(session)
            if review_status["resources"]["pending"] or review_status["dependencies"]["configured"] != review_status["dependencies"]["total"]:
                raise ValueError("Review is incomplete; run review check for remaining decisions")
            source = profiles.manifest["source"]
            assert isinstance(source, dict)
            inventory = load_inventory(manifest_path.parent / str(source["file"]), str(source["format"]))
            mapping, registry = _compile_review(session, inventory, profiles)
            _publish_compilation({
                manifest_path.parent / "profiles" / "mapping-generation.yaml": dump_yaml(mapping),
                manifest_path.parent / "profiles" / "namespace-registry.yaml": dump_yaml(registry),
            })
            print("Review finalized. Internal transformation profiles were updated.")
            return 0
        pending = [uri for uri, choice in session["choices"]["resources"].items() if choice == "pending"]
        for uri in pending[:args.limit]:
            resource = _review_resource(session, uri)
            print(f"\n{resource['kind']} {uri}\nLabels: {resource['labels'] or 'none'}\nFindings: {resource['finding_count']}")
            answer = input("[p]ublish, [e]xclude, [s]kip: ").strip().lower()
            choice = {"p": "publish", "e": "exclude", "s": "pending"}.get(answer)
            if choice is None:
                print("No decision recorded.")
                continue
            record_choice(session, "resource", uri, choice)
            save_session(session, session_path)
        _print_review_status(status(session))
        return 0
    except (AssistantError, OntoMECatalogError, ProfileError, RdfLoadError, OSError, ValueError) as error:
        print(f"ontome-importer review: {error}", file=sys.stderr)
        return 2


def _review_resource(session: dict[str, object], uri: str) -> dict[str, object]:
    queue = session["queue"]
    assert isinstance(queue, dict)
    resources = queue["resources"]
    assert isinstance(resources, dict)
    for kind, values in resources.items():
        assert isinstance(values, list)
        match = next((item for item in values if item["uri"] == uri), None)
        if match is not None:
            labels = ", ".join(f"{label['value']} [{label.get('language', '')}]" for label in match["labels"])
            return {"kind": "Class" if kind == "classes" else "Property", "labels": labels, "finding_count": len(match["findings"])}
    raise ValueError(f"Review resource is missing from the queue: {uri}")


def _configure_review_dependencies(session: dict[str, object], session_path: Path) -> None:
    choices = session["choices"]
    assert isinstance(choices, dict)
    dependencies = choices["dependencies"]
    assert isinstance(dependencies, list)
    bindings = load_namespace_bindings()
    for dependency in dependencies:
        if dependency.get("id") or dependency.get("catalog_paths"):
            continue
        uri = str(dependency["uri"])
        candidates = [item for item in bindings if uri.startswith(item.uri) and (item.version is None or item.version in uri)]
        if len(candidates) != 1:
            print(f"Dependency requires a version selection before it can be resolved: {uri}")
            continue
        binding = candidates[0]
        answer = input(f"Use OntoME namespace {binding.ontome_namespace_id} for {binding.uri} version {binding.version}? [Y/n] ").strip().lower()
        if answer not in {"", "y", "yes", "o", "oui"}:
            continue
        catalog = Path("references") / "ontome" / f"namespace-{binding.ontome_namespace_id}.rdf"
        if not catalog.exists():
            fetch_namespace_catalog(binding, catalog)
        record_choice(session, "dependency", uri, identifier=str(binding.ontome_namespace_id), catalog_paths=[str(catalog)])
        print(f"Dependency resolved: {binding.uri} version {binding.version}, OntoME namespace {binding.ontome_namespace_id}.")


def _print_review_status(value: dict[str, object]) -> None:
    resources = value["resources"]
    dependencies = value["dependencies"]
    print("Review status")
    print(f"Resources: {resources['publish']} publish, {resources['exclude']} exclude, {resources['pending']} pending.")
    print(f"Dependencies: {dependencies['configured']}/{dependencies['total']} configured.")


def _compile_review(session: dict[str, object], inventory: object, profiles: object) -> tuple[dict[str, object], dict[str, object]]:
    from ontome_importer.constructs import OWL, RDF, RDFS, SKOS

    assert hasattr(inventory, "resources") and hasattr(inventory, "triples")
    choices = session["choices"]
    assert isinstance(choices, dict)
    resource_choices = choices["resources"]
    assert isinstance(resource_choices, dict)
    scope = profiles.mapping["scope"]
    rules = []
    for resource in inventory.resources:
        if resource.id.kind != "uri" or resource_choices.get(resource.id.value) not in {"publish", "exclude"}:
            continue
        types = {term.value for term in resource.types}
        action = resource_choices[resource.id.value]
        rule: dict[str, object] = {"id": "review-" + hashlib.sha256(resource.id.value.encode()).hexdigest()[:12], "selector": {"uri": resource.id.value}, "action": action}
        if action == "exclude":
            rule["reason"] = "Excluded during terminal review."
        else:
            if types & {f"{OWL}Class", f"{RDFS}Class"}:
                target = {"entity_kind": "class"}
            elif f"{OWL}ObjectProperty" in types:
                target = {"entity_kind": "property", "property_kind": "object"}
            elif f"{OWL}DatatypeProperty" in types:
                target = {"entity_kind": "property", "property_kind": "datatype"}
            else:
                target = {"entity_kind": "property", "property_kind": "rdf"}
            prefix, terminal = resource.id.value.rsplit("/", 1) if "/" in resource.id.value else ("", resource.id.value)
            identifier = terminal.split("_", 1)[0]
            target["identifier_in_namespace"] = {"source": "regex_capture", "pattern": re.escape(prefix + "/") + "(" + re.escape(identifier) + r")(?:_.*)?"}
            target["label_predicates"] = [f"{RDFS}label"]
            target["identifier_in_uri"] = "source_uri"
            if target["entity_kind"] == "class":
                target["relations"] = [{"field": "subClassOf", "predicate": f"{RDFS}subClassOf"}, {"field": "equivalentClass", "predicate": f"{OWL}equivalentClass"}]
            else:
                target["relations"] = [{"field": "subPropertyOf", "predicate": f"{RDFS}subPropertyOf"}, {"field": "equivalentProperty", "predicate": f"{OWL}equivalentProperty"}, {"field": "inverseOf", "predicate": f"{OWL}inverseOf"}]
                target["domain_range"] = {"domain_predicate": f"{RDFS}domain", "range_predicate": f"{RDFS}range"}
            rule["target"] = target
        rules.append(rule)
    registry, catalog_terms = _review_catalogs(choices)
    external_references = {}
    published = {uri for uri, choice in resource_choices.items() if choice == "publish"}
    relation_predicates = {f"{RDFS}subClassOf", f"{RDFS}subPropertyOf", f"{RDFS}domain", f"{RDFS}range", f"{OWL}equivalentClass", f"{OWL}equivalentProperty", f"{OWL}inverseOf"}
    for triple in inventory.triples:
        if triple.subject.value not in published or triple.object.kind != "uri" or triple.object.value in published or triple.predicate.value not in relation_predicates:
            continue
        matches = [(item, _resolve_catalog_identifier(triple.object.value, terms)) for item, terms in catalog_terms]
        matches = [(item, identifier) for item, identifier in matches if identifier]
        if len(matches) != 1:
            raise ValueError(f"External term is not resolved by exactly one selected OntoME catalog: {triple.object.value}")
        item, identifier = matches[0]
        external_references[triple.object.value] = {"uri": triple.object.value, "reference_namespace": item["ontome_namespace_id"], "identifier": identifier}
    mapping = {"format_version": "7.0", "scope": scope, "rules": rules, "external_references": list(external_references.values()), "external_reference_rules": [], "editorial_exceptions": [], "decisions": []}
    validate_compiled_profiles(mapping, registry, profiles)
    return mapping, registry


def _review_catalogs(choices: dict[str, object]) -> tuple[dict[str, object], list[tuple[dict[str, object], dict[str, str]]]]:
    dependencies = choices["dependencies"]
    assert isinstance(dependencies, list)
    namespaces = []
    catalogs = []
    for dependency in dependencies:
        for name in dependency.get("catalog_paths", []):
            path = Path(name)
            metadata = json.loads(path.with_suffix(path.suffix + ".metadata.json").read_text(encoding="utf-8"))
            item = {"uri": metadata["uri"], "version": metadata["version"], "ontome_namespace_id": metadata["ontome_namespace_id"], "status": "active", "source": metadata["url"]}
            namespaces.append(item)
            catalogs.append((item, _catalog_identifiers(load_inventory(path, "rdfxml"), "http://www.w3.org/2004/02/skos/core#notation")))
    return {"format_version": "1.1", "namespaces": namespaces}, catalogs


def _run_generate(args: argparse.Namespace) -> int:
    try:
        manifest_path = Path(args.manifest)
        profiles = load_generation_profiles(manifest_path)
        xsd_path = verify_capability_xsd(profiles.capability)
        source = profiles.manifest["source"]
        assert isinstance(source, dict)
        source_path = manifest_path.parent / str(source["file"])
        verify_source_checksum(profiles.manifest, source_path)
        inventory = load_inventory(source_path, str(source["format"]))
        result = resolve_generation(inventory, profiles.manifest, profiles.capability, profiles.mapping, profiles.namespace_registry)
        output_dir = Path(args.output_dir)
        if result.generation is None:
            _publish_files(output_dir, {"generation-audit.json": _json(result.audit).encode("utf-8")})
            if args.workbook:
                annotate_workbook(Path(args.workbook), profiles, inventory, _generation_issues(result.audit, inventory))
            print("ontome-importer generate: generation blocked; see generation-audit.json", file=sys.stderr)
            return 3
        xml, trace = write_xml(result.generation, profiles.capability, xsd_path, inventory.source_sha256)
        _publish_files(output_dir, {
            "import.xml": xml,
            "generation-trace.json": _json(trace).encode("utf-8"),
            "generation-audit.json": _json(result.audit).encode("utf-8"),
        })
        if args.workbook:
            annotate_workbook(Path(args.workbook), profiles, inventory, _generation_issues(result.audit, inventory))
        print(f"ontome-importer generate: XML and reports written to {output_dir}")
        return 0
    except XmlGenerationError as error:
        print(f"ontome-importer generate: {error}", file=sys.stderr)
        return 3
    except (AssistantError, ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer generate: {error}", file=sys.stderr)
        return 2


def _run_assist(args: argparse.Namespace) -> int:
    try:
        manifest_path = Path(args.manifest)
        profiles = load_generation_profiles(manifest_path)
        verify_capability_xsd(profiles.capability)
        source = profiles.manifest["source"]
        assert isinstance(source, dict)
        source_path = manifest_path.parent / str(source["file"])
        verify_source_checksum(profiles.manifest, source_path)
        inventory = load_inventory(source_path, str(source["format"]))
        if args.assist_command == "export":
            output = Path(args.output)
            if output.exists():
                raise OSError(f"Workbook already exists: {output}")
            catalog_options = (args.catalog, args.catalog_format, args.catalog_identifier_predicate, args.catalog_namespace_uri, args.catalog_namespace_version, args.catalog_namespace_id)
            if any(value is not None for value in catalog_options) and not all(value is not None for value in catalog_options):
                raise AssistantError("Catalog use requires --catalog, --catalog-format, --catalog-identifier-predicate, --catalog-namespace-uri, --catalog-namespace-version and --catalog-namespace-id")
            if args.catalog:
                binding = resolve_namespace_binding(args.catalog_namespace_uri, args.catalog_namespace_version)
                if binding.ontome_namespace_id != args.catalog_namespace_id:
                    raise AssistantError("Catalog namespace ID does not match the bundled OntoME URI/version registry")
            catalog = load_inventory(Path(args.catalog), args.catalog_format) if args.catalog else None
            export_workbook(output, profiles, inventory, catalog, args.catalog_identifier_predicate, args.catalog_namespace_version, args.catalog_namespace_id)
            return 0
        workbook = Path(args.workbook)
        if args.assist_command == "check":
            report = check_workbook(workbook, profiles, inventory)
            output = Path(args.output)
            _publish_files(output.parent, {output.name: _json(report).encode("utf-8")})
            return 0 if report["valid"] else 3
        if args.assist_command == "refresh":
            report = refresh_workbook(workbook, profiles, inventory)
            output = Path(args.output)
            _publish_files(output.parent, {output.name: _json(report).encode("utf-8")})
            return 0 if report["valid"] else 3
        mapping, registry, report = compile_workbook(workbook, profiles, inventory)
        compilation_paths = (Path(args.mapping_output), Path(args.registry_output), Path(args.report_output))
        if len({path.resolve() for path in compilation_paths}) != len(compilation_paths):
            raise AssistantError("Compilation output paths must be distinct")
        _publish_compilation({
            compilation_paths[0]: dump_yaml(mapping),
            compilation_paths[1]: dump_yaml(registry),
            compilation_paths[2]: _json(report).encode("utf-8"),
        })
        return 0
    except (AssistantError, ProfileError, RdfLoadError, OSError, ValueError) as error:
        print(f"ontome-importer assist: {error}", file=sys.stderr)
        return 2


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _run_validate(args: argparse.Namespace) -> int:
    try:
        report = validate_generation(Path(args.manifest), Path(args.xml), Path(args.trace), Path(args.audit))
        output = Path(args.output)
        _publish_files(output.parent, {output.name: _json(report).encode("utf-8")})
        if args.workbook:
            manifest_path = Path(args.manifest)
            profiles = load_generation_profiles(manifest_path)
            source = profiles.manifest["source"]
            assert isinstance(source, dict)
            inventory = load_inventory(manifest_path.parent / str(source["file"]), str(source["format"]))
            annotate_workbook(Path(args.workbook), profiles, inventory, _validation_issues(report))
        return 0 if report["valid"] else 3
    except (AssistantError, ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer validate: {error}", file=sys.stderr)
        return 2


def _publish_files(output_dir: Path, files: dict[str, bytes]) -> None:
    """Stage a complete artifact set before exposing any final artifact."""
    if output_dir.exists() and any((output_dir / name).exists() for name in files):
        raise OSError(f"Output directory already contains generated artifacts: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = output_dir if output_dir.is_dir() else output_dir.parent
    staging = Path(tempfile.mkdtemp(prefix=".ontome-importer-", dir=staging_parent))
    try:
        for name, content in files.items():
            (staging / name).write_bytes(content)
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in sorted(files):
            os.replace(staging / name, output_dir / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _publish_compilation(files: dict[Path, bytes]) -> None:
    """Publish compiled artifacts together and restore every prior file on failure."""
    destinations = list(files)
    if len({path.resolve() for path in destinations}) != len(destinations):
        raise AssistantError("Compilation output paths must be distinct")
    temporaries: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: set[Path] = set()
    try:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporaries[path] = Path(temporary_name)
        for path in destinations:
            if path.exists():
                backup = path.with_name(f".{path.name}.backup")
                if backup.exists():
                    raise OSError(f"Stale compilation backup exists: {backup}")
                os.replace(path, backup)
                backups[path] = backup
            os.replace(temporaries[path], path)
            published.add(path)
        for backup in backups.values():
            backup.unlink(missing_ok=True)
    except Exception:
        for path in destinations:
            if path in backups:
                path.unlink(missing_ok=True)
                os.replace(backups[path], path)
            elif path in published:
                path.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporaries.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def _generation_issues(audit: dict[str, object], inventory: object) -> list[dict[str, object]]:
    triples = {item.id: item for item in inventory.triples}
    issues: list[dict[str, object]] = []
    for finding in audit.get("findings", []):
        status = str(finding.get("status", ""))
        if status not in {"blocked", "invalid", "configured"}:
            continue
        triple_ids = list(finding.get("triple_ids", []))
        external_uri = ""
        for triple_id in triple_ids:
            triple = triples.get(triple_id)
            if triple and triple.object.kind == "uri":
                external_uri = triple.object.value
                break
        resource = finding.get("resource", {})
        issues.append({
            "phase": "generation", "severity": "error", "sheet": "VALIDATION", "row": 0,
            "resource_uri": resource.get("value", "") if isinstance(resource, dict) else "",
            "mapping_rule": finding.get("mapping_rule", ""), "external_uri": external_uri,
            "triple_ids": triple_ids, "code": status, "message": finding.get("reason", "Generation is blocked."),
        })
    if not issues:
        issues.append({"phase": "generation", "severity": "info", "sheet": "VALIDATION", "row": 0, "code": "success", "message": "Generation completed successfully."})
    return issues


def _validation_issues(report: dict[str, object]) -> list[dict[str, object]]:
    issues = [
        {"phase": "validation", "severity": "error", "sheet": "VALIDATION", "row": 0, "code": check["name"], "message": check.get("message", str(check["name"]))}
        for check in report.get("checks", []) if not check["valid"]
    ]
    if not issues:
        issues.append({"phase": "validation", "severity": "info", "sheet": "VALIDATION", "row": 0, "code": "success", "message": "Validation completed successfully."})
    return issues


if __name__ == "__main__":
    raise SystemExit(main())
