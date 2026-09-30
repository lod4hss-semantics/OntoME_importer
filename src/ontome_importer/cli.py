"""Command-line interface for the OntoME importer."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ontome_importer import __version__
from ontome_importer.audit import audit_inventory
from ontome_importer.constructs import OWL, RDFS, anonymous_domain_ranges
from ontome_importer.external_references import ExternalReferenceError, resolve_external_reference, validate_external_reference_configuration
from ontome_importer.loader import RdfLoadError, load_inventory
from ontome_importer.ontome_catalog import NamespaceBinding, OntoMECatalogError, fetch_namespace_catalog, parse_target_namespace, resolve_namespace_binding, catalog_identifiers
from ontome_importer.package_resources import package_resource_path
from ontome_importer.profiles import ProfileError, load_audit_profiles, load_generation_profiles, target_identity, validate_generation_mapping, verify_capability_xsd, verify_source_checksum
from ontome_importer.review import active_dependencies, build_review_queue, load_session, new_session, record_choice, refresh_session, save_session, status
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
    init.add_argument("--scope-uri-prefix", action="append", help="URI prefix to include in the import scope; repeat for multiple prefixes.")
    init.add_argument("--target-ontome-namespace", help="Existing OntoME namespace/version ID or page URL; prompted when omitted in a terminal.")
    init.add_argument("--target-namespace-uri", help="RDF namespace URI, if the source ontology does not specify it unambiguously.")
    init.add_argument("--target-label", help="Target namespace label, if unavailable from the RDF source.")
    init.add_argument("--target-label-lang", help="Language of --target-label (default: en).")
    init.add_argument("--target-version", help="Target version, if ontology versionInfo is missing or ambiguous.")
    audit = commands.add_parser("audit", help="Audit an RDF ontology and prepare a terminal review queue.")
    audit.add_argument("--manifest", required=True, help="Path to an import manifest 1.1.")
    audit.add_argument("--output-dir", required=True, help="Directory for audit outputs.")
    generate = commands.add_parser("generate", help="Generate OntoME XML from finalized publication decisions.")
    generate.add_argument("--manifest", required=True, help="Path to a finalized generation import manifest.")
    generate.add_argument("--output-dir", required=True, help="Directory for generated XML and reports.")
    validate = commands.add_parser("validate", help="Validate a generated OntoME XML import.")
    validate.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    validate.add_argument("--xml", required=True, help="Path to import.xml.")
    validate.add_argument("--trace", required=True, help="Path to generation-trace.json.")
    validate.add_argument("--audit", required=True, help="Path to generation-audit.json.")
    validate.add_argument("--output", required=True, help="Path for validation.json.")
    namespaces = commands.add_parser("namespaces", help="Resolve and cache versioned OntoME namespace catalogs.")
    namespace_commands = namespaces.add_subparsers(dest="namespace_command", required=True)
    fetch = namespace_commands.add_parser("fetch", help="Download the RDF catalog for an explicit OntoME namespace URI and version.")
    fetch.add_argument("--uri", required=True, help="External namespace URI from the RDF source.")
    fetch.add_argument("--version", required=True, help="Explicit OntoME namespace version to select.")
    fetch.add_argument("--output", required=True, help="New local RDF/XML cache path.")
    fetch.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    fetch.add_argument("--ontome-base-url", default="https://ontome.net", help="OntoME instance hosting this external namespace.")
    review = commands.add_parser("review", help="Review import decisions locally in the terminal.")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_start = review_commands.add_parser("start", help="Create or resume a local review session.")
    review_start.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    review_start.add_argument("--session", default="decisions/review.json", help="Path for the persistent review session.")
    review_start.add_argument("--assertion-policy", choices=("review", "strict"), help="Require explicit decisions on non-exportable RDF assertions (default: review).")
    review_resources = review_commands.add_parser("resources", help="Review pending classes and properties.")
    review_resources.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    review_resources.add_argument("--limit", type=int, help="Maximum pending resources to review in this run (default: all).")
    review_resources.add_argument("--resource", action="append", help="URI of a resource to review again; repeat to select several resources.")
    review_resources.add_argument("--action", choices=("publish", "exclude"), help="Apply one decision to the selected resources; displays the affected count before applying.")
    review_resources.add_argument("--reason", help="Required when excluding a resource or a batch.")
    review_assertions = review_commands.add_parser("assertions", help="Decide how to handle non-exportable RDF assertions.")
    review_assertions.add_argument("--manifest", help="Generation manifest; inferred from the review session if omitted.")
    review_assertions.add_argument("--session", default="decisions/review.json")
    review_assertions.add_argument("--finding", help="Review one specific audit finding instead of a group.")
    review_assertions.add_argument("--limit", type=int, help="Maximum groups to review in this run.")
    review_assertions.add_argument("--reviewer", help="Name recorded with assertion decisions (defaults to the current OS user).")
    review_references = review_commands.add_parser("references", help="Resolve or explicitly omit external relations used in the XML.")
    review_references.add_argument("--manifest", help="Generation manifest; inferred from the session if omitted.")
    review_references.add_argument("--session", default="decisions/review.json")
    review_references.add_argument("--limit", type=int, help="Maximum external terms to review.")
    review_references.add_argument("--uri", help="Review this external term again, including a previously ignored reference.")
    review_references.add_argument("--reviewer", help="Name recorded with omitted external relations.")
    review_references.add_argument("--ontome-base-url", default="https://ontome.net", help="OntoME instance for a chosen external catalog (only used when fetching).")
    review_required = review_commands.add_parser("required", help="Resolve missing mandatory fields or revise resource choices.")
    review_required.add_argument("--manifest", help="Generation manifest; inferred from the review session if omitted.")
    review_required.add_argument("--session", default="decisions/review.json")
    review_required.add_argument("--reviewer", help="Name recorded with editorial decisions.")
    review_status = review_commands.add_parser("status", help="Show local review progress.")
    review_status.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    review_check = review_commands.add_parser("check", help="Report decisions that still block finalization.")
    review_check.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
    review_check.add_argument("--manifest", help="Generation manifest; inferred from the review session if omitted.")
    review_finalize = review_commands.add_parser("finalize", help="Compile reviewed decisions into internal transformation profiles.")
    review_finalize.add_argument("--manifest", required=True, help="Path to the generation import manifest.")
    review_finalize.add_argument("--session", default="decisions/review.json", help="Path to the review session.")
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
    return _run_validate(args)


def _run_init(args: argparse.Namespace) -> int:
    try:
        target = args.target_ontome_namespace
        if target is None:
            if not sys.stdin.isatty():
                raise WorkspaceError("Provide --target-ontome-namespace (an existing OntoME namespace ID or URL) when running without a terminal")
            target = input("URL ou ID du namespace/version OntoME cible déjà créé : ").strip()
        namespace_id = parse_target_namespace(target)
        command = initialize_workspace(
            Path(args.source),
            Path(args.workspace),
            args.format,
            args.scope_uri_prefix or [],
            args.target_namespace_uri,
            args.target_label,
            args.target_label_lang,
            args.target_version,
            namespace_id,
        )
        print("Workspace created.")
        print(f"OntoME target namespace ID: {namespace_id}")
        print("Next command:")
        print(command)
        return 0
    except (WorkspaceError, OntoMECatalogError, RdfLoadError, OSError, ProfileError, EOFError) as error:
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
        _publish_files(Path(args.output_dir), {
            "inventory.json": inventory.to_json().encode("utf-8"),
            "audit.json": report.to_json().encode("utf-8"),
            "audit.md": report.to_markdown().encode("utf-8"),
            "review-queue.json": _json(build_review_queue(inventory, report)).encode("utf-8"),
        }, replace_managed={"inventory.json", "audit.json", "audit.md", "review-queue.json"})
        print(f"ontome-importer audit: {'ready for generation' if report.to_dict()['strict_ok'] else 'decisions required'}; reports written to {args.output_dir}")
        return 0
    except (ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer audit: {error}", file=sys.stderr)
        return 2


def _run_namespaces(args: argparse.Namespace) -> int:
    try:
        binding = resolve_namespace_binding(args.uri, args.version)
        output = Path(args.output)
        metadata = output.with_suffix(output.suffix + ".metadata.json")
        if output.exists() or metadata.exists():
            raise OSError(f"Namespace catalog output already exists: {output}")
        result = fetch_namespace_catalog(binding, output, args.timeout, args.ontome_base_url)
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
            queue = build_review_queue(inventory, report)
            if session_path.exists():
                session = load_session(session_path)
                if session.get("source_sha256") != inventory.source_sha256:
                    raise ValueError("Review session does not belong to this source")
                session["assertion_policy"] = args.assertion_policy or ("review" if session.get("assertion_policy") == "ignore-with-report" else session.get("assertion_policy", "review"))
                if refresh_session(session, queue, manifest_sha256=_hash_json(profiles.manifest)):
                    print("Review queue refreshed; existing resource decisions retained.")
                print(f"Review session resumed: {session_path}")
            else:
                session = new_session(queue, manifest_sha256=_hash_json(profiles.manifest), assertion_policy=args.assertion_policy or "review")
                save_session(session, session_path)
                print(f"Review session created: {session_path}")
            session["manifest_path"] = str(manifest_path.resolve())
            save_session(session, session_path)
            print(f"Assertion policy: {session.get('assertion_policy', 'strict')}")
            _print_review_status(status(session))
            print("Next command: ontome-importer review resources --session " + str(session_path))
            return 0
        session = load_session(session_path)
        if args.review_command == "status":
            _print_review_status(status(session))
            return 0
        if args.review_command == "assertions":
            manifest = Path(args.manifest or session.get("manifest_path") or session_path.parent.parent / "config/generation.yaml")
            profiles = load_generation_profiles(manifest)
            inventory = _review_inventory(manifest, profiles)
            mapping, registry = _compile_review(session, inventory, profiles)
            groups = _assertion_groups(session, audit_inventory(inventory, profiles.capability, {**mapping, "ignored_assertions": []}, registry), inventory, include_decided=bool(args.finding))
            if args.finding:
                matched = next((item for _, group in groups for item in group if item["id"] == args.finding), None)
                matches = [item for _, group in groups for item in group if matched and set(item["triple_ids"]) & set(matched["triple_ids"])]
                if not matches:
                    raise ValueError(f"No pending assertion finding: {args.finding}")
                groups = [(args.finding, matches)]
            if args.limit is not None and args.limit < 1:
                raise ValueError("--limit must be positive")
            for key, findings in groups[:args.limit]:
                print(f"\n{key}: {len({triple_id for item in findings for triple_id in item['triple_ids']})} assertion(s), {len(findings)} finding(s)\nConstructs: {', '.join(sorted({item['construct'] for item in findings}))}\nExample: {findings[0]['example']}")
                examples = [next((triple for triple in inventory.triples if triple.id == item["triple_ids"][0]), None) for item in findings]
                construct = findings[0]["construct"]
                fields = {"comment": "contextNote", "scope_note": "scopeNote", "example": "example", "disjointness": "disjointWith"}
                keep = construct in fields and all(item and item.predicate.value == examples[0].predicate.value and (construct == "disjointness" or item.object.kind == "literal" and item.object.language) for item in examples)
                transform = all(item and item.object.kind == "literal" and item.object.language for item in examples)
                print("Choices: " + ("[k]eep in OntoME, " if keep else "") + ("[t]ransform to a note, " if transform else "") + "[i]gnore with reason, [s]kip")
                answer = input("Decision: ").strip().lower()
                if answer not in {"i", "k" if keep else "", "t" if transform else ""}:
                    continue
                if answer == "i" and session.get("assertion_policy") == "strict":
                    print("Strict policy does not permit omitting assertions.")
                    continue
                reason = input("Reason for this decision: ").strip()
                if not reason:
                    print("A reason is required. No decision recorded.")
                    continue
                reviewer = (args.reviewer or getpass.getuser()).strip()
                if not reviewer:
                    raise ValueError("A reviewer name is required")
                now = datetime.now(timezone.utc).isoformat()
                for item in findings:
                    session["choices"].setdefault("assertions", {})[item["id"]] = {"action": {"i": "ignore", "k": "map", "t": "transform"}[answer], "reason": reason, "reviewer": reviewer, "at": now, "scope": "assertion" if args.finding else "group", "triple_ids": item["triple_ids"]}
                    if answer in {"k", "t"}:
                        triple = next(triple for triple in inventory.triples if triple.id == item["triple_ids"][0])
                        uri = (item.get("scope_resource") or item["resource"])["value"]
                        field = fields[construct] if answer == "k" else "contextNote"
                        session["choices"].setdefault("field_mappings", {})[f"{uri}|{triple.predicate.value}"] = {"uri": uri, "predicate": triple.predicate.value, "field": field, "construct": item["construct"], "action": "map" if answer == "k" else "transform", "reason": reason, "reviewer": reviewer, "at": now}
                session["journal"].append({"action": {"i": "ignore_assertions", "k": "map_assertions", "t": "transform_assertions"}[answer], "at": now, "reviewer": reviewer, "scope": key, "finding_ids": [item["id"] for item in findings], "reason": reason})
                save_session(session, session_path)
            print(f"Assertion groups requiring a decision: {len(_assertion_groups(session, audit_inventory(inventory, profiles.capability, {**mapping, 'ignored_assertions': []}, registry), inventory))}")
            print("Next command: ontome-importer review references --session " + str(session_path))
            return 0
        if args.review_command == "references":
            manifest = Path(args.manifest or session.get("manifest_path") or session_path.parent.parent / "config/generation.yaml")
            profiles = load_generation_profiles(manifest)
            inventory = _review_inventory(manifest, profiles)
            mapping, registry = _compile_review(session, inventory, profiles)
            report = audit_inventory(inventory, profiles.capability, {**mapping, "ignored_assertions": []}, registry)
            dependencies = [item for item in active_dependencies(session) if not item.get("catalog_paths")]
            if args.uri:
                dependencies = [item for item in session["choices"]["dependencies"] if item["uri"] == args.uri and item["uri"] in {value["uri"] for value in session["queue"]["external_dependencies"]}]
                if not dependencies:
                    raise ValueError(f"No external relation to review for {args.uri}")
            if args.limit is not None and args.limit < 1:
                raise ValueError("--limit must be positive")
            for dependency in dependencies[:args.limit]:
                uri = dependency["uri"]
                print(f"\nExternal term: {uri}")
                print("Used by: " + ", ".join(item.subject.value for item in inventory.triples if item.object.kind == "uri" and item.object.value == uri and session["choices"]["resources"].get(item.subject.value) == "publish"))
                answer = input("[i]gnore these relations, [l]ocal catalog, [f]etch catalog, [s]kip: ").strip().lower()
                if answer == "i":
                    if session.get("assertion_policy") == "strict":
                        print("Strict policy does not permit omitting relations.")
                        continue
                    reason = input("Reason for omitting these relations: ").strip()
                    if not reason:
                        print("A reason is required.")
                        continue
                    reviewer = (args.reviewer or getpass.getuser()).strip()
                    now = datetime.now(timezone.utc).isoformat()
                    linked = {item.id for item in inventory.triples if item.object.kind == "uri" and item.object.value == uri and session["choices"]["resources"].get(item.subject.value) == "publish"}
                    findings = [item for item in report.findings if item["status"] in {"blocked", "mapped"} and len(item["triple_ids"]) == 1 and item["triple_ids"][0] in linked]
                    for item in findings:
                        session["choices"].setdefault("assertions", {})[item["id"]] = {"action": "ignore", "reason": reason, "reviewer": reviewer, "at": now, "scope": "reference", "triple_ids": item["triple_ids"]}
                    session["choices"].setdefault("references", {})[uri] = {"action": "ignore", "reason": reason, "reviewer": reviewer, "at": now}
                    session["journal"].append({"action": "ignore_reference", "at": now, "uri": uri, "finding_ids": [item["id"] for item in findings], "reason": reason, "reviewer": reviewer})
                    save_session(session, session_path)
                elif answer in {"l", "f"}:
                    namespace_uri = input("Exact RDF namespace URI of the external term: ").strip()
                    namespace_id = parse_target_namespace(input("OntoME namespace ID: ").strip())
                    version = input("Version (leave empty if unversioned): ").strip() or None
                    if not uri.startswith(namespace_uri):
                        raise ValueError(f"External term {uri} is not in the selected namespace {namespace_uri}")
                    catalog = session_path.parent.parent / "references/ontome" / f"namespace-{namespace_id}.rdf"
                    if answer == "l":
                        local_path = Path(input("Path to the RDF/XML export: ").strip())
                        terms = catalog_identifiers(local_path)
                        if uri not in terms:
                            raise ValueError(f"Catalog does not contain an exact identifier for {uri}")
                        catalog.parent.mkdir(parents=True, exist_ok=True)
                        if catalog.exists() and catalog.read_bytes() != local_path.read_bytes():
                            raise ValueError(f"Different catalog already cached at {catalog}")
                        catalog.write_bytes(local_path.read_bytes())
                        metadata = {"uri": namespace_uri, "version": version, "ontome_namespace_id": namespace_id, "url": local_path.resolve().as_uri(), "sha256": hashlib.sha256(catalog.read_bytes()).hexdigest()}
                    else:
                        if not catalog.exists():
                            temporary_catalog = catalog.with_suffix(".rdf.download")
                            if temporary_catalog.exists():
                                raise ValueError(f"Incomplete catalog download already exists: {temporary_catalog}")
                            try:
                                metadata = fetch_namespace_catalog(NamespaceBinding(namespace_uri, version, namespace_id), temporary_catalog, base_url=args.ontome_base_url)
                                if uri not in catalog_identifiers(temporary_catalog):
                                    raise ValueError(f"OntoME catalog does not contain an exact identifier for {uri}")
                                os.replace(temporary_catalog, catalog)
                            finally:
                                temporary_catalog.unlink(missing_ok=True)
                        else:
                            metadata = json.loads(catalog.with_suffix(".rdf.metadata.json").read_text(encoding="utf-8"))
                            if uri not in catalog_identifiers(catalog):
                                raise ValueError(f"OntoME catalog does not contain an exact identifier for {uri}")
                        metadata["catalog"] = str(catalog)
                    catalog.with_suffix(".rdf.metadata.json").write_text(_json(metadata), encoding="utf-8")
                    record_choice(session, "dependency", uri, identifier=str(namespace_id), catalog_paths=[str(catalog)])
                    session["choices"].setdefault("references", {})[uri] = {"action": "reference", "namespace_id": namespace_id}
                    for finding in report.findings:
                        if len(finding["triple_ids"]) == 1 and any(triple.id == finding["triple_ids"][0] and triple.object.kind == "uri" and triple.object.value == uri for triple in inventory.triples):
                            decision = session["choices"].get("assertions", {}).get(finding["id"])
                            if decision and decision["scope"] == "reference":
                                session["choices"]["assertions"].pop(finding["id"])
                    save_session(session, session_path)
            _print_review_status(status(session))
            print("Next command: ontome-importer review required --session " + str(session_path))
            return 0
        if args.review_command == "required":
            manifest = Path(args.manifest or session.get("manifest_path") or session_path.parent.parent / "config/generation.yaml")
            profiles = load_generation_profiles(manifest)
            inventory = _review_inventory(manifest, profiles)
            mapping, registry = _compile_review(session, inventory, profiles)
            report = audit_inventory(inventory, profiles.capability, mapping, registry)
            for item in report.findings:
                uri = (item.get("scope_resource") or item["resource"])["value"]
                if item["construct"] != "missing_label_language" or session["choices"]["resources"].get(uri) != "publish" or mapping.get("ignored_assertions") and item["status"] == "excluded":
                    continue
                if session["choices"].get("required", {}).get(uri, {}).get("label_language"):
                    continue
                print(f"\nA label of {uri} has no language: {item['example']}")
                language = input("Language to assign (empty to leave pending): ").strip()
                if language:
                    if not re.fullmatch(r"[A-Za-z]{2,3}([_-][A-Za-z0-9]+)*", language):
                        raise ValueError("Language tag is invalid")
                    reason = input("Reason for assigning this language: ").strip()
                    if not reason:
                        print("A reason is required. No decision recorded.")
                        continue
                    record = session["choices"].setdefault("required", {}).setdefault(uri, {})
                    record.update(label_language=language, language_rationale=reason, reviewer=args.reviewer or getpass.getuser(), at=datetime.now(timezone.utc).isoformat())
                    session["journal"].append({"action": "assign_label_language", "uri": uri, "language": language, "reason": reason, "reviewer": record["reviewer"], "at": record["at"]})
                    save_session(session, session_path)
            mapping, registry = _compile_review(session, inventory, profiles)
            report = audit_inventory(inventory, profiles.capability, mapping, registry)
            owl_sources = anonymous_domain_ranges(inventory)
            local_classes = {item.id.value for item in inventory.resources if item.id.kind == "uri" and any(term.value in {f"{OWL}Class", f"{RDFS}Class"} for term in item.types) and session["choices"]["resources"].get(item.id.value) == "publish"}
            for (field, motifs), uris in _owl_review_groups(session, inventory):
                uris = [uri for uri in uris if session["choices"]["resources"].get(uri) == "publish"]
                if not uris:
                    continue
                print(f"\n{field} / {', '.join(motifs)}: {len(uris)} published property/properties")
                for uri in uris:
                    print(f"  {uri}")
                answer = input("[b]atch exclude all, [r]eview individually, [s]kip group: ").strip().lower()
                if answer == "b":
                    reason = input("Reason for excluding these properties: ").strip()
                    if not reason:
                        print("A reason is required. No decisions recorded.")
                        continue
                    if input(f"Confirm exclusion of {len(uris)} properties? [y/N]: ").strip().lower() != "y":
                        continue
                    for uri in uris:
                        _exclude_review_resource(session, uri, reason)
                    save_session(session, session_path)
                elif answer == "r":
                    for uri in uris:
                        if session["choices"]["resources"].get(uri) != "publish":
                            continue
                        source = owl_sources[(uri, field)]
                        if session["choices"].get("required", {}).get(uri, {}).get(field):
                            continue
                        print(f"\n{uri}: {field} uses {', '.join(source['motifs'])} (source assertion {source['root_triple_id']}).")
                        print("Named OWL members: " + (", ".join(source["members"]) or "none"))
                        if not local_classes:
                            print("No named local published class is available; an external URI needs a configured reference.")
                        decision = input("[p]ublish with editorial replacement, [e]xclude property, [s]kip: ").strip().lower()
                        if decision == "e":
                            reason = input("Reason for excluding the property: ").strip()
                            if reason:
                                _exclude_review_resource(session, uri, reason)
                                save_session(session, session_path)
                            else:
                                print("A reason is required.")
                        elif decision == "p":
                            ref = input("Exact URI of the replacement class: ").strip()
                            try:
                                resolved = _review_reference(ref, session, inventory, mapping, registry)
                            except ValueError as error:
                                print(error)
                                continue
                            print(f"The XML {field} will reference {ref} ({resolved}); the source OWL expression will not be exported.")
                            if input("Confirm this replacement? [y/N]: ").strip().lower() != "y":
                                continue
                            reason = input("Editorial rationale for this change: ").strip()
                            if not reason:
                                print("A rationale is required.")
                                continue
                            session["choices"].setdefault("required", {}).setdefault(uri, {})[field] = {"reference_uri": ref, "rationale": reason, "reviewer": args.reviewer or getpass.getuser(), "at": datetime.now(timezone.utc).isoformat(), "source_triple_ids": source["triple_ids"], "root_triple_id": source["root_triple_id"]}
                            session["journal"].append({"action": "replace_owl_domain_range", "uri": uri, "field": field, "reference_uri": ref, "reason": reason, "source_triple_ids": source["triple_ids"], "reviewer": args.reviewer or getpass.getuser(), "at": datetime.now(timezone.utc).isoformat()})
                            save_session(session, session_path)
            mapping, registry = _compile_review(session, inventory, profiles)
            report = audit_inventory(inventory, profiles.capability, mapping, registry)
            triples = {(triple.subject.value, triple.predicate.value) for triple in inventory.triples}
            for item in report.findings:
                uri = (item.get("scope_resource") or item["resource"])["value"]
                if item["construct"] not in {"missing_domain", "missing_range"} or session["choices"]["resources"].get(uri) != "publish":
                    continue
                field = "hasDomain" if item["construct"] == "missing_domain" else "hasRange"
                predicate = "http://www.w3.org/2000/01/rdf-schema#" + ("domain" if field == "hasDomain" else "range")
                if (uri, predicate) in triples:
                    continue
                if session["choices"].get("required", {}).get(uri, {}).get(field):
                    continue
                print(f"\n{uri} lacks a {field} required by OntoME XML.")
                answer = input("[r]eference to a published class, [e]xclude property, [s]kip: ").strip().lower()
                if answer == "e":
                    reason = input("Reason for excluding the property: ").strip()
                    if not reason:
                        print("A reason is required.")
                        continue
                    _exclude_review_resource(session, uri, reason)
                elif answer == "r":
                    ref = input("Exact URI of the published class to use: ").strip()
                    try:
                        _review_reference(ref, session, inventory, mapping, registry)
                    except ValueError as error:
                        print(error)
                        continue
                    reason = input("Editorial rationale: ").strip()
                    if not reason:
                        print("A rationale is required.")
                        continue
                    session["choices"].setdefault("required", {}).setdefault(uri, {})[field] = {"reference_uri": ref, "rationale": reason, "reviewer": args.reviewer or getpass.getuser(), "at": datetime.now(timezone.utc).isoformat()}
                else:
                    continue
                save_session(session, session_path)
            _print_review_status(status(session))
            print("Next command: ontome-importer review check --session " + str(session_path))
            return 0
        if args.review_command == "check":
            review_status = status(session)
            if session.get("assertion_policy") == "strict" and _active_ignored_decisions(session):
                print("Review incomplete: strict policy conflicts with existing ignored assertions. Reconsider these decisions in review assertions/references.")
                return 3
            pending = review_status["resources"]["pending"]
            if pending:
                print(f"Review incomplete: {pending} resource decisions pending. Run review resources.")
                return 3
            if not review_status["resources"]["publish"]:
                print("Review incomplete: no classes or properties selected for publication.")
                return 3
            manifest = Path(args.manifest or session.get("manifest_path") or session_path.parent.parent / "config/generation.yaml")
            profiles = load_generation_profiles(manifest)
            inventory = _review_inventory(manifest, profiles)
            for (field, motifs), uris in _owl_review_groups(session, inventory):
                print(f"OWL review: {field} / {', '.join(motifs)}: {len(uris)} properties: {', '.join(uris)}. Run review required.")
            mapping, registry = _compile_review(session, inventory, profiles)
            groups = _assertion_groups(session, audit_inventory(inventory, profiles.capability, {**mapping, "ignored_assertions": []}, registry), inventory)
            if groups:
                print(f"Review incomplete: {len(groups)} assertion groups require decisions. Run review assertions.")
                for name, values in groups:
                    print(f"  {name}: {len(values)} finding(s)")
                return 3
            dependencies = review_status["dependencies"]
            if dependencies["configured"] != dependencies["total"]:
                print(f"Review incomplete: {dependencies['configured']}/{dependencies['total']} references configured. Run review references.")
                _print_unresolved_dependencies(session)
                return 3
            blockers = _preflight(inventory, profiles, mapping, registry)
            if blockers:
                _print_review_blockers(blockers)
                return 3
            print("Review is ready for generation.")
            print(f"Next command: ontome-importer review finalize --manifest {manifest} --session {session_path}")
            return 0
        if args.review_command == "finalize":
            manifest_path = Path(args.manifest)
            profiles = load_generation_profiles(manifest_path)
            review_status = status(session)
            if session.get("assertion_policy") == "strict" and _active_ignored_decisions(session):
                raise ValueError("Strict policy conflicts with ignored assertions; review them before finalizing")
            if review_status["resources"]["pending"] or not review_status["resources"]["publish"]:
                raise ValueError("Review is incomplete; run review check for remaining decisions")
            inventory = _review_inventory(manifest_path, profiles)
            report = audit_inventory(inventory, profiles.capability, profiles.mapping, profiles.namespace_registry)
            if refresh_session(session, build_review_queue(inventory, report), manifest_sha256=_hash_json(profiles.manifest)):
                save_session(session, session_path)
                raise ValueError("Review queue changed; decisions were retained. Run review start to configure new dependencies")
            mapping, registry = _compile_review(session, inventory, profiles)
            if _assertion_groups(session, audit_inventory(inventory, profiles.capability, {**mapping, "ignored_assertions": []}, registry), inventory):
                raise ValueError("Assertion decisions are incomplete; run review assertions")
            if review_status["dependencies"]["configured"] != review_status["dependencies"]["total"]:
                raise ValueError("External references are unresolved; run review references")
            blockers = _preflight(inventory, profiles, mapping, registry)
            if blockers:
                _print_review_blockers(blockers)
                raise ValueError("Review is not ready; resolve the reported blockers before finalizing")
            _publish_compilation({
                manifest_path.parent / "profiles" / "mapping-generation.yaml": _dump_yaml(mapping),
                manifest_path.parent / "profiles" / "namespace-registry.yaml": _dump_yaml(registry),
            })
            print("Review finalized. Internal transformation profiles were updated.")
            print(f"Reviewed omissions: {len(mapping.get('ignored_assertions', []))} findings recorded in the generation audit.")
            print(f"Next command: ontome-importer generate --manifest {manifest_path} --output-dir {manifest_path.parent.parent / 'build/import'}")
            return 0
        for uri in args.resource or []:
            if uri not in session["choices"]["resources"]:
                raise ValueError(f"Unknown review resource: {uri}")
        if args.limit is not None and args.limit < 1:
            raise ValueError("--limit must be positive")
        pending = list(dict.fromkeys(args.resource)) if args.resource else [uri for uri, choice in session["choices"]["resources"].items() if choice == "pending"]
        if args.action and args.action == "exclude" and not args.reason:
            raise ValueError("Exclusion requires --reason")
        selected = pending if args.resource else pending[:args.limit]
        if args.action:
            print(f"Apply {args.action} to {len(selected)} resource(s)")
            for uri in selected:
                resource = _review_resource(session, uri)
                if args.action == "publish" and not resource["publishable"]:
                    raise ValueError(f"Cannot publish unsupported RDF resource type: {uri}")
            for uri in selected:
                record_choice(session, "resource", uri, args.action)
                if args.action == "exclude":
                    session["choices"].setdefault("resource_reasons", {})[uri] = args.reason
                    session["journal"][-1]["reason"] = args.reason
            save_session(session, session_path)
            _print_review_status(status(session))
            if status(session)["resources"]["pending"] == 0:
                print("Next command: ontome-importer review assertions --session " + str(session_path))
            return 0
        for uri in selected:
            resource = _review_resource(session, uri)
            print(f"\n{resource['kind']} {uri}\nLabels: {resource['labels'] or 'none'}\nFindings: {resource['finding_count']}")
            for (category, construct), count in resource["finding_summary"]:
                print(f"  {category} / {construct}: {count}")
            answer = input("[p]ublish, [e]xclude, [s]kip: ").strip().lower()
            choice = {"p": "publish", "e": "exclude", "s": "pending"}.get(answer)
            if choice is None:
                print("No decision recorded.")
                continue
            if choice == "publish" and not resource["publishable"]:
                print("This RDF resource type cannot be serialized as an OntoME class or property. Exclude it or leave it pending.")
                continue
            if choice == "exclude":
                reason = input("Reason for excluding the resource: ").strip()
                if not reason:
                    print("A reason is required. No decision recorded.")
                    continue
                session["choices"].setdefault("resource_reasons", {})[uri] = reason
            record_choice(session, "resource", uri, choice)
            if choice == "exclude":
                session["journal"][-1]["reason"] = reason
            save_session(session, session_path)
        _print_review_status(status(session))
        if status(session)["resources"]["pending"] == 0:
            print("Next command: ontome-importer review assertions --session " + str(session_path))
        return 0
    except (OntoMECatalogError, ProfileError, RdfLoadError, OSError, ValueError) as error:
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
            summary = Counter((item["category"], item["construct"]) for item in match["findings"])
            kinds = {item["value"] for item in match["types"]}
            publishable = bool(kinds & {"http://www.w3.org/2002/07/owl#Class", "http://www.w3.org/2000/01/rdf-schema#Class", "http://www.w3.org/2002/07/owl#ObjectProperty", "http://www.w3.org/2002/07/owl#DatatypeProperty", "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"})
            return {"kind": "Class" if kind == "classes" else "Property", "labels": labels, "finding_count": len(match["findings"]), "finding_summary": sorted(summary.items()), "publishable": publishable}
    raise ValueError(f"Review resource is missing from the queue: {uri}")


def _exclude_review_resource(session: dict[str, object], uri: str, reason: str) -> None:
    record_choice(session, "resource", uri, "exclude")
    session["choices"].setdefault("resource_reasons", {})[uri] = reason
    session["journal"][-1]["reason"] = reason


def _owl_review_groups(session: dict[str, object], inventory: object) -> list[tuple[tuple[str, tuple[str, ...]], list[str]]]:
    grouped: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    properties = {item.id.value for item in inventory.resources if item.id.kind == "uri" and any(term.value in {f"{OWL}ObjectProperty", f"{OWL}DatatypeProperty", "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"} for term in item.types)}
    for (uri, field), source in anonymous_domain_ranges(inventory).items():
        if uri not in properties or session["choices"]["resources"].get(uri) != "publish" or session["choices"].get("required", {}).get(uri, {}).get(field):
            continue
        grouped.setdefault((field, tuple(source["motifs"])), set()).add(uri)
    return [(key, sorted(uris)) for key, uris in sorted(grouped.items())]


def _review_reference(ref: str, session: dict[str, object], inventory: object, mapping: dict[str, object], registry: dict[str, object]) -> str:
    resource = next((item for item in inventory.resources if item.id.kind == "uri" and item.id.value == ref), None)
    if ref in session["choices"]["resources"]:
        if resource and session["choices"]["resources"][ref] == "publish" and any(term.value in {f"{OWL}Class", f"{RDFS}Class"} for term in resource.types):
            return "local published class"
        raise ValueError(f"Replacement {ref} must be a published local class.")
    try:
        resolved = resolve_external_reference(ref, mapping, registry)
    except ExternalReferenceError as error:
        _, catalogs = _review_catalogs(session["choices"])
        matches = [(item["ontome_namespace_id"], terms[ref]) for item, terms in catalogs if ref in terms]
        if len(matches) == 1:
            return f"namespace {matches[0][0]}, identifier {matches[0][1]}"
        raise ValueError(f"Reference {ref} must be a published local class or have an explicit external reference/rule: {error}") from error
    return f"namespace {resolved.reference_namespace}, identifier {resolved.identifier}"


def _print_review_status(value: dict[str, object]) -> None:
    resources = value["resources"]
    dependencies = value["dependencies"]
    print("Review status")
    print(f"Resources: {resources['publish']} publish, {resources['exclude']} exclude, {resources['pending']} pending.")
    print(f"Dependencies: {dependencies['configured']}/{dependencies['total']} configured.")


def _print_unresolved_dependencies(session: dict[str, object]) -> None:
    queue = session["queue"]
    assert isinstance(queue, dict)
    external = {item["uri"]: item.get("sources", []) for item in queue.get("external_dependencies", [])}
    for dependency in active_dependencies(session):
        if dependency.get("catalog_paths"):
            continue
        print(f"Unresolved external term: {dependency['uri']}")
        for uri in external.get(dependency["uri"], []):
            if session["choices"]["resources"].get(uri) != "exclude":
                print(f"  Used by: {uri}")


def _review_inventory(manifest_path: Path, profiles: object) -> object:
    source = profiles.manifest["source"]
    assert isinstance(source, dict)
    path = manifest_path.parent / str(source["file"])
    verify_source_checksum(profiles.manifest, path)
    return load_inventory(path, str(source["format"]))


def _active_ignored_decisions(session: dict[str, object]) -> bool:
    published = {uri for uri, choice in session["choices"]["resources"].items() if choice == "publish"}
    ignored = {finding_id for finding_id, choice in session["choices"].get("assertions", {}).items() if choice.get("action") == "ignore"}
    return any(item["id"] in ignored and (item.get("scope_resource") or item["resource"])["value"] in published for group in session["queue"]["resources"].values() for resource in group for item in resource["findings"])


def _preflight(inventory: object, profiles: object, mapping: dict[str, object], registry: dict[str, object]) -> list[dict[str, object]]:
    result = resolve_generation(inventory, profiles.manifest, profiles.capability, mapping, registry)
    if result.generation is None:
        return [item for item in result.audit["findings"] if item["status"] in {"blocked", "invalid", "configured"}]
    try:
        write_xml(result.generation, profiles.capability, verify_capability_xsd(profiles.capability), inventory.source_sha256, target_identity(profiles.manifest))
    except XmlGenerationError as error:
        return [{"reason": str(error), "category": "xml_generation", "resource": {"value": "namespace"}}]
    return []


def _print_review_blockers(blockers: list[dict[str, object]]) -> None:
    grouped: dict[tuple[str, str], set[str]] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for item in blockers:
        key = (str(item.get("category", "unknown")), str(item.get("reason") or item.get("decision_needed") or item.get("construct") or "Needs review"))
        grouped.setdefault(key, set()).add(str((item.get("scope_resource") or item.get("resource") or {}).get("value", "")))
        counts[key] += 1
    print(f"Review cannot generate XML: {len(blockers)} blocking findings.")
    for (category, reason), resources in sorted(grouped.items()):
        print(f"  {category}: {reason} ({counts[(category, reason)]} finding(s), {len(resources)} URI(s); first: {', '.join(sorted(resources)[:3])})")
    print("Run review assertions, review references or review required to resolve these issues; a mandatory XML field cannot be ignored.")


def _assertion_groups(session: dict[str, object], report: object, inventory: object, *, include_decided: bool = False) -> list[tuple[str, list[dict[str, object]]]]:
    from ontome_importer.review import RELATION_PREDICATES

    published = {uri for uri, choice in session["choices"]["resources"].items() if choice == "publish"}
    decisions = session["choices"].get("assertions", {})
    triples = {triple.id: triple for triple in inventory.triples}
    groups: dict[str, list[dict[str, object]]] = {}
    for item in report.findings:
        if item["status"] not in ({"blocked", "mapped"} if include_decided else {"blocked"}) or not item["triple_ids"] or (item["id"] in decisions and not include_decided):
            continue
        if item["construct"] == "missing_label_language":
            continue
        if (item.get("scope_resource") or item["resource"])["value"] not in published:
            continue
        first = triples[item["triple_ids"][0]]
        if first.predicate.value in RELATION_PREDICATES and item["construct"] in {"missing_external_reference", "unknown_namespace"}:
            continue
        key = first.predicate.value
        groups.setdefault(key, []).append(item)
    return sorted(groups.items())


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
            rule["reason"] = choices.get("resource_reasons", {}).get(resource.id.value, "Excluded during terminal review.")
        else:
            rule["action"] = "map"
            if types & {f"{OWL}Class", f"{RDFS}Class"}:
                target = {"entity_kind": "class"}
            elif f"{OWL}ObjectProperty" in types:
                target = {"entity_kind": "property", "property_kind": "object"}
            elif f"{OWL}DatatypeProperty" in types:
                target = {"entity_kind": "property", "property_kind": "datatype"}
            else:
                target = {"entity_kind": "property", "property_kind": "rdf"}
            prefix = resource.id.value.rsplit("#", 1)[0] + "#" if "#" in resource.id.value else resource.id.value.rsplit("/", 1)[0] + "/"
            target["identifier_in_namespace"] = {"source": "uri_suffix", "strip_prefix": prefix}
            target["label_predicates"] = [f"{RDFS}label"]
            language = choices.get("required", {}).get(resource.id.value, {}).get("label_language")
            if language:
                target["default_label_language"] = language
            target["identifier_in_uri"] = "source_uri"
            if target["entity_kind"] == "class":
                target["relations"] = [{"field": "subClassOf", "predicate": f"{RDFS}subClassOf"}, {"field": "equivalentClass", "predicate": f"{OWL}equivalentClass"}]
            else:
                target["relations"] = [{"field": "subPropertyOf", "predicate": f"{RDFS}subPropertyOf"}, {"field": "equivalentProperty", "predicate": f"{OWL}equivalentProperty"}, {"field": "inverseOf", "predicate": f"{OWL}inverseOf"}]
                target["domain_range"] = {"domain_predicate": f"{RDFS}domain", "range_predicate": f"{RDFS}range"}
            for decision in choices.get("field_mappings", {}).values():
                if decision["uri"] != resource.id.value:
                    continue
                if decision["field"] == "disjointWith":
                    relation = {"field": "disjointWith", "predicate": decision["predicate"]}
                    if relation not in target["relations"]:
                        target["relations"].append(relation)
                else:
                    text_field = {"field": decision["field"], "predicates": [decision["predicate"]]}
                    if text_field not in target.setdefault("text_fields", []):
                        target["text_fields"].append(text_field)
            rule["target"] = target
        rules.append(rule)
    registry, catalog_terms = _review_catalogs(choices)
    configured_registry = profiles.namespace_registry
    for namespace in configured_registry["namespaces"]:
        existing = next((item for item in registry["namespaces"] if item["ontome_namespace_id"] == namespace["ontome_namespace_id"]), None)
        if existing is not None and existing != namespace:
            raise ValueError(f"Conflicting reference namespace configuration: {namespace['ontome_namespace_id']}")
        if existing is None:
            registry["namespaces"].append(namespace)
    external_references = {item["uri"]: item for item in profiles.mapping.get("external_references", [])}
    published = {uri for uri, choice in resource_choices.items() if choice == "publish"}
    ignored_relation_triples = {decision["triple_ids"][0] for decision in choices.get("assertions", {}).values() if decision.get("action") == "ignore" and len(decision.get("triple_ids", [])) == 1}
    relation_predicates = {f"{RDFS}subClassOf", f"{RDFS}subPropertyOf", f"{RDFS}domain", f"{RDFS}range", f"{OWL}equivalentClass", f"{OWL}equivalentProperty", f"{OWL}inverseOf", f"{OWL}disjointWith"}
    for triple in inventory.triples:
        if triple.subject.value not in published or triple.object.kind != "uri" or triple.object.value in published or triple.predicate.value not in relation_predicates:
            continue
        if triple.id in ignored_relation_triples:
            continue
        if choices.get("references", {}).get(triple.object.value, {}).get("action") == "ignore":
            continue
        matches = [(item, _resolve_catalog_identifier(triple.object.value, terms)) for item, terms in catalog_terms]
        matches = [(item, identifier) for item, identifier in matches if identifier]
        if len(matches) != 1:
            continue
        item, identifier = matches[0]
        external_references.setdefault(triple.object.value, {"uri": triple.object.value, "reference_namespace": item["ontome_namespace_id"], "identifier": identifier})
    for fields in choices.get("required", {}).values():
        for field in ("hasDomain", "hasRange"):
            ref = fields.get(field, {}).get("reference_uri")
            if ref and ref not in published and ref not in external_references:
                matches = [(item, _resolve_catalog_identifier(ref, terms)) for item, terms in catalog_terms]
                matches = [(item, identifier) for item, identifier in matches if identifier]
                if len(matches) == 1:
                    item, identifier = matches[0]
                    external_references[ref] = {"uri": ref, "reference_namespace": item["ontome_namespace_id"], "identifier": identifier}
    mapping = {"format_version": "7.0", "scope": scope, "rules": rules, "external_references": list(external_references.values()), "external_reference_rules": profiles.mapping.get("external_reference_rules", []), "editorial_exceptions": [], "decisions": []}
    for uri, fields in choices.get("required", {}).items():
        if resource_choices.get(uri) == "publish" and fields.get("label_language"):
            mapping["decisions"].append({"id": "review-label-" + hashlib.sha256(uri.encode()).hexdigest()[:12], "resource_uri": uri, "construct": "missing_label_language", "action": "transform", "status": "approved", "rationale": fields["language_rationale"], "approved_by": fields["reviewer"], "approved_at": fields["at"][:10], "decision_reference": "review session label language"})
    for decision in choices.get("field_mappings", {}).values():
        uri = decision["uri"]
        if resource_choices.get(uri) != "publish":
            continue
        key = f"{uri}|{decision['construct']}"
        if any(item["resource_uri"] == uri and item["construct"] == decision["construct"] for item in mapping["decisions"]):
            continue
        mapping["decisions"].append({"id": "review-field-" + hashlib.sha256(key.encode()).hexdigest()[:12], "resource_uri": uri, "construct": decision["construct"], "action": decision["action"], "status": "approved", "rationale": decision["reason"], "approved_by": decision["reviewer"], "approved_at": decision["at"][:10], "decision_reference": "review session assertion mapping"})
    for uri, fields in choices.get("required", {}).items():
        if resource_choices.get(uri) != "publish":
            continue
        for field in ("hasDomain", "hasRange"):
            if field not in fields:
                continue
            decision = fields[field]
            mapping["editorial_exceptions"].append({"id": "review-exception-" + hashlib.sha256(f"{uri}|{field}".encode()).hexdigest()[:12], "resource_uri": uri, "field": field, "reference_uri": decision["reference_uri"], "status": "approved", "rationale": decision["rationale"], "approved_by": decision["reviewer"], "approved_at": decision["at"][:10], "decision_reference": "review session required field", **({"source_triple_ids": decision["source_triple_ids"]} if decision.get("source_triple_ids") else {})})
    report = audit_inventory(inventory, profiles.capability, mapping, registry)
    decisions = choices.get("assertions", {})
    mapping["ignored_assertions"] = [
        {"finding_id": item["id"], "triple_ids": item["triple_ids"], "reason": decision["reason"], "reviewer": decision["reviewer"], "decided_at": decision["at"], "scope": decision["scope"]}
        for item in report.findings
        if (decision := decisions.get(item["id"], {})).get("action") == "ignore"
        and item["triple_ids"] and (item.get("scope_resource") or item["resource"])["value"] in published
    ]
    _validate_compiled_profiles(mapping, registry, profiles)
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
            if (metadata.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
                or metadata.get("ontome_namespace_id") != int(dependency["id"])
                or not dependency["uri"].startswith(str(metadata.get("uri", "")))):
                raise ValueError(f"Selected external catalog differs from its verified metadata: {path}")
            item = {"uri": metadata["uri"], "version": metadata["version"], "ontome_namespace_id": metadata["ontome_namespace_id"], "status": "active", "source": metadata["url"]}
            if not any(value["ontome_namespace_id"] == item["ontome_namespace_id"] for value in namespaces):
                namespaces.append(item)
                catalogs.append((item, _catalog_identifiers(load_inventory(path, "rdfxml"), "http://www.w3.org/2004/02/skos/core#notation")))
    return {"format_version": "1.1", "namespaces": namespaces}, catalogs


def _catalog_identifiers(catalog: object, predicate: str) -> dict[str, str]:
    values: dict[str, set[str]] = {}
    for triple in catalog.triples:
        if triple.predicate.value == predicate and triple.subject.kind == "uri" and triple.object.kind == "literal" and triple.object.value:
            values.setdefault(triple.subject.value, set()).add(triple.object.value)
    ambiguous = sorted(uri for uri, identifiers in values.items() if len(identifiers) > 1)
    if ambiguous:
        raise ValueError(f"Catalog identifier predicate is ambiguous for: {ambiguous[0]}")
    return {uri: next(iter(identifiers)) for uri, identifiers in values.items()}


def _resolve_catalog_identifier(source_uri: str, catalog_identifiers: dict[str, str]) -> str | None:
    """Never resolve a foreign URI using another term's local identifier."""
    return catalog_identifiers.get(source_uri)


