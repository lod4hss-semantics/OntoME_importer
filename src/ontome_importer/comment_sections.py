"""Opt-in extraction of CIDOC CRM editorial sections from RDF comments."""

from __future__ import annotations

from dataclasses import dataclass
import re


_HEADINGS = re.compile(
    r"^(?P<section>Quantification|Full path|Scope note|Examples|In First Order Logic)"
    r"(?: of the inverse property)?:\s*(?P<remainder>.*)$",
    re.IGNORECASE,
)
_CARDINALITY = re.compile(r"\(([0-5n]),([1-5n]):([0-5n]),([1-5n])\)\s*$")


@dataclass(frozen=True)
class CommentSections:
    scope_note: str
    examples: tuple[str, ...]
    # XML fields in UML order: domain instances per range, range instances per domain.
    quantifiers: tuple[tuple[str, str], ...]


def parse_cidoc_comment(value: str, *, property: bool = False) -> CommentSections:
    """Split a CIDOC CRM comment; reject ambiguous sections rather than losing text."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in value.splitlines():
        match = _HEADINGS.fullmatch(line.strip())
        if match:
            current = match.group("section").lower()
            if current in sections:
                raise ValueError(f"Duplicate {current} section")
            sections[current] = [match.group("remainder")] if match.group("remainder") else []
        elif current is None:
            if line.strip():
                raise ValueError("Text before the first recognized CIDOC CRM section")
        else:
            sections[current].append(line)
    scope_note = "\n".join(sections.get("scope note", [])).strip()
    if not scope_note:
        raise ValueError("Missing Scope note section")
    examples: list[str] = []
    for line in sections.get("examples", []):
        if line.startswith("- "):
            examples.append(line[2:])
        elif examples:
            examples[-1] += "\n" + line
        elif line.strip():
            raise ValueError("Example without a '- ' delimiter")
    examples = [example.strip() for example in examples]
    if "examples" in sections and not examples:
        raise ValueError("Empty Examples section")
    quantifiers: tuple[tuple[str, str], ...] = ()
    if "quantification" in sections:
        if not property:
            raise ValueError("Quantification on a class comment")
        quantification = "\n".join(sections["quantification"]).strip()
        match = _CARDINALITY.search(quantification)
        if not match:
            raise ValueError("Unrecognized E-A quantification")
        range_min, range_max, domain_min, domain_max = match.groups()
        if any(int(low) > int(high) for low, high in ((range_min, range_max), (domain_min, domain_max)) if high != "n"):
            raise ValueError("Invalid E-A quantification bounds")
        quantifiers = (
            ("domainInstancesMinQuantifier", domain_min),
            ("domainInstancesMaxQuantifier", domain_max),
            ("rangeInstancesMinQuantifier", range_min),
            ("rangeInstancesMaxQuantifier", range_max),
        )
    return CommentSections(scope_note, tuple(examples), quantifiers)
