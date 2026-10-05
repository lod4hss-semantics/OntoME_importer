"""Shareable snapshot of the decisions and blockers in a terminal review."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import tempfile

from ontome_importer.review import active_dependencies, status


STATES = {
    "strict": "Strict policy conflicts with ignored assertions",
    "pending": "Resource decisions pending",
    "no_publication": "No resources selected for publication",
    "assertions": "Assertion decisions pending",
    "references": "External references unresolved",
    "blockers": "Generation preflight blocked",
    "ready": "Ready to finalize",
}


def _code(value: object) -> str:
    return "`" + str(value).replace("`", "\\`").replace("\n", " ") + "`"


def _text(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def render_review_report(
    session: dict[str, object], session_path: Path, state: str, *,
    assertion_groups: list[tuple[str, list[dict[str, object]]]] | None = None,
    owl_groups: list[tuple[tuple[str, tuple[str, ...]], list[str]]] | None = None,
    blockers: list[dict[str, object]] | None = None,
) -> str:
    """Describe current choices, with explicit boundaries on which checks ran."""
    progress = status(session)
    choices = session["choices"]
    resource_choices = choices["resources"]
    queue = session["queue"]
    lines = [
        "# OntoME import — review status", "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Session: {_code(session_path)}  ",
        f"Source SHA-256: {_code(session['source_sha256'])}  ",
        f"Assertion policy: {_code(session.get('assertion_policy', 'review'))}", "",
        f"**Result: {STATES[state]}.**", "",
        "This snapshot reflects the review session, not the initial RDF audit. It is not a finalized import or XML validation.", "",
        "## Progress", "",
        f"- Resources: {progress['resources']['publish']} publish, {progress['resources']['exclude']} exclude, {progress['resources']['pending']} pending.",
        f"- Active or potential external references: {progress['dependencies']['configured']}/{progress['dependencies']['total']} configured.",
    ]
    if state == "strict":
        lines.append("- Ignored assertions conflict with the strict policy; assertion and generation preflight checks were deferred.")
    elif state in {"pending", "no_publication"}:
        lines.append("- Assertion and generation preflight checks were deferred; resolve the condition above and rerun `review check`.")
    elif state == "assertions":
        lines.append("- Generation preflight was deferred until assertion decisions and external references are resolved.")
    elif state == "references":
        lines.append("- Generation preflight was deferred until external references are resolved.")
    lines.extend(["", "## Resource decisions", ""])
    reasons = choices.get("resource_reasons", {})
    for kind, title in (("classes", "Classes"), ("properties", "Properties")):
        lines.extend([f"### {title}", ""])
        resources = sorted((item["uri"] for item in queue["resources"][kind]), key=str)
        if not resources:
            lines.append("None in the review queue.")
        else:
            lines.extend(["| URI | Decision | Reason for exclusion |", "| --- | --- | --- |"])
            for uri in resources:
                decision = resource_choices.get(uri, "pending")
                reason = _text(reasons.get(uri, "")) if decision == "exclude" else ""
                lines.append(f"| {_code(uri)} | {decision} | {reason} |")
        lines.append("")
    lines.extend(["## Other recorded decisions", ""])
    assertions = choices.get("assertions", {})
    published = {uri for uri, decision in resource_choices.items() if decision == "publish"}
    active_ids = {item["id"] for group in queue["resources"].values() for resource in group if resource["uri"] in published for item in resource["findings"]}
    active_assertions = [(finding_id, decision) for finding_id, decision in assertions.items() if finding_id in active_ids]
    counts = Counter(item["action"] for _, item in active_assertions)
    lines.append("- Assertion decisions on published resources: " + (", ".join(f"{count} {action}" for action, count in sorted(counts.items())) or "none") + ".")
    for finding_id, decision in sorted(active_assertions):
        lines.append(f"  - {_code(finding_id)}: {decision['action']} — {_text(decision.get('reason', ''))} ({_text(decision.get('reviewer', ''))}).")
    required = [(uri, fields) for uri, fields in choices.get("required", {}).items() if uri in published]
    lines.append(f"- Mandatory field decisions for published resources: {sum(field in {'hasDomain', 'hasRange', 'label_language'} for _, fields in required for field in fields)}.")
    for uri, fields in sorted(required):
        for field, decision in sorted(fields.items()):
            if field in {"hasDomain", "hasRange"}:
                lines.append(f"  - {_code(uri)} {field} → {_code(decision['reference_uri'])}: {_text(decision['rationale'])}.")
            elif field == "label_language":
                lines.append(f"  - {_code(uri)} label language → {_code(decision)}: {_text(fields.get('language_rationale', ''))}.")
    lines.extend(["", "## Remaining issues", ""])
    pending = sorted(uri for uri, decision in resource_choices.items() if decision == "pending")
    if pending:
        lines.extend([f"### Resources awaiting a decision ({len(pending)})", ""])
        lines.extend(f"- {_code(uri)}" for uri in pending)
        lines.append("")
    if assertion_groups:
        lines.extend([f"### Assertion groups awaiting a decision ({len(assertion_groups)})", ""])
        for predicate, findings in assertion_groups:
            affected = sorted({(item.get("scope_resource") or item["resource"])["value"] for item in findings})
            lines.append(f"- {_code(predicate)}: {len(findings)} finding(s), {len(affected)} resource(s).")
            lines.extend(f"  - {_code(uri)}" for uri in affected)
        lines.append("")
    if owl_groups:
        lines.extend(["### OWL domain/range constructions awaiting review", ""])
        for (field, motifs), uris in owl_groups:
            lines.append(f"- {field} / {', '.join(motifs)}: {len(uris)} propert{'y' if len(uris) == 1 else 'ies'}.")
            lines.extend(f"  - {_code(uri)}" for uri in uris)
        lines.append("")
    dependencies = [item for item in active_dependencies(session) if not item.get("catalog_paths")]
    if dependencies:
        external = {item["uri"]: item.get("sources", []) for item in queue.get("external_dependencies", [])}
        lines.extend([f"### Active or potential external references awaiting configuration ({len(dependencies)})", ""])
        for dependency in dependencies:
            lines.append(f"- {_code(dependency['uri'])}")
            lines.extend(f"  - Used by {_code(uri)} ({resource_choices.get(uri, 'pending')})" for uri in external.get(dependency["uri"], []) if resource_choices.get(uri) != "exclude")
        lines.append("")
    if blockers:
        grouped: dict[tuple[str, str], set[str]] = {}
        counts_by_group: Counter[tuple[str, str]] = Counter()
        for item in blockers:
            key = (str(item.get("category", "unknown")), str(item.get("reason") or item.get("decision_needed") or item.get("construct") or "Needs review"))
            grouped.setdefault(key, set()).add(str((item.get("scope_resource") or item.get("resource") or {}).get("value", "")))
            counts_by_group[key] += 1
        lines.extend([f"### Generation blockers ({len(blockers)} findings)", ""])
        for key, uris in sorted(grouped.items()):
            lines.append(f"- **{_text(key[0])}**: {_text(key[1])} ({counts_by_group[key]} findings, {len(uris)} resources).")
            lines.extend(f"  - {_code(uri)}" for uri in sorted(uris))
        lines.append("")
    if state == "ready" and not pending and not assertion_groups and not owl_groups and not dependencies and not blockers:
        lines.extend(["No individual issues were identified in the checks completed so far.", ""])
    commands = {
        "strict": ["assertions", "references"], "pending": ["resources"], "no_publication": ["resources"],
        "assertions": ["assertions", "required"] if owl_groups else ["assertions"],
        "references": ["references"], "blockers": ["required", "resources", "assertions"],
    }
    lines.extend(["## Next actions", ""])
    if state == "ready":
        manifest = session.get("manifest_path") or session_path.parent.parent / "config/generation.yaml"
        lines.append(f"- Finalize: `ontome-importer review finalize --manifest {shlex.quote(str(manifest))} --session {shlex.quote(str(session_path))}`")
    else:
        for command in commands[state]:
            lines.append(f"- `ontome-importer review {command} --session {shlex.quote(str(session_path))}`")
        lines.append(f"- Then rerun `ontome-importer review check --session {shlex.quote(str(session_path))}` to refresh this report.")
    return "\n".join(lines) + "\n"


def save_review_report(path: Path, content: str) -> None:
    """Atomically replace the current report without touching the initial audit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
