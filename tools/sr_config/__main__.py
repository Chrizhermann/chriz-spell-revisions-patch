"""Command-line entry point for configurable Spell Revisions tooling."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from .catalog import CatalogError, load_catalog
from .coverage import audit_catalog_coverage, format_coverage_diagnostics
from .generate import GenerationError, generate
from .inventory import write_inventory_report
from .resources import ResourceError
from .source import SourceError
from .text import TraError


_CATALOG_PATH = Path("spell_rev/catalog/changes.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.sr_config")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory_parser = subparsers.add_parser(
        "inventory", help="inventory source/resources or check catalog coverage"
    )
    inventory_parser.add_argument("--json", type=Path, dest="output")
    inventory_parser.add_argument(
        "--check-catalog",
        action="store_true",
        help="validate exhaustive catalog ownership without writing files",
    )
    generate_parser = subparsers.add_parser(
        "generate", help="generate the synchronized config and change catalogs"
    )
    generate_parser.add_argument(
        "--check",
        action="store_true",
        help="report stale generated files without writing them",
    )
    args = parser.parse_args(argv)

    if args.command == "inventory":
        if args.output is None and not args.check_catalog:
            inventory_parser.error("at least one of --json or --check-catalog is required")
        if args.check_catalog:
            try:
                catalog = load_catalog(Path.cwd() / _CATALOG_PATH)
                coverage = audit_catalog_coverage(Path.cwd(), catalog)
            except (CatalogError, ResourceError, SourceError, TraError) as error:
                print(f"catalog coverage failed: {error}", file=sys.stderr)
                return 1
            if not coverage.ok:
                sys.stderr.write(format_coverage_diagnostics(coverage))
                return 1
            sys.stdout.write(format_coverage_diagnostics(coverage))
        if args.output is None:
            return 0
        try:
            report, payload = write_inventory_report(Path.cwd(), args.output)
        except (SourceError, ResourceError) as error:
            print(f"inventory failed: {error}", file=sys.stderr)
            return 1
        summary = report["summary"]
        digest = hashlib.sha256(payload).hexdigest()
        print(
            f"wrote {args.output.as_posix()}: "
            f"{summary['source_node_count']} source nodes, "
            f"{summary['resource_file_count']} resources, "
            f"{summary['binary_edge_count']} binary edges, sha256 {digest}"
        )
        return 0
    if args.command == "generate":
        try:
            result = generate(Path.cwd(), check=args.check)
        except (CatalogError, GenerationError, TraError) as error:
            print(f"generation failed: {error}", file=sys.stderr)
            return 1
        if args.check and result.changed:
            sys.stdout.write(result.diff)
            if result.diff and not result.diff.endswith("\n"):
                sys.stdout.write("\n")
            print(
                "generated files are stale: "
                + ", ".join(
                    path.relative_to(Path.cwd().resolve()).as_posix()
                    for path in result.changed_paths
                ),
                file=sys.stderr,
            )
            return 1
        if result.changed:
            print(
                "generated: "
                + ", ".join(
                    path.relative_to(Path.cwd().resolve()).as_posix()
                    for path in result.changed_paths
                )
            )
        else:
            print("generated files are up to date")
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