def _validate_compiled_profiles(mapping: dict[str, object], registry: dict[str, object], profiles: object) -> None:
    for value, schema_name in ((mapping, "schemas/config/mapping-profile-7.0.schema.json"), (registry, "schemas/config/namespace-registry.schema.json")):
        schema = json.loads(package_resource_path(schema_name).read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value), key=str)
        if errors:
            raise ValueError(f"Compiled profile is invalid: {errors[0].message}")
    namespace_ids = [item["ontome_namespace_id"] for item in registry["namespaces"]]
    if len(namespace_ids) != len(set(namespace_ids)):
        raise ValueError("OntoME namespace identifiers must be unique")
    rule_ids = [item["id"] for item in mapping["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Mapping rule identifiers must be unique")
    try:
        validate_external_reference_configuration(mapping, registry)
        validate_generation_mapping(mapping, profiles.capability)
    except (ExternalReferenceError, ProfileError) as error:
        raise ValueError(str(error)) from error


def _dump_yaml(value: dict[str, object]) -> bytes:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).encode("utf-8")


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
            _publish_files(output_dir, {"generation-audit.json": _json(result.audit).encode("utf-8")}, replace_managed={"generation-audit.json", "generation-trace.json", "import.xml", "validation.json"})
            print("ontome-importer generate: generation blocked; see generation-audit.json", file=sys.stderr)
            return 3
        xml, trace = write_xml(result.generation, profiles.capability, xsd_path, inventory.source_sha256, target_identity(profiles.manifest))
        _publish_files(output_dir, {
            "import.xml": xml,
            "generation-trace.json": _json(trace).encode("utf-8"),
            "generation-audit.json": _json(result.audit).encode("utf-8"),
        }, replace_managed={"generation-audit.json", "generation-trace.json", "import.xml", "validation.json"})
        print(f"ontome-importer generate: XML and reports written to {output_dir}")
        print(f"Next command: ontome-importer validate --manifest {manifest_path} --xml {output_dir / 'import.xml'} --trace {output_dir / 'generation-trace.json'} --audit {output_dir / 'generation-audit.json'} --output {output_dir / 'validation.json'}")
        return 0
    except XmlGenerationError as error:
        print(f"ontome-importer generate: {error}", file=sys.stderr)
        return 3
    except (ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer generate: {error}", file=sys.stderr)
        return 2


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _hash_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _run_validate(args: argparse.Namespace) -> int:
    try:
        report = validate_generation(Path(args.manifest), Path(args.xml), Path(args.trace), Path(args.audit))
        output = Path(args.output)
        _publish_files(output.parent, {output.name: _json(report).encode("utf-8")}, replace_managed={output.name})
        return 0 if report["valid"] else 3
    except (ProfileError, RdfLoadError, OSError) as error:
        print(f"ontome-importer validate: {error}", file=sys.stderr)
        return 2


def _publish_files(output_dir: Path, files: dict[str, bytes], *, replace_managed: set[str] | None = None) -> None:
    """Stage a complete artifact set before exposing any final artifact."""
    if replace_managed is None and output_dir.exists() and any((output_dir / name).exists() for name in files):
        raise OSError(f"Output directory already contains generated artifacts: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = output_dir if output_dir.is_dir() else output_dir.parent
    staging = Path(tempfile.mkdtemp(prefix=".ontome-importer-", dir=staging_parent))
    archived: dict[str, Path] = {}
    published: list[str] = []
    try:
        for name, content in files.items():
            (staging / name).write_bytes(content)
        output_dir.mkdir(parents=True, exist_ok=True)
        managed = replace_managed or set(files)
        old = [name for name in sorted(managed) if (output_dir / name).exists()]
        if old:
            history = output_dir / ".history" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            history.mkdir(parents=True)
            for name in old:
                os.replace(output_dir / name, history / name)
                archived[name] = history / name
        for name in sorted(files):
            os.replace(staging / name, output_dir / name)
            published.append(name)
    except Exception:
        for name in published:
            (output_dir / name).unlink(missing_ok=True)
        for name, backup in archived.items():
            os.replace(backup, output_dir / name)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _publish_compilation(files: dict[Path, bytes]) -> None:
    """Publish compiled artifacts together and restore every prior file on failure."""
    destinations = list(files)
    if len({path.resolve() for path in destinations}) != len(destinations):
        raise ValueError("Compilation output paths must be distinct")
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


if __name__ == "__main__":
    raise SystemExit(main())
