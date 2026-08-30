"""Command-line entry point for configurable Spell Revisions tooling."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from .inventory import write_inventory_report
from .resources import ResourceError
from .source import SourceError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.sr_config")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory_parser = subparsers.add_parser(
        "inventory", help="write the deterministic source/resource inventory"
    )
    inventory_parser.add_argument("--json", required=True, type=Path, dest="output")
    args = parser.parse_args(argv)

    if args.command == "inventory":
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
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
