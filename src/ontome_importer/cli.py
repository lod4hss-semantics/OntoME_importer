"""Command-line interface for the OntoME importer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from ontome_importer import __version__


EXIT_NOT_IMPLEMENTED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ontome-importer")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("audit", help="Audit an RDF ontology against a mapping profile.")
    commands.add_parser("generate", help="Generate OntoME XML from resolved mappings.")
    commands.add_parser("validate", help="Validate a generated OntoME XML import.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(
        f"ontome-importer {args.command} is not available yet.",
        "It will be implemented in a later phase.",
        sep=" ",
        file=sys.stderr,
    )
    return EXIT_NOT_IMPLEMENTED


if __name__ == "__main__":
    raise SystemExit(main())
