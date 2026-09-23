"""Command-line interface for the OntoME importer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from ontome_importer import __version__
from ontome_importer.audit import audit_inventory
from ontome_importer.loader import RdfLoadError, load_inventory
from ontome_importer.mapping_assistant import AssistantError, annotate_workbook, check_workbook, compile_workbook, dump_yaml, export_workbook, refresh_workbook
from ontome_importer.profiles import ProfileError, load_audit_profiles, load_generation_profiles, verify_capability_xsd, verify_source_checksum
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
    audit = commands.add_parser("audit", help="Audit an RDF ontology against a mapping profile.")
    audit.add_argument("--manifest", required=True, help="Path to an import manifest 1.1.")
    audit.add_argument("--output-dir", required=True, help="Directory for audit outputs.")
    audit.add_argument("--generation-manifest", help="Generation manifest used to prefill an optional mapping workbook.")
    audit.add_argument("--workbook", help="New XLSX mapping workbook created with this audit.")
    generate = commands.add_parser("generate", help="Generate OntoME XML from resolved mappings.")
    generate.add_argument("--manifest", required=True, help="Path to an import manifest 1.0 with mapping profile 7.0.")
    generate.add_argument("--output-dir", required=True, help="Directory for generated XML and reports.")
    generate.add_argument("--workbook", help="Optional XLSX workbook to annotate with generation diagnostics.")
    validate = commands.add_parser("validate", help="Validate a generated OntoME XML import.")
    validate.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    validate.add_argument("--xml", required=True, help="Path to import.xml.")
    validate.add_argument("--trace", required=True, help="Path to generation-trace.json.")
    validate.add_argument("--audit", required=True, help="Path to generation-audit.json.")
    validate.add_argument("--output", required=True, help="Path for validation.json.")
    validate.add_argument("--workbook", help="Optional XLSX workbook to annotate with validation diagnostics.")
    assist = commands.add_parser("assist", help="Create and compile an XLSX mapping decision workbook.")
    assist_commands = assist.add_subparsers(dest="assist_command", required=True)
    export = assist_commands.add_parser("export", help="Create an XLSX workbook from a generation manifest.")
    export.add_argument("--manifest", required=True, help="Path to a generation import manifest.")
    export.add_argument("--output", required=True, help="New XLSX workbook path.")
    export.add_argument("--catalog", help="Optional RDF catalog used only to prefill exact external identifiers.")
    export.add_argument("--catalog-format", choices=("turtle", "rdfxml", "ntriples"), help="Format of the optional catalog RDF.")
    export.add_argument("--catalog-identifier-predicate", help="URI predicate holding one canonical identifier per catalog resource.")
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
        })
        print(f"ontome-importer audit: {'ready for generation' if report.to_dict()['strict_ok'] else 'decisions required'}; reports written to {args.output_dir}")
        return 0
    except (AssistantError, ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer audit: {error}", file=sys.stderr)
        return 2


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
            catalog_options = (args.catalog, args.catalog_format, args.catalog_identifier_predicate, args.catalog_namespace_id)
            if any(value is not None for value in catalog_options) and not all(value is not None for value in catalog_options):
                raise AssistantError("Catalog use requires --catalog, --catalog-format, --catalog-identifier-predicate and --catalog-namespace-id")
            catalog = load_inventory(Path(args.catalog), args.catalog_format) if args.catalog else None
            export_workbook(output, profiles, inventory, catalog, args.catalog_identifier_predicate, args.catalog_namespace_id)
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
